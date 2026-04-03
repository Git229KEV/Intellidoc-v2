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

def is_sample_data(response_dict: dict, file_type: str) -> bool:
    """
    Detects if the response is sample/default data rather than actual analysis.
    """
    summary = response_dict.get("summary", "").lower()
    entities = response_dict.get("entities", {})
    
    # Known sample data indicators
    sample_indicators = [
        "techcorp", "receipt", "sample", "example", "dummy",
        "january 12", "1234", "test document", "example data",
        "purchase made", "rcpt-001", "555-1234"
    ]
    
    for indicator in sample_indicators:
        if indicator in summary:
            print(f"DEBUG: Detected sample data indicator: '{indicator}'")
            return True
    
    # For images, if no entities extracted, likely sample data
    if file_type.lower().strip() in ['png', 'webp', 'jpg', 'jpeg', 'image']:
        total_entities = sum([
            len(entities.get("names", [])),
            len(entities.get("dates", [])),
            len(entities.get("organizations", [])),
            len(entities.get("locations", [])),
            len(entities.get("contact_details", [])),
            len(entities.get("unique_identifiers", [])),
            len(entities.get("amounts", [])),
        ])
        if total_entities == 0:
            print(f"DEBUG: Image analysis returned no entities - likely sample/empty")
            return True
    
    return False

def generate_analysis(file_bytes: bytes, file_type: str, extracted_text: str = "") -> dict:
    """
    Attempts to analyze the document using multiple AI providers in sequence.
    Priority: Gemini -> Groq Vision -> OpenRouter -> Hugging Face
    """
    
    is_image = file_type.lower().strip() in ['png', 'webp', 'jpg', 'jpeg', 'image']
    
    # Different prompts for images vs text
    if is_image:
        prompt = """
        YOU ARE A PROFESSIONAL DOCUMENT ANALYZER. YOU MUST ANALYZE THE ACTUAL IMAGE PROVIDED.
        
        CRITICAL INSTRUCTIONS:
        1. LOOK AT THE IMAGE CAREFULLY - You MUST perform OCR/text recognition on the visual content
        2. READ ALL TEXT VISIBLE - Extract every word, name, date, number, and identifiable information
        3. DO NOT generate sample data - ONLY report what you see in the image
        4. IF IMAGE IS BLANK OR UNREADABLE - Return empty arrays, NOT sample data
        
        MANDATORY EXTRACTION REQUIREMENTS:
        1. ALL NAMES visible in the image (people, companies, organizations)
        2. ALL DATES visible (any date format)
        3. ALL ORGANIZATIONS/COMPANIES mentioned
        4. ALL MONETARY AMOUNTS or prices
        5. ALL UNIQUE IDENTIFIERS (ID numbers, invoice numbers, receipt numbers, reference codes)
        6. ALL LOCATIONS/ADDRESSES visible
        7. ALL CONTACT DETAILS (phone numbers, emails, websites)
        8. SENTIMENT of the document (Positive, Negative, or Neutral tone)
        9. SUMMARY: 1-2 sentences describing what this document/image shows
        
        CRITICAL: 
        - If you cannot read the image clearly, return empty results
        - Do NOT hallucinate or invent data
        - Do NOT use sample data like "TechCorp" or "receipt example"
        - Only extract what is VISUALLY present in the image
        
        Return ONLY valid JSON in this exact format:
        {
          "summary": "Brief description of what the image shows (empty if unreadable)",
          "entities": {
            "names": ["exact names from image"],
            "dates": ["all visible dates"],
            "organizations": ["companies/orgs mentioned"],
            "amounts": ["monetary values if any"],
            "unique_identifiers": ["ID numbers, codes"],
            "locations": ["addresses and places"],
            "contact_details": ["phones, emails, websites"]
          },
          "sentiment": "Positive/Negative/Neutral",
          "confidence_score": 0.95
        }
        """
    else:
        prompt = """
        CRITICAL: You are an expert document analysis agent. 
        Analyze the provided document with 100% precision.
        
        EXTRACT ALL OF THE FOLLOWING:
        1. Names, Dates, Organizations, Monetary Amounts
        2. UNIQUE IDENTIFIERS: Extract EVERY ID, Invoice Number, Receipt ID, etc.
        3. LOCATIONS & CONTACTS: Extract full addresses, phone numbers, and emails
        4. SENTIMENT: Determine if the document tone is Positive, Negative, or Neutral
        5. SUMMARY: 1-2 sentence high-level synthesis of what this document is

        Return result in STRICT JSON format:
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
    
    # Determine provider priority based on file type
    # For images, ONLY use vision-capable providers (Groq and Gemini)
    # OpenRouter and HuggingFace cannot process images and will return sample data
    
    if is_image:
        providers = [
            ("Groq", _try_groq),
            ("Gemini", _try_gemini),
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
                
                # Check for sample data
                if is_sample_data(json_data, file_type):
                    print(f"DEBUG: {name} returned sample data, trying next provider...")
                    errors.append(f"{name} returned sample/default data")
                    continue
                
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
    if not api_key:
        print("DEBUG: GEMINI_API_KEY not set")
        return None
    
    client = genai.Client(api_key=api_key)
    file_type = file_type.lower().strip()
    
    contents = []
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image']:
        print(f"DEBUG: Gemini processing image - file_type: {file_type}, size: {len(file_bytes)} bytes")
        # Ensure common image formats are consistent
        mime = "image/jpeg"
        if file_type == 'png': mime = "image/png"
        elif file_type == 'webp': mime = "image/webp"
        contents = [types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt]
        print(f"DEBUG: Gemini image prepared with mime: {mime}")
    elif file_type == 'pdf':
        print(f"DEBUG: Gemini processing PDF - size: {len(file_bytes)} bytes")
        contents = [types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"), prompt]
    else:
        contents = [f"Document Text:\n\n{extracted_text}\n\n{prompt}"]
    
    try:
        # Set a strict 7s timeout for Gemini in serverless environment
        print("DEBUG: Sending request to Gemini...")
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
        result = response.text
        print("DEBUG: Gemini response received successfully")
        # The new SDK response.text is already clean JSON if response_schema is used,
        # but we handle it via the main loop's cleaning just in case.
        return result
    except Exception as e:
        print(f"DEBUG: Gemini error: {str(e)}")
        raise

def _try_groq(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: 
        print("DEBUG: GROQ_API_KEY not set")
        return None
    
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
    file_type = file_type.lower().strip()

    messages = []
    # Vision Support for Groq
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image']:
        print(f"DEBUG: Groq processing image - file_type: {file_type}, size: {len(file_bytes)} bytes")
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        print(f"DEBUG: Image encoded to base64, length: {len(base64_image)}")
        
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
        print("DEBUG: Groq vision message prepared")
    else:
        content = f"Document Text:\n\n{extracted_text}\n\n{prompt}"
        messages = [{"role": "user", "content": content}]
    
    try:
        # Using a shorter timeout for Groq
        print("DEBUG: Sending request to Groq...")
        response = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=10.0  # Increased timeout for image processing
        )
        result = response.choices[0].message.content
        print("DEBUG: Groq response received successfully")
        return result
    except Exception as e:
        print(f"DEBUG: Groq error: {str(e)}")
        raise

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
