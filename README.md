# Intelligent Document Processor — IntelliDoc

## Description
IntelliDoc is a full-stack Intelligent Document Processor built with **FastAPI** (backend) and **React** (frontend). It accepts uploaded documents (PDF, DOCX, and image files), extracts text, identifies entities, summarizes content, and returns structured AI intelligence. The platform now includes user authentication and a personal file dashboard powered by **Supabase**.

---

## 🆕 Recent Updates

### Supabase Integration (April 2026)

- **Google Authentication** — Users can now sign in via Google OAuth through Supabase Auth. Authentication state is persisted across sessions and managed globally via a React context (`AuthContext`).
- **File Storage** — Uploaded documents and document analysis result PDFs are stored in Supabase Storage buckets (`documents` and `analysis-results`). Files are scoped per user to ensure privacy.
- **Dashboard Page** — A new `/dashboard` route has been added to the frontend. Authenticated users can:
  - View all their **uploaded files** under the *Uploaded Files* tab.
  - View and download **document analysis results** (as PDFs) under the *Document Analysis Results* tab.
  - **Delete** individual files using an inline confirmation modal (no browser alerts).
  - See consistent empty-state feedback when no files are present in either tab.
- **Routing** — `react-router-dom` has been added to handle SPA navigation between the landing/analyzer page and the Dashboard. A `vercel.json` catch-all rewrite rule ensures deep links work correctly on Vercel.

---

## Live Demo

- **Frontend**: [https://intellidoc-v2.vercel.app](https://intellidoc-v2.vercel.app)
- **API Endpoint**: `POST https://intellidoc-v2.vercel.app/api/document-analyze`

---

## Setup Instructions

### Prerequisites
1. **Python 3.10+**
2. **Node.js 18+** and **npm**
3. **Tesseract-OCR** installed and available in your system PATH (optional, for local OCR fallback)
4. A **Supabase** project with:
   - Google OAuth provider enabled
   - Two storage buckets created: `documents` and `analysis-results`

### Backend — Install Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend — Install Dependencies
```bash
cd frontend
npm install
```

### Environment Variables

**Backend** — Copy and edit `.env.example`:
```bash
copy .env.example .env
```
Configure:
- `GEMINI_API_KEY` — Google Gemini API key
- `GROQ_API_KEY` — Groq API key (optional fallback)
- `OPENROUTER_API_KEY` — OpenRouter API key (optional fallback)
- `HUGGINGFACE_API_KEY` — Hugging Face API key (optional fallback)
- `API_KEY` — Custom API key used by the frontend or clients

**Frontend** — Edit `frontend/.env`:
```env
VITE_SUPABASE_URL=https://<your-project-id>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-anon-key>
```

### Run Locally
```bash
# Backend
uvicorn backend.main:app --reload

# Frontend (in a separate terminal)
cd frontend
npm run dev
```
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:5173`

---

## Architecture Overview

```
Intelli-Doc Final/
├── backend/
│   ├── main.py             # FastAPI app & /api/document-analyze endpoint
│   ├── DocumentParser.py   # Text extraction (PDF, DOCX, Image)
│   └── AIProcessor.py      # Multi-provider AI analysis pipeline
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Root component with react-router-dom routes
│   │   ├── supabaseClient.js   # Supabase client initialization
│   │   ├── AuthContext.jsx     # Global auth state (Google OAuth)
│   │   ├── Dashboard.jsx       # User dashboard (files & analysis results)
│   │   └── ...
│   └── .env                # Frontend environment variables
└── vercel.json             # Vercel SPA rewrite config
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python, FastAPI, Uvicorn |
| **Frontend** | React (Vite), react-router-dom |
| **Auth & Storage** | Supabase (Google OAuth, Storage Buckets) |
| **Deployment** | Vercel (serverless functions + static frontend) |
| **Document Parsing** | pdfplumber, python-docx, Pillow, pytesseract |
| **AI Providers** | Google Gemini, Groq, OpenRouter, Hugging Face |

---

## AI Tools Used

### Google Gemini
- Package: `google-genai`
- Model: `gemini-2.5-flash`
- Role: Primary provider — structured JSON analysis (summary, entities, sentiment, confidence score) for text and images.

### Groq Vision
- Package: `openai`
- Model: `meta-llama/llama-4-scout-17b-16e-instruct`
- Role: Secondary provider — vision-capable fallback for image documents.

### OpenRouter
- Package: `openai`
- Model: `meta-llama/llama-3.1-8b-instruct`
- Role: Third-tier fallback for text and limited image analysis.

### Hugging Face Inference
- Package: `requests`
- Endpoint: `https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-8B-Instruct`
- Role: Final fallback for text-based document analysis.

### Local OCR
- Packages: `pytesseract`, `Pillow`
- Role: Local text extraction from images before AI analysis.

---

## Known Limitations

- Maximum upload size is limited to **4 MB**.
- OCR accuracy depends on image quality and clarity.
- Optimized for PDF, DOCX, and common image formats; encrypted or complex layouts may fail.
- Supabase free-tier storage limits apply.
- Model output quality depends on AI provider availability and network conditions.

---

## Notes

- The Supabase auth callback is handled at `/auth/callback` — ensure your Supabase project's redirect URLs include `https://intellidoc-v2.vercel.app/auth/callback` (and `http://localhost:5173/auth/callback` for local dev).
- The deployed API endpoint remains: `https://intellidoc-v2.vercel.app/api/document-analyze`.
