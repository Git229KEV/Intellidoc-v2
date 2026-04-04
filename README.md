# Intelligent Document Processor API

## Description
This repository implements an Intelligent Document Processor built with FastAPI. It accepts uploaded documents (PDF, DOCX, and image files), extracts text, identifies entities, summarizes content, and returns structured intelligence.

## API Endpoint
- POST `https://intellidoc-v2.vercel.app/api/document-analyze`

## Setup Instructions

### Prerequisites
1. **Python 3.10+** installed on your machine.
2. **Tesseract-OCR** installed and available in your system PATH.
3. Optional: a virtual environment for isolation.

### Install Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Copy the example environment file and configure your keys:
```bash
copy .env.example .env
```
Edit `.env` and set:
- `GEMINI_API_KEY` — Google Gemini API key
- `GROQ_API_KEY` — Groq API key (optional fallback)
- `OPENROUTER_API_KEY` — OpenRouter API key (optional fallback)
- `HUGGINGFACE_API_KEY` — Hugging Face API key (optional fallback)
- `API_KEY` — custom API key used by the frontend or clients

### Run Locally
```bash
uvicorn backend.main:app --reload
```
The local server will be available at `http://127.0.0.1:8000`.

## Architecture Overview

The project is structured as a FastAPI backend with a document parsing layer and an AI provider fallback pipeline.

- `backend/main.py` defines the FastAPI application and the `/api/document-analyze` endpoint.
- `backend/DocumentParser.py` extracts raw text from supported files:
  - PDF → `pdfplumber`
  - DOCX → `python-docx`
  - Images → `Pillow` + `pytesseract`
- `backend/AIProcessor.py` performs the document analysis and manages multiple AI providers for fallback processing.
- The deployed API is served on Vercel as a FastAPI serverless function.

## Tech Stack

- **Backend**: Python, FastAPI, Uvicorn
- **Deployment**: Vercel serverless functions
- **Document parsing**:
  - `pdfplumber`
  - `python-docx`
  - `Pillow`
  - `pytesseract`
- **AI/ML**:
  - `google-genai`
- **Environment management**:
  - `python` venv

## AI Tools Used

This project uses a multi-provider AI pipeline with fallback support.

### Google Gemini
- Package: `google-genai`
- Model: `gemini-2.5-flash`
- Purpose: primary document analysis for text and supported image payloads.
- Role: first-choice provider for documents and images; returns structured JSON fields such as `summary`, `entities`, `sentiment`, and `confidence_score`.

### Groq Vision
- Package: `openai`
- Model: `meta-llama/llama-4-scout-17b-16e-instruct`
- Purpose: vision-capable AI used for image document analysis and text extraction when Gemini is unavailable or less reliable.
- Role: used as a secondary provider for images and as a fallback for text analysis.

### OpenRouter
- Package: `openai`
- Model: `meta-llama/llama-3.1-8b-instruct`
- Purpose: fallback provider for document analysis when Gemini or Groq fail due to network issues or high load.
- Role: supports text analysis and limited vision-style image fallback behavior.

### Hugging Face Inference
- Package: `requests`
- Model endpoint: `https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-8B-Instruct`
- Purpose: final fallback provider for text-based document analysis.
- Role: used only after Gemini, Groq, and OpenRouter fail.

### Local OCR / Text Extraction
- Package: `pytesseract`
- Package: `Pillow`
- Purpose: local OCR extraction for images before AI analysis, improving fallback resilience and helping support providers that need plain text.

## Known Limitations

- Maximum upload size is limited to 4MB.
- OCR accuracy depends on image quality and clarity.
- The system is optimized for PDF, DOCX, and common image formats, but may fail on highly complex or encrypted documents.
- The deployed API is currently based on a single serverless FastAPI endpoint; heavy loads may require scaling or a dedicated backend.
- Model output quality depends on the Gemini provider and network availability.

## Notes

- This project uses FastAPI for the backend API; the endpoint is not a generic REST framework, but a FastAPI implementation.
- The deployed API endpoint is `https://intellidoc-v2.vercel.app/api/document-analyze`.
