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
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "tesseract",
        "tesseract.exe"
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
    Hybrid PDF extraction using PyMuPDF and Tesseract OCR for scanned pages.
    """
    text = ""
    try:
        # First layer: PyMuPDF for fast extraction
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        ocr_text = ""
        
        for i in range(len(doc)):
            page = doc[i]
            page_text = page.get_text().strip()
            
            # If page has text, use it
            if page_text:
                text += f"\n[Page {i+1} Text]:\n{page_text}\n"
            
            # If page has images OR no text, attempt OCR on the visual layer
            # This handles "images inside PDF" even if there's some background text/metadata
            page_images = page.get_images()
            if len(page_images) > 0 or not page_text:
                print(f"DEBUG: PDF Page {i+1} contains images or no text. Attempting OCR...")
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                if tesseract_path:
                    page_ocr = pytesseract.image_to_string(img)
                    if page_ocr.strip():
                        ocr_text += f"\n[Page {i+1} OCR]:\n{page_ocr}\n"
                else:
                    print(f"DEBUG: No Tesseract for Page {i+1} OCR fallback.")
            
            # Limit to first 5 pages for processing speed
            if i >= 4: break

        doc.close()
        
        # Combine everything
        combined_text = (text + "\n" + ocr_text).strip()
        
        if len(combined_text) < 20:
            print("DEBUG: No substantial text found in PDF.")
            return ""
            
        return combined_text
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
