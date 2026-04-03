import subprocess
import os

def check_tesseract():
    print("--- Searching for Tesseract binary ---")
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
        "tesseract.exe"
    ]
    
    found = False
    for path in possible_paths:
        try:
            # shell=True for 'tesseract.exe' check on PATH
            result = subprocess.run([path, "--version"], capture_output=True, text=True, shell=(path=="tesseract.exe"))
            if result.returncode == 0:
                print(f"SUCCESS: Tesseract version response at {path}")
                print(result.stdout.split('\n')[0])
                found = True
                break
        except Exception as e:
            print(f"DEBUG: Failed at {path}: {str(e)}")
            
    if not found:
        print("FAILURE: Tesseract-OCR binary NOT found in common locations or PATH.")

if __name__ == "__main__":
    check_tesseract()
