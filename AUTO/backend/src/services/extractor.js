const fs = require('fs');
const path = require('path');
const pdf = require('pdf-parse');
const axios = require('axios');
const Tesseract = require('tesseract.js');
const os = require('os');
const XLSX = require('xlsx');

// Simple heuristic extractor: extract text from PDF and run regex heuristics.
// If GEMINI_API_KEY is provided, this module will call Gemini document API (stubbed) —
// otherwise fallback to pdf-parse text extraction.

async function extractWithPdfParse(filePath) {
  const dataBuffer = fs.readFileSync(filePath);
  const data = await pdf(dataBuffer);
  return data.text;
}

async function runTesseractOCR(filePath) {
  // Use the Tesseract.recognize helper (simpler and works across versions)
  try {
    const res = await Tesseract.recognize(filePath, 'eng', { logger: m => { /* optional logging */ } });
    return res?.data?.text || '';
  } catch (err) {
    throw err;
  }
}

function parseExcelFile(filePath) {
  // Read workbook and try to detect invoice data in the first sheet
  try {
    const wb = XLSX.readFile(filePath);
    const sheetName = wb.SheetNames[0];
    const ws = wb.Sheets[sheetName];
    const json = XLSX.utils.sheet_to_json(ws, { defval: '' });
    // Heuristic: if rows contain Description/Qty/Unit Price columns, treat as line items
    const lowerKeys = json.length ? Object.keys(json[0]).map(k => k.toLowerCase()) : [];
    const hasDesc = lowerKeys.find(k => k.includes('desc') || k.includes('description') || k.includes('item'));
    const hasQty = lowerKeys.find(k => k.includes('qty') || k.includes('quantity'));
    const hasPrice = lowerKeys.find(k => k.includes('price') || k.includes('unit'));
    const items = [];
    if (hasDesc) {
      for (const row of json) {
        const description = row[Object.keys(row).find(k => k.toLowerCase().includes('desc') || k.toLowerCase().includes('description') || k.toLowerCase().includes('item'))] || '';
        const qty = row[Object.keys(row).find(k => k.toLowerCase().includes('qty') || k.toLowerCase().includes('quantity'))] || '';
        const price = row[Object.keys(row).find(k => k.toLowerCase().includes('price') || k.toLowerCase().includes('unit'))] || '';
        if (description || qty || price) items.push({ description: String(description).trim(), qty: qty || '', unit_price: price || '' });
      }
    }
    // Try to pick up invoice-level metadata from sheet properties or first rows
    let invoice_number = '';
    let invoice_date = '';
    let total = '';
    if (json.length && json[0]) {
      const combined = JSON.stringify(json[0]);
      const mInv = combined.match(/invoice\s*[:#]?\s*([A-Z0-9-]+)/i);
      if (mInv) invoice_number = mInv[1];
    }
    return { invoice_number: invoice_number || null, invoice_date: invoice_date || null, total: total || null, items };
  } catch (err) {
    return null;
  }
}

async function callGeminiStub(filePath) {
  // If you have Gemini API credentials set in env, implement here.
  // For now we return null to trigger fallback.
  if (!process.env.GEMINI_API_KEY) return null;
  // Example placeholder: implement document processing call
  return null;
}

function normalizeNumberString(s) {
  if (s == null) return null;
  const str = String(s).replace(/[^0-9.,\-]/g, '').trim();
  if (!str) return null;
  // Replace comma-thousand separators when appropriate
  const parts = str.split(/[.,]/);
  // If there are multiple commas/periods, remove thousand separators
  const cleaned = str.replace(/,/g, '');
  const n = Number(cleaned);
  if (!isNaN(n)) return n;
  // fallback: try replacing periods
  const alt = str.replace(/\./g, '').replace(/,/g, '.');
  const n2 = Number(alt);
  return isNaN(n2) ? null : n2;
}

function parseDateString(s) {
  if (!s) return null;
  const candidate = String(s).trim();
  // Try ISO first
  const iso = new Date(candidate);
  if (!isNaN(iso.getTime())) {
    return iso.toISOString().slice(0,10);
  }
  // Try dd MMM yyyy (e.g., 12 Nov 2024)
  const m = candidate.match(/(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})/);
  if (m) {
    const day = m[1].padStart(2,'0');
    const monthNames = { jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12 };
    const mon = monthNames[m[2].toLowerCase().slice(0,3)];
    if (mon) return `${m[3]}-${String(mon).padStart(2,'0')}-${day}`;
  }
  // Try dd/mm/yyyy or dd-mm-yyyy
  const m2 = candidate.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})/);
  if (m2) {
    let day = m2[1].padStart(2,'0');
    let month = m2[2].padStart(2,'0');
    let year = m2[3];
    if (year.length === 2) year = '20' + year;
    return `${year}-${month}-${day}`;
  }
  return null;
}

