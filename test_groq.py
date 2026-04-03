import os, sys, io, json
from dotenv import load_dotenv
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from AIProcessor import _try_groq, _try_gemini
load_dotenv()
from PIL import Image

img = Image.new('RGB', (10, 10))
b = io.BytesIO()
img.save(b, 'PNG')

try:
    _try_groq(b.getvalue(), 'png', '', 'test')
except Exception as e:
    if hasattr(e, 'response'):
        with open('groq_err.json', 'w') as f:
            json.dump(getattr(e.response, 'json', lambda: {})(), f)

try:
    _try_gemini(b.getvalue(), 'png', '', 'test')
except Exception as e:
    with open('gemini_err.txt', 'w') as f:
        f.write(str(e))
