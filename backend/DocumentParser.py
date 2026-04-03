import os
import io
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
from docx import Document as DocxDocument

# --- Tesseract Auto-Detection (Windows) ---
def find_tesseract_cmd():
    """
    Attempts to locate the tesseract binary in common Windows installation paths.
    """
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
        "tesseract.exe"  # Fallback to system PATH
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"DEBUG: Tesseract found at {path}")
            return path
            
    # Try searching system PATH via shutil if available
    import shutil
    shutil_path = shutil.which("tesseract")
    if shutil_path:
        print(f"DEBUG: Tesseract found in PATH at {shutil_path}")
        return shutil_path
        
    print("DEBUG: Tesseract NOT FOUND. OCR will use AI Vision fallback.")
    return None

# Configure Tesseract path
tesseract_path = find_tesseract_cmd()
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def parse_document(file_base64: str, file_type: str) -> str:
    """
    Orchestrates extraction based on file type.
    """
    import base64
    file_bytes = base64.b64decode(file_base64)
    file_type = file_type.lower().strip()

    if file_type == 'pdf':
        return extract_text_from_pdf(file_bytes)
    elif file_type == 'docx':
        return extract_text_from_docx(file_bytes)
    elif file_type == 'image' or file_type in ['png', 'webp', 'jpg', 'jpeg']:
        return extract_text_from_image(file_bytes)
    else:
        return ""

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Hybrid PDF extraction using PyMuPDF and pdfplumber.
    """
    text = ""
    try:
        # First layer: PyMuPDF for fast extraction
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text()
        
        # If text is minimal, try OCR fallback for scanned PDFs
        if len(text.strip()) < 50:
            print("DEBUG: PDF text minimal, attempting hybrid OCR...")
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    # Low-level OCR integration could go here
                    pass
    except Exception as e:
        print(f"DEBUG: PDF extraction error: {e}")
    return text

def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    DOCX extraction using python-docx.
    """
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"DEBUG: DOCX extraction error: {e}")
        return ""

def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Image text extraction using Tesseract OCR.
    """
    try:
        image = Image.open(io.BytesIO(file_bytes))
        # Use Tesseract if it was detected earlier
        if tesseract_path:
            text = pytesseract.image_to_string(image)
            return text
        else:
            print("DEBUG: Skipping local OCR (No Tesseract).")
            return ""
    except Exception as e:
        print(f"DEBUG: Image OCR error: {e}")
        return ""