function heuristicParseInvoiceText(text) {
  const lines = text.split('\n').map(l => l.replace(/\u00A0/g,' ').trim()).filter(Boolean);
  const joined = lines.join('\n');

  // invoice number: look for common labels and fallback to short alphanumeric tokens near top
  let invoice_number = null;
  const invRegexes = [
    /invoice\s*(?:number|no\.?|#|:)\s*([A-Z0-9\-\/]+)/i,
    /tax\s*invoice\s*(?:no\.?|:)\s*([A-Z0-9\-\/]+)/i,
    /invoice\s*[:#]\s*([A-Z0-9\-\/]+)/i,
    /bill\s*no\.?\s*[:#]?\s*([A-Z0-9\-\/]+)/i,
    /ref\s*[:#]?\s*([A-Z0-9\-\/]+)/i
  ];
  for (const rx of invRegexes) {
    const m = joined.match(rx);
    if (m && m[1]) { invoice_number = m[1].trim(); break; }
  }
  if (!invoice_number) {
    // fallback: first short token after word Invoice in first 10 lines
    for (let i=0;i<Math.min(10,lines.length);i++){
      const l = lines[i];
      const m = l.match(/invoice[^A-Za-z0-9]*([A-Z0-9\-\/]{3,40})/i);
      if (m && m[1]) { invoice_number = m[1].trim(); break; }
    }
  }

  // date detection: search lines for date-like tokens
  let invoice_date = null;
  for (const l of lines.slice(0, 40)) {
    const m = l.match(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})/);
    if (m) { invoice_date = parseDateString(m[1]); break; }
    const m2 = l.match(/(\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})/);
    if (m2) { invoice_date = parseDateString(m2[1]); break; }
    const m3 = l.match(/(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})/);
    if (m3) { invoice_date = parseDateString(m3[1]); break; }
  }

  // total detection: look for lines mentioning total, balance due, amount payable
  let total = null;
  for (let i = lines.length-1; i >= 0; i--) {
    const l = lines[i];
    if (/grand\s*total|amount\s*due|balance\s*due|total\s*amount|invoice\s*total|amount\s*payable|total\s*[:]/i.test(l)) {
      const m = l.match(/([₹$€£]?\s?[\d,]+(?:\.\d{1,2})?)/g);
      if (m && m.length) { total = normalizeNumberString(m[m.length-1]); break; }
    }
  }
  // fallback: find the last currency-like number in document
  if (total == null) {
    const allNums = joined.match(/([₹$€£]?\s?[\d,]+(?:\.\d{1,2})?)/g);
    if (allNums && allNums.length) {
      total = normalizeNumberString(allNums[allNums.length-1]);
    }
  }

  // line-items: look for blocks with headers (description, qty, price) or lines with multiple columns
  let items = [];
  // find header index
  let headerIdx = -1;
  for (let i=0;i<Math.min(50,lines.length);i++){
    if (/description|qty|quantity|unit price|price|amount|total/i.test(lines[i])) { headerIdx = i; break; }
  }
  const candidateLines = headerIdx >=0 ? lines.slice(headerIdx+1, headerIdx+1+60) : lines.slice(0, Math.min(60, lines.length));
  for (const l of candidateLines) {
    // skip lines that look like addresses / totals
    if (/subtotal|total|tax|invoice|bill|date|due|terms/i.test(l)) continue;
    // split on two+ spaces or tabs
    const parts = l.split(/\s{2,}|\t/).map(p => p.trim()).filter(Boolean);
    if (parts.length >= 2) {
      // try to detect qty and price among last parts
      let qty = null; let price = null;
      // detect numeric tokens in parts
      const numericParts = parts.map(p => ({ raw: p, num: (p.match(/[\d,.]+/) || [null])[0] }));
      if (numericParts.length >= 2) {
        // if last part looks like price
        const lastNum = numericParts[numericParts.length-1].num;
        price = normalizeNumberString(lastNum);
        // if second last is qty (integer)
        const secondLast = numericParts[numericParts.length-2].num;
        if (secondLast && /^\d+$/.test(secondLast.replace(/,/g,''))) qty = Number(secondLast.replace(/,/g,''));
      }
      const description = parts.slice(0, Math.max(1, parts.length- (price?2:1))).join(' ').trim();
      // Only accept as item if description present
      if (description) items.push({ description, qty: qty || 1, unit_price: price, raw: l });
    } else {
      // try to extract single-line item like "Widget 2 199.00"
      const m = l.match(/(.+)\s+(\d+)\s+([\d,]+(?:\.\d{1,2})?)/);
      if (m) items.push({ description: m[1].trim(), qty: Number(m[2]), unit_price: normalizeNumberString(m[3]), raw: l });
    }
    if (items.length >= 200) break;
  }

  // If no items found, attempt a looser search for lines with two numbers (qty+price)
  if (!items.length) {
    for (const l of lines) {
      const m = l.match(/(.+)\s+(\d+)\s+([\d,]+(?:\.\d{1,2})?)/);
      if (m) {
        items.push({ description: m[1].trim(), qty: Number(m[2]), unit_price: normalizeNumberString(m[3]), raw: l });
      }
      if (items.length >= 50) break;
    }
  }

  return {
    invoice_number: invoice_number || null,
    invoice_date: invoice_date || null,
    total: total == null ? null : (typeof total === 'number' ? total : normalizeNumberString(total)),
    items: items
  };
}

