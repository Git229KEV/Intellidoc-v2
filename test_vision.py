import os
import sys
import base64
import json
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from AIProcessor import _try_gemini, _try_groq, clean_json_response

load_dotenv()

from PIL import Image, ImageDraw
import io

img = Image.new('RGB', (200, 50), color = (255, 255, 255))
d = ImageDraw.Draw(img)
d.text((10,10), "INVOICE #12345 TOTAL: $500", fill=(0,0,0))

img_byte_arr = io.BytesIO()
img.save(img_byte_arr, format='PNG')
img_bytes = img_byte_arr.getvalue()

prompt = """
    Please analyze the document content with extreme precision.
    Extract the following standard entities: Names, Dates, Organizations, Monetary Amounts.
    Identify UNIQUE DOCUMENT FACTORS: Invoice numbers, Ref IDs, Passport/ID numbers, Order numbers, etc.
    Extract Contact Details (phone, email) and Locations (addresses).
    Determine overall sentiment (Positive, Negative, or Neutral) and provide a 1-2 sentence summary.
    
    IMPORTANT: You MUST return the result in STRICT JSON format matching this schema:
    {
      "summary": "...",
      "entities": {
        "names": [], "dates": [], "organizations": [], "amounts": [],
        "unique_identifiers": [], "locations": [], "contact_details": []
      },
      "sentiment": "...",
      "confidence_score": 0.95
    }
"""

print("=== Testing Gemini ===")
try:
    gem_res = _try_gemini(img_bytes, 'png', '', prompt)
    print("Gemini Output:", gem_res)
except Exception as e:
    print("Gemini Error:", e)

print("\n=== Testing Groq ===")
try:
    groq_res = _try_groq(img_bytes, 'png', '', prompt)
    print("Groq Output:", groq_res)
except Exception as e:
    print("Groq Error:", e)
