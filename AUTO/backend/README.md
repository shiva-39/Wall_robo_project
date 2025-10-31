# Backend - Swipe Invoice Extraction

This is a minimal Express backend to accept uploads and return structured JSON for invoices, products and customers.

Main endpoints
- POST /api/upload - accepts form-data file field `file`

How it works
- If `GEMINI_API_KEY` is present in env, extractor will attempt to call Gemini (stubbed currently).
- Otherwise extractor uses `pdf-parse` to extract text and a simple heuristic parser to build invoice objects.

Quickstart
1. cd backend
2. npm install
3. npm run dev
4. POST to http://localhost:4000/api/upload with form-data `file` field

Processing testcases
- `npm run process-testcases` will process files under `assignment_test_cases/*` and write `.extracted.json` files and a `process_results.json` log.

 Env
 - GEMINI_API_KEY (optional) - if you have Gemini API credentials, you can wire them into `src/services/extractor.js`.

 OCR notes:
 - This project includes a tesseract.js-based fallback for image OCR (PNG/JPG). That dependency is declared in `package.json`.
 - Scanned PDFs (image-based PDFs) often require converting PDF pages to images before OCR. That conversion typically requires native tools such as Poppler (pdfimages) or other PDF->image utilities. In this prototype the extractor uses `pdf-parse` first; if the parsed text is empty/very short, the extractor will return a result flagged with `extracted.needs_ocr = true` and a message describing next steps.
 - For better accuracy on scanned PDFs install Poppler and extend `src/services/extractor.js` to convert pages to images and then run tesseract OCR on those images. Alternatively provide a Gemini (document/vision) API key — Gemini can process scanned documents and return structured output.
