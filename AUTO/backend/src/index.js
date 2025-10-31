require('dotenv').config();
const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const extractor = require('./services/extractor');

const app = express();
const upload = multer({ dest: path.join(__dirname, '..', 'uploads/') });
app.use(express.json());

app.post('/api/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
    const inputPath = req.file.path;
    const result = await extractor.processFile(inputPath, req.file.originalname);
    // keep the uploaded file for debugging; optionally unlink
    res.json({ ok: true, data: result });
  } catch (err) {
    console.error('upload error', err);
    res.status(500).json({ error: String(err) });
  }
});

// basic health
app.get('/api/health', (req, res) => res.json({ ok: true, ts: Date.now() }));

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => console.log(`Backend listening on ${PORT}`));
