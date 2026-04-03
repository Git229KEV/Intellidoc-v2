import os
import sys
from dotenv import load_dotenv

# Add backend to path to allow imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from AIProcessor import generate_analysis

def test_image_analysis():
    load_dotenv()
    image_path = r"C:\Users\kevin\Downloads\sample3.jpg"
    
    if not os.path.exists(image_path):
        print(f"FAILURE: Image not found at {image_path}")
        return

    print(f"--- Starting analysis for {image_path} ---")
    with open(image_path, "rb") as f:
        file_bytes = f.read()
    
    try:
        # Note: DocumentParser text extraction will likely fail (as OCR is missing)
        # But Groq Llama 3.2 Vision fallback should handle the raw bytes!
        result = generate_analysis(file_bytes, "image", "")
        
        print("\n--- ANALYSIS RESULT ---")
        print(f"Summary: {result.get('summary')}")
        print(f"Sentiment: {result.get('sentiment')}")
        print(f"Confidence: {result.get('confidence_score')}")
        print(f"Entities: {result.get('entities')}")
        
    except Exception as e:
        print(f"FAILURE: Analysis crashed: {str(e)}")

if __name__ == "__main__":
    test_image_analysis()
