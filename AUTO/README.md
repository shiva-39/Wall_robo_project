# Automated Data Extraction and Invoice Management (Swipe)

This repository contains a full-stack prototype for "Automated Data Extraction and Invoice Management".

Overview
- Backend: Node.js + Express handling file uploads and running an extraction pipeline (Gemini if configured, otherwise PDF text extraction + OCR fallback).
- Frontend: React + Vite with Redux Toolkit for central state (Invoices, Products, Customers). Upload files, review extracted data, edit missing fields, and keep related entities in sync.

Folders
- `backend/` - Express server and extraction scripts
- `frontend/` - React app (Vite) with Redux
- `assignment_test_cases/` - provided invoices and test PDFs

Next steps
1. `cd backend` && `npm install` then `npm run dev` to start the API server
2. `cd frontend` && `npm install` && `npm run dev` to start frontend

See `backend/README.md` and `frontend/README.md` for details.
