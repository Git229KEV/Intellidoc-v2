import os
import json
import base64
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from openai import OpenAI

class InsuranceExtractionSchema(BaseModel):
    policy_number: list[str] = Field(default_factory=list, description="Extracted policy numbers")
    insured_name: list[str] = Field(default_factory=list, description="Extracted names of the insured")
    vehicle_number: list[str] = Field(default_factory=list, description="Extracted vehicle registration numbers")
    policy_start_date: list[str] = Field(default_factory=list, description="Extracted policy start dates")
    policy_end_date: list[str] = Field(default_factory=list, description="Extracted policy end dates")
    od_premium: list[str] = Field(default_factory=list, description="Extracted Own Damage (OD) premium amounts")
    tp_premium: list[str] = Field(default_factory=list, description="Extracted Third Party (TP) premium amounts")
    net_premium: list[str] = Field(default_factory=list, description="Extracted net premium amounts")
    gross_premium: list[str] = Field(default_factory=list, description="Extracted gross premium amounts")

class AnalysisSchema(BaseModel):
    summary: str = Field(default="", description="A summary of the document.")
    entities: InsuranceExtractionSchema = Field(default_factory=InsuranceExtractionSchema)
    sentiment: str = Field(default="Neutral")
    confidence_score: float = Field(default=0.0)

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
    
    # For images, if no insurance entities extracted, likely sample data or failed extraction
    image_types = ['png', 'webp', 'jpg', 'jpeg', 'image']
    is_img = any(t in file_type.lower() for t in image_types)
    
    if is_img:
        total_entities = 0
        valid_entities = 0
        for key, values in entities.items():
            if isinstance(values, list):
                total_entities += len(values)
                for v in values:
                    v_str = str(v).lower()
                    if v_str and "not explicitly" not in v_str and "not mentioned" not in v_str and "n/a" not in v_str and "unknown" not in v_str and "not available" not in v_str:
                        valid_entities += 1
        
        if valid_entities == 0:
            print(f"DEBUG: Image analysis returned no valid insurance entities - trying fallback...")
            return True
    
    return False

