import os
import json
import base64
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from openai import OpenAI

class InsuranceExtractionSchema(BaseModel):
    policy_number: list[str] = Field(default_factory=list)
    insured_name: list[str] = Field(default_factory=list)
    vehicle_number: list[str] = Field(default_factory=list)
    policy_start_date: list[str] = Field(default_factory=list)
    policy_end_date: list[str] = Field(default_factory=list)
    od_premium: list[str] = Field(default_factory=list)
    tp_premium: list[str] = Field(default_factory=list)
    net_premium: list[str] = Field(default_factory=list)
    gross_premium: list[str] = Field(default_factory=list)

class AnalysisSchema(BaseModel):
    summary: str = ""
    entities: InsuranceExtractionSchema = Field(default_factory=InsuranceExtractionSchema)
    sentiment: str = "Neutral"
    confidence_score: float = 0.0


def clean_json_response(raw_text: str) -> dict:
    text = raw_text.strip().replace('```json', '').replace('```', '').strip()
    if not (text.startswith('{') and text.endswith('}')):
        s = text.find('{'); e = text.rfind('}') + 1
        if s != -1 and e > 0:
            text = text[s:e]
    return json.loads(text)


def generate_analysis(file_bytes: bytes, file_type: str, extracted_text: str = "") -> dict:
    image_types = ['png', 'webp', 'jpg', 'jpeg', 'image']
    is_image = any(t in file_type.lower() for t in image_types)

    prompt = '''You are an expert insurance policy analyzer. Extract:
Policy Number, Insured Name, Vehicle Number, Policy Start Date, Policy End Date,
OD Premium, TP Premium, Net Premium, Gross Premium.
Use only document content. If not found return empty arrays.
Return strict JSON with summary, entities, sentiment, confidence_score.
If PDF contains scanned pages, perform OCR on visible content before extracting fields.'''

    # Native PDF approach only: no PDF-to-image conversion
    providers = [
        ("Gemini", lambda b, t, e, p: _try_gemini(b, t, e, p, 'gemini-2.5-flash')),
        ("Gemini-Pro", lambda b, t, e, p: _try_gemini(b, t, e, p, 'gemini-3.1-pro-preview')),
        ("Groq", _try_groq),
        ("OpenRouter", _try_openrouter),
        ("HuggingFace", _try_huggingface),
    ]

    errors = []
    for name, func in providers:
        try:
            raw = func(file_bytes, file_type, extracted_text, prompt)
            if not raw:
                continue
            data = raw if isinstance(raw, dict) else clean_json_response(str(raw))
            return AnalysisSchema.model_validate(data).model_dump()
        except Exception as e:
            errors.append(f'{name}: {e}')

    return {
        'summary': 'All providers failed',
        'entities': InsuranceExtractionSchema().model_dump(),
        'sentiment': 'Neutral',
        'confidence_score': 0.0,
        'error_details': '; '.join(errors)
    }


def _try_gemini(file_bytes, file_type, extracted_text, prompt, model_name='gemini-2.5-flash'):
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    ft = file_type.lower()

    if any(x in ft for x in ['png', 'jpg', 'jpeg', 'webp', 'image']):
        mime = 'image/png' if 'png' in ft else 'image/webp' if 'webp' in ft else 'image/jpeg'
        contents = [types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt]
    elif 'pdf' in ft:
        # Native PDF upload to Gemini
        contents = [types.Part.from_bytes(data=file_bytes, mime_type='application/pdf'), prompt]
    else:
        contents = [f'Document Text:\n{extracted_text}\n\n{prompt}']

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=AnalysisSchema,
            temperature=0.1,
        )
    )
    return response.text


def _try_groq(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        return None
    client = OpenAI(base_url='https://api.groq.com/openai/v1', api_key=api_key)
    content = f'{prompt}\n\nDocument Text:\n{extracted_text}'
    r = client.chat.completions.create(
        model='meta-llama/llama-4-scout-17b-16e-instruct',
        messages=[{'role':'user','content':content}],
        response_format={'type':'json_object'},
        temperature=0
    )
    return r.choices[0].message.content


def _try_openrouter(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        return None
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=api_key)
    r = client.chat.completions.create(
        model='meta-llama/llama-3.1-8b-instruct',
        messages=[{'role':'user','content':f'{prompt}\n\n{extracted_text}'}],
        response_format={'type':'json_object'}
    )
    return r.choices[0].message.content


def _try_huggingface(file_bytes, file_type, extracted_text, prompt):
    api_key = os.getenv('HUGGINGFACE_API_KEY')
    if not api_key:
        return None
    headers = {'Authorization': f'Bearer {api_key}'}
    payload = {'inputs': f'{prompt}\n\n{extracted_text}'}
    r = requests.post('https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-8B-Instruct', headers=headers, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()[0]['generated_text']
