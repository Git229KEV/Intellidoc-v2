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
- `API_KEY` — custom API key used by the frontend or clients

### Run Locally
```bash
uvicorn src.main:app --reload
```
The local server will be available at `http://127.0.0.1:8000`.

## Architecture Overview

The project is structured as a FastAPI backend with a document parsing layer and an AI processing layer.

- `src.main` defines the FastAPI application and the `/api/document-analyze` endpoint.
- `backend/DocumentParser.py` extracts raw text from supported files:
  - PDF → `pdfplumber`
  - DOCX → `python-docx`
  - Images → `Pillow` + `pytesseract`
- `backend/AIProcessor.py` sends the extracted text into the AI pipeline and returns structured JSON output.
- The deployed API is served on Vercel as a serverless FastAPI endpoint.

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

This project uses the following AI tool:

### Google Gemini
- Package: `google-genai`
- Model: `gemini-2.5-flash`
- Purpose: summarization, entity extraction, sentiment classification
- Behavior: extracted document text is passed to Gemini with a structured prompt that requests JSON schema output. This ensures the AI returns consistent fields such as `summary`, `entities`, and `sentiment`.

## Known Limitations

- Maximum upload size is limited to 4MB.
- OCR accuracy depends on image quality and clarity.
- The system is optimized for PDF, DOCX, and common image formats, but may fail on highly complex or encrypted documents.
- The deployed API is currently based on a single serverless FastAPI endpoint; heavy loads may require scaling or a dedicated backend.
- Model output quality depends on the Gemini provider and network availability.

## Notes

- This project uses FastAPI for the backend API; the endpoint is not a generic REST framework, but a FastAPI implementation.
- The deployed API endpoint is `https://intellidoc-v2.vercel.app/api/document-analyze`.