def generate_analysis(file_bytes: bytes, file_type: str, extracted_text: str = "") -> dict:
    """
    Attempts to analyze the document using multiple AI providers in sequence.
    Priority: Gemini -> Groq Vision -> OpenRouter -> Hugging Face
    """
    
    is_image = file_type.lower().strip() in ['png', 'webp', 'jpg', 'jpeg', 'image']
    
    # Different prompts for insurance document analysis
    if is_image:
        prompt = """
        YOU ARE A PROFESSIONAL INSURANCE DOCUMENT ANALYZER. YOU MUST ANALYZE THE ACTUAL IMAGE PROVIDED.
        
        CRITICAL INSTRUCTIONS:
        1. LOOK AT THE IMAGE CAREFULLY - You MUST perform OCR/text recognition on the visual content
        2. READ ALL TEXT VISIBLE - Extract specific insurance policy details
        3. DO NOT generate sample data - ONLY report what you see in the image
        4. IF IMAGE IS BLANK OR UNREADABLE - Return empty arrays, NOT sample data
        
        MANDATORY EXTRACTION REQUIREMENTS:
        1. POLICY NUMBER: The unique identifier for the policy
        2. INSURED NAME: The name of the person or entity insured
        3. VEHICLE NUMBER: The registration number of the vehicle (e.g., TN01AB1234)
        4. POLICY START DATE: When the coverage begins
        5. POLICY END DATE: When the coverage ends
        6. OD: Own Damage premium amount
        7. TP: Third Party premium amount
        8. NET PREMIUM: The net premium amount
        9. GROSS PREMIUM: The total gross premium amount
        
        CRITICAL: 
        - If you cannot read the image clearly, return empty results
        - Do NOT hallucinate or invent data
        - Only extract what is VISUALLY present in the image
        
        Return ONLY valid JSON in this exact format. 
        CRITICAL: If a field is not found in the image, return an EMPTY LIST []. 
        DO NOT use strings like "not mentioned", "not explicitly mentioned", "n/a", "unknown", "none", "...", "null", or "not available" in the lists.
        
        {
          "summary": "Brief description of the insurance document",
          "entities": {
            "policy_number": [],
            "insured_name": [],
            "vehicle_number": [],
            "policy_start_date": [],
            "policy_end_date": [],
            "od_premium": [],
            "tp_premium": [],
            "net_premium": [],
            "gross_premium": []
          },
          "sentiment": "Neutral",
          "confidence_score": 0.95
        }
        """
    else:
        prompt = """
        CRITICAL: You are an expert insurance document analysis agent. 
        Analyze the provided document and extract the following insurance fields with 100% precision.
        
        EXTRACT ALL OF THE FOLLOWING:
        1. Policy Number
        2. Insured Name
        3. Vehicle Number
        4. Policy Start Date
        5. Policy End Date
        6. OD (Own Damage Premium)
        7. TP (Third Party Premium)
        8. Net Premium
        9. Gross Premium

        Return result in STRICT JSON format.
        CRITICAL: If a field is not found, return an EMPTY LIST []. 
        DO NOT use strings like "Not mentioned" or "N/A" in the lists.
        {
          "summary": "...",
          "entities": {
            "policy_number": [],
            "insured_name": [],
            "vehicle_number": [],
            "policy_start_date": [],
            "policy_end_date": [],
            "od_premium": [],
            "tp_premium": [],
            "net_premium": [],
            "gross_premium": []
          },
          "sentiment": "...",
          "confidence_score": 0.95
        }
        """

    image_types = ['png', 'webp', 'jpg', 'jpeg', 'image']
    is_image = any(t in file_type.lower() for t in image_types)
    is_pdf = 'pdf' in file_type.lower()
    
    # Extract first page as image for all PDFs to ensure vision models can see embedded images/scans
    pdf_vision_image_bytes = None
    if is_pdf:
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if len(doc) > 0:
                print(f"DEBUG: Extracting PDF page 1 for vision analysis...")
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                pdf_vision_image_bytes = pix.tobytes("png")
            doc.close()
        except Exception as e:
            print(f"DEBUG: Failed to extract first page image from PDF: {e}")

    # Determine provider priority based on file type
    if is_image or pdf_vision_image_bytes:
        providers = [
            ("Gemini", _try_gemini), # Gemini is best for multi-page PDFs
            ("Groq", _try_groq),      # Groq is best for fast vision fallback
            ("OpenRouter", _try_openrouter),
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
            # Gemini has native PDF support - ALWAYS give it the original file for full context
            if name == "Gemini":
                target_bytes = file_bytes
                target_type = file_type
            else:
                # Groq and others need the extracted image for PDFs
                target_bytes = pdf_vision_image_bytes if (pdf_vision_image_bytes and name == "Groq" and is_pdf) else file_bytes
                target_type = "image/png" if (pdf_vision_image_bytes and name == "Groq" and is_pdf) else file_type
            
            raw_result = func(target_bytes, target_type, extracted_text, prompt)
            
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
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image', 'image/png', 'image/jpeg', 'image/webp']:
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
        # Increased timeout for Gemini (experiencing high load periods, 503 errors)
        # Minimum is 10s, using 15s to handle demand spikes
        print("DEBUG: Sending request to Gemini...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalysisSchema,
                temperature=0.1,
                http_options={'timeout': 15000} # 15 seconds - handle high demand
            ),
        )
        result = response.text
        print("DEBUG: Gemini response received successfully")
        # The new SDK response.text is already clean JSON if response_schema is used,
        # but we handle it via the main loop's cleaning just in case.
        return result
    except Exception as e:
        error_str = str(e)
        if '503' in error_str or 'UNAVAILABLE' in error_str:
            print(f"DEBUG: Gemini experiencing high load (503): {error_str}")
        else:
            print(f"DEBUG: Gemini error: {error_str}")
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
    if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image', 'image/png', 'image/jpeg', 'image/webp']:
        print(f"DEBUG: Groq processing image - file_type: {file_type}, size: {len(file_bytes)} bytes")
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        print(f"DEBUG: Image encoded to base64, length: {len(base64_image)}")
        
        # Map back to standard jpeg/png for data URL
        mime_url = "image/jpeg"
        if file_type == 'png': mime_url = "image/png"
        
        messages = [
            {"role": "system", "content": "You are a professional insurance data extraction agent. You must extract policy details with 100% accuracy from the provided visual data."},
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
        messages = [
            {"role": "system", "content": "You are a professional insurance data extraction agent. You must extract policy details with 100% accuracy from the provided visual or text data."},
            {
                "role": "user",
                "content": content
            }
        ]
    
    try:
        print("DEBUG: Sending request to Groq...")
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0, # Zero temperature for precision
            timeout=15.0  # Increased timeout
        )
        result = response.choices[0].message.content
        print("DEBUG: Groq response received successfully")
        return result
    except Exception as e:
        print(f"DEBUG: Groq error: {str(e)}")
        raise

def _try_openrouter(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("DEBUG: OPENROUTER_API_KEY not set")
        return None
    
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        file_type = file_type.lower().strip()
        
        messages = []
        # Try vision support for OpenRouter as fallback
        if file_type in ['png', 'webp', 'jpg', 'jpeg', 'image']:
            print("DEBUG: OpenRouter processing image as fallback...")
            base64_image = base64.b64encode(file_bytes).decode('utf-8')
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
        
        print("DEBUG: Sending request to OpenRouter...")
        # Using a longer timeout for OpenRouter
        response = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=8.0
        )
        result = response.choices[0].message.content
        print("DEBUG: OpenRouter response received successfully")
        return result
    except Exception as e:
        print(f"DEBUG: OpenRouter error: {str(e)}")
        raise

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
