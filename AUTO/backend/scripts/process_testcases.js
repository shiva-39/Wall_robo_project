const path = require('path');
const fs = require('fs');
const extractor = require('../src/services/extractor');

const testCasesDir = path.join(__dirname, '..', '..', 'assignment_test_cases');

async function run() {
  if (!fs.existsSync(testCasesDir)) {
    console.error('assignment_test_cases folder not found at', testCasesDir);
    process.exit(1);
  }
  const results = [];
  const tcDirs = fs.readdirSync(testCasesDir).filter(d => fs.statSync(path.join(testCasesDir, d)).isDirectory());
  let totalFiles = 0;
  let processed = 0;
  let skipped = 0;
  const supportedRe = /\.(pdf|png|jpg|jpeg|xls|xlsx)$/i;
  for (const d of tcDirs) {
    const dir = path.join(testCasesDir, d);
    const files = fs.readdirSync(dir);
    for (const f of files) {
      totalFiles++;
      const p = path.join(dir, f);
      // skip outputs and non-supported files
      if (f.endsWith('.extracted.json')) {
        skipped++;
        console.log('Skipping already-processed output file:', p);
        continue;
      }
      if (!supportedRe.test(f)) {
        skipped++;
        console.log('Skipping unsupported file type:', p);
        continue;
      }
      console.log('Processing', p);
      try {
        const out = await extractor.processFile(p, f);
        results.push({ file: p, ok: true, out });
        const outPath = path.join(dir, f + '.extracted.json');
        fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
        console.log('Wrote', outPath);
        processed++;
      } catch (err) {
        console.error('Error processing', p, err);
        results.push({ file: p, ok: false, error: String(err) });
      }
    }
  }
  // summary
  console.log('\nSummary:');
  console.log('  Total files scanned:', totalFiles);
  console.log('  Processed:', processed);
  console.log('  Skipped:', skipped);
  const logPath = path.join(testCasesDir, 'process_results.json');
  fs.writeFileSync(logPath, JSON.stringify(results, null, 2));
  console.log('Done. Results:', logPath);
}

run();
