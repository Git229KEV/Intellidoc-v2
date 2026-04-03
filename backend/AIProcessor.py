import os
import json
import base64
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from openai import OpenAI

class EntitiesSchema(BaseModel):
    names: list[str] = Field(default_factory=list, description="Extracted names of people")
    dates: list[str] = Field(default_factory=list, description="Extracted dates")
    organizations: list[str] = Field(default_factory=list, description="Extracted organizations/company names")
    amounts: list[str] = Field(default_factory=list, description="Extracted monetary amounts")
    unique_identifiers: list[str] = Field(default_factory=list, description="Extracted IDs, Invoice Nos, Passport Nos, etc.")
    locations: list[str] = Field(default_factory=list, description="Extracted addresses or specific landmarks")
    contact_details: list[str] = Field(default_factory=list, description="Extracted phone numbers, email addresses, etc.")

class AnalysisSchema(BaseModel):
    summary: str = Field(default="", description="A concise and accurate summary of the document content (max 2 sentences)")
    entities: EntitiesSchema = Field(default_factory=EntitiesSchema)
    sentiment: str = Field(default="Neutral", description="The overall sentiment of the content. Must be Positive, Negative, or Neutral")
    confidence_score: float = Field(default=0.0, description="Confidence score for the extraction (0.0 to 1.0)")

def clean_json_response(raw_text: str) -> dict:
    """
    Cleans markdown code blocks and attempts to parse JSON from AI responses.
    """
    try:
        # Standard cleaning
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # If extraction within brackets fails, try searching
        if not (text.startswith('{') and text.endswith('}')):
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != 0:
                text = text[start:end]
                
        return json.loads(text)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {str(e)}\nRaw: {raw_text[:200]}")
        raise ValueError(f"Invalid JSON format from AI: {str(e)}")

def generate_analysis(file_bytes: bytes, file_type: str, extracted_text: str = "") -> dict:
    """
    Attempts to analyze the document using multiple AI providers in sequence.
    Priority: Gemini -> Groq Vision -> OpenRouter -> Hugging Face
    """
    
    prompt = """
    CRITICAL: You are an expert document OCR and Analysis agent. 
    Analyze the provided document image or text with 100% precision.
    
    1. EXTRACR ALL: Names, Dates, Organizations, Monetary Amounts.
    2. UNIQUE IDENTIFIERS: Extract EVERY ID, Invoice Number, Receipt ID, etc.
    3. LOCATIONS & CONTACTS: Extract full addresses, phone numbers, and emails.
    4. SENTIMENT: Determine if the document tone is Positive, Negative, or Neutral.
    5. SUMMARY: 1-2 sentence high-level synthesis of what this document is.

    IMPORTANT: If this is an IMAGE, perform deep visual OCR first. 
    You MUST return the result in STRICT JSON format matching this schema:
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

    # Determine provider priority based on file type
    # For images, Groq Vision is currently more stable/accurate for extracting text
    is_image = file_type.lower().strip() in ['png', 'webp', 'jpg', 'jpeg', 'image']
    
    if is_image:
        providers = [
            ("Groq", _try_groq),
            ("Gemini", _try_gemini),
            ("OpenRouter", _try_openrouter)
        ]
    else:
        providers = [
            ("Gemini", _try_gemini),
            ("Groq", _try_groq),
            ("OpenRouter", _try_openrouter),
            ("HuggingFace", _try_huggingface)
        ]

    errors = []
    for name, func in providers:
        try:
            print(f"DEBUG: Attempting analysis with {name}...")
            raw_result = func(file_bytes, file_type, extracted_text, prompt)
            
            if raw_result:
                # Some funcs return strings, some return dicts. Normalize to strings for cleaning.
                if isinstance(raw_result, dict):
                    json_data = raw_result
                else:
                    json_data = clean_json_response(str(raw_result))
                
                print(f"DEBUG: {name} raw success. Validating schema...")
                validated_data = AnalysisSchema.model_validate(json_data)
                return validated_data.model_dump()
                
        except Exception as e:
            error_msg = f"{name} process failed: {str(e)}"
            print(f"DEBUG: {error_msg}")
            errors.append(error_msg)
            continue

    return {
        "summary": "All AI providers failed to process this document.",
        "entities": {
            "names": [], "dates": [], "organizations": [], "amounts": [],
            "unique_identifiers": [], "locations": [], "contact_details": []
        },
        "sentiment": "Neutral",
        "confidence_score": 0.0,
        "error_details": "; ".join(errors)
    }

def _try_gemini(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return None
    
    client = genai.Client(api_key=api_key)
    file_type = file_type.lower().strip()
    
    contents = []
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image']:
        # Ensure common image formats are consistent
        mime = "image/jpeg"
        if file_type == 'png': mime = "image/png"
        elif file_type == 'webp': mime = "image/webp"
        contents = [types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt]
    elif file_type == 'pdf':
        contents = [types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"), prompt]
    else:
        contents = [f"Document Text:\n\n{extracted_text}\n\n{prompt}"]
    
    # Set a strict 7s timeout for Gemini in serverless environment
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnalysisSchema,
            temperature=0.1,
            http_options={'timeout': 7000} # 7 seconds
        ),
    )
    # The new SDK response.text is already clean JSON if response_schema is used,
    # but we handle it via the main loop's cleaning just in case.
    return response.text

def _try_groq(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return None
    
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    file_type = file_type.lower().strip()

    messages = []
    # Vision Support for Groq
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image']:
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        # Map back to standard jpeg/png for data URL
        mime_url = "image/jpeg"
        if file_type == 'png': mime_url = "image/png"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_url};base64,{base64_image}"}
                    }
                ]
            }
        ]
    else:
        content = f"Document Text:\n\n{extracted_text}\n\n{prompt}"
        messages = [{"role": "user", "content": content}]
    
    # Using a shorter timeout for Groq
    response = client.chat.completions.create(
        model="llama-3.2-90b-vision-preview",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
        timeout=5.0
    )
    return response.choices[0].message.content

def _try_openrouter(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key: return None
    
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    content = f"Document Text:\n\n{extracted_text}\n\n{prompt}"
    
    # Using a shorter timeout for OpenRouter
    response = client.chat.completions.create(
        model="meta-llama/llama-3.1-8b-instruct",
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
        temperature=0.1,
        timeout=5.0
    )
    return response.choices[0].message.content

def _try_huggingface(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    if not api_key: return None
    
    API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-8B-Instruct"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    payload = {
        "inputs": f"{prompt}\n\nDocument text to analyze:\n{extracted_text}",
        "parameters": {"return_full_text": False, "max_new_tokens": 1000}
    }
    
    # Crucial timeout for requests
    response = requests.post(API_URL, headers=headers, json=payload, timeout=5.0)
    if response.status_code != 200:
        raise Exception(f"HF Error Status {response.status_code}")
    
    raw_text = response.json()[0]['generated_text']
    return raw_text