async function processFile(filePath, originalName) {
  // Try Gemini first
  const gemini = await callGeminiStub(filePath);
  if (gemini && gemini.data) {
    return gemini.data;
  }
  // Fallback: handle Excel files, pdf-parse and OCR for images
  const ext = path.extname(filePath || originalName || '').toLowerCase();
  let text = '';
  let ocr_used = false;
  // Excel handling
  if (ext === '.xls' || ext === '.xlsx') {
    const parsedExcel = parseExcelFile(filePath);
    if (parsedExcel) {
      const parsed = parsedExcel;
      const result = {
        source_filename: path.basename(originalName || filePath),
        _meta: { source_type: 'excel' },
        extracted: parsed,
        customers: [],
        products: parsed.items.map((it, i) => ({ id: `p_${i+1}`, name: it.description, sku: null, price: it.unit_price })),
        invoices: parsed.items.length ? [{ id: `inv_${Date.now()}`, invoice_number: parsed.invoice_number, invoice_date: parsed.invoice_date, total: parsed.total, line_items: parsed.items.map((it, idx) => ({ id: `li_${idx+1}`, description: it.description, qty: it.qty, unit_price: it.unit_price })) }] : []
      };
      return result;
    }
    // if parseExcelFile failed, fall through to needs_ocr
  }
  if (ext === '.png' || ext === '.jpg' || ext === '.jpeg' || ext === '.tiff' || ext === '.bmp') {
    // run OCR on image files
    try {
      text = await runTesseractOCR(filePath);
      ocr_used = true;
    } catch (err) {
      console.warn('Tesseract OCR failed for', filePath, err.message || err);
      text = '';
    }
  } else {
    // try pdf-parse for PDF and other documents
    try {
      text = await extractWithPdfParse(filePath);
    } catch (err) {
      console.warn('pdf-parse failed for', filePath, err.message || err);
      text = '';
    }
    // if pdf-parse returned little or no text, mark as needs OCR (scanned PDF)
    if (!text || text.trim().length < 80) {
      // We cannot reliably OCR PDF pages without additional native dependencies (poppler) in this environment.
      // For now attempt no further PDF OCR; return partial result with a flag.
      const partial = {
        source_filename: path.basename(originalName || filePath),
        extracted: { needs_ocr: true, message: 'PDF likely scanned or image-based. Enable Gemini or install poppler/pdf->image converters for OCR.' },
        customers: [],
        products: [],
        invoices: []
      };
      return partial;
    }
  }
  const parsed = heuristicParseInvoiceText(text);
  // Build structured object expected by frontend
  const result = {
    source_filename: path.basename(originalName || filePath),
    _meta: { ocr_used: !!ocr_used },
    extracted: parsed,
    customers: [],
    products: parsed.items.map((it, i) => ({ id: `p_${i+1}`, name: it.description, sku: null, price: it.unit_price })),
    invoices: [{
      id: `inv_${Date.now()}`,
      invoice_number: parsed.invoice_number,
      invoice_date: parsed.invoice_date,
      total: parsed.total,
      line_items: parsed.items.map((it, idx) => ({ id: `li_${idx+1}`, description: it.description, qty: it.qty, unit_price: it.unit_price }))
    }]
  };
  return result;
}

module.exports = { processFile };
