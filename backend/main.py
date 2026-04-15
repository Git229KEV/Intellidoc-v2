import os
import sys
import base64
import requests  # ✅ NEW
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
from mangum import Mangum

# Ensure the current directory is in the path for local imports on Vercel
sys.path.append(os.path.dirname(__file__))

# Load environment variables
load_dotenv()

API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

app = FastAPI(
    title="Intelligent Document Processor",
    description="API for extracting and summarizing text from documents.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 API Key verification
def verify_api_key(api_key: str = Security(api_key_header)):
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="API_KEY not set")
    if api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key


# 📥 Request Schema
class DocumentRequest(BaseModel):
    fileName: str
    fileType: str
    fileBase64: str


# 📤 Response Schema
class EntitiesResponse(BaseModel):
    names: list[str] = []
    dates: list[str] = []
    organizations: list[str] = []
    amounts: list[str] = []
    unique_identifiers: list[str] = []
    locations: list[str] = []
    contact_details: list[str] = []


class DocumentResponse(BaseModel):
    status: str
    fileName: str
    summary: str
    entities: EntitiesResponse
    sentiment: str
    confidence_score: float
    error_details: str = ""


# 🔧 Safe entity formatter
def _safe_entities_payload(raw) -> dict:
    keys = (
        "names",
        "dates",
        "organizations",
        "amounts",
        "unique_identifiers",
        "locations",
        "contact_details",
    )
    if not isinstance(raw, dict):
        return {k: [] for k in keys}

    out = {}
    for k in keys:
        v = raw.get(k)
        if isinstance(v, list):
            out[k] = [str(x) for x in v]
        elif v is None:
            out[k] = []
        else:
            out[k] = [str(v)]
    return out


# 🚀 MAIN ENDPOINT
@app.post("/api/document-analyze", response_model=DocumentResponse)
async def analyze_document(request: DocumentRequest, api_key: str = Depends(verify_api_key)):
    try:
        # Lazy imports
        from DocumentParser import parse_document
        from AIProcessor import generate_analysis

        # Decode file
        try:
            file_bytes = base64.b64decode(request.fileBase64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64")

        # File validation
        if len(file_bytes) > 4 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large")

        supported_types = ['pdf', 'docx', 'doc', 'image', 'png', 'jpg', 'jpeg', 'webp']
        if request.fileType.lower() not in supported_types:
            raise HTTPException(status_code=415, detail="Unsupported file type")

        # Extract + AI analysis
        extracted_text = parse_document(request.fileBase64, request.fileType)
        analysis_result = generate_analysis(file_bytes, request.fileType, extracted_text)

        is_success = "error_details" not in analysis_result or not analysis_result["error_details"]

        entities = EntitiesResponse.model_validate(
            _safe_entities_payload(analysis_result.get("entities"))
        )

        # 🔥 -------------------------------
        # 🔗 SEND DATA TO N8N WEBHOOK
        # 🔥 -------------------------------
        try:
            webhook_url = os.getenv("N8N_WEBHOOK_URL")

            if webhook_url:
                full_name = entities.names[0] if entities.names else ""
                name_parts = full_name.strip().split(" ")

                payload = {
                    "surname": name_parts[-1] if len(name_parts) > 1 else "",
                    "givenName": " ".join(name_parts[:-1]) if len(name_parts) > 1 else full_name,
                    "passport": entities.unique_identifiers[0] if entities.unique_identifiers else "",
                    "dob": entities.dates[0] if entities.dates else "",
                    "nationality": entities.locations[0] if entities.locations else "",
                    "raw_entities": entities.model_dump()
                }

                requests.post(webhook_url, json=payload, timeout=5)

        except Exception as e:
            print("⚠️ n8n webhook failed:", str(e))
        # 🔥 -------------------------------

        return DocumentResponse(
            status="success" if is_success else "error",
            fileName=request.fileName,
            summary=analysis_result.get("summary", ""),
            entities=entities,
            sentiment=analysis_result.get("sentiment", "Neutral"),
            confidence_score=float(analysis_result.get("confidence_score", 0.0)),
            error_details=analysis_result.get("error_details", "")
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("CRITICAL ERROR:", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Processing Failed")


# ❤️ Health check
@app.get("/api/health")
def health_check():
    import sys
    return {
        "status": "healthy",
        "python_version": sys.version
    }


@app.get("/")
def root():
    return {"message": "API running 🚀", "version": "2.0.0"}


handler = Mangum(app, lifespan="off")