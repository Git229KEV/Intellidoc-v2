import os
import sys
import base64
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
    description="API for extracting and summarizing text from multi-format documents.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication Dependency
def verify_api_key(api_key: str = Security(api_key_header)):
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        raise HTTPException(
            status_code=500, detail="Server configuration error: API_KEY not set"
        )
    if api_key != expected_api_key:
        raise HTTPException(
            status_code=401, detail="Invalid API Key"
        )
    return api_key

class DocumentRequest(BaseModel):
    fileName: str = Field(..., description="Name of the uploaded file")
    fileType: str = Field(..., description="Detected MIME type or extension")
    fileBase64: str = Field(..., description="Base64 encoded content")

class EntitiesResponse(BaseModel):
    policy_number: list[str] = Field(default_factory=list)
    insured_name: list[str] = Field(default_factory=list)
    vehicle_number: list[str] = Field(default_factory=list)
    policy_start_date: list[str] = Field(default_factory=list)
    policy_end_date: list[str] = Field(default_factory=list)
    od_premium: list[str] = Field(default_factory=list)
    tp_premium: list[str] = Field(default_factory=list)
    net_premium: list[str] = Field(default_factory=list)
    gross_premium: list[str] = Field(default_factory=list)

class DocumentResponse(BaseModel):
    policy_number: str = ""
    name: str = ""
    vehicle_no: str = ""
    policy_start_date: str = ""
    policy_end_date: str = ""
    od: str = ""
    tp: str = ""
    net_premium: str = ""
    gross_premium: str = ""
    premium: str = ""
    status: str
    error_details: str = ""


def _safe_entities_payload(raw) -> dict:
    """Coerce AI output into a dict Pydantic can validate and filter placeholders."""
    keys = (
        "policy_number",
        "insured_name",
        "vehicle_number",
        "policy_start_date",
        "policy_end_date",
        "od_premium",
        "tp_premium",
        "net_premium",
        "gross_premium",
    )
    if not isinstance(raw, dict):
        return {k: [] for k in keys}
    
    placeholders = ["not explicitly mentioned", "n/a", "unknown", "none", "...", "null"]
    out = {}
    for k in keys:
        v = raw.get(k)
        if isinstance(v, list):
            # Filter out placeholder values
            out[k] = [str(x) for x in v if str(x).lower() not in placeholders]
        elif v is None:
            out[k] = []
        else:
            v_str = str(v)
            if v_str.lower() in placeholders:
                out[k] = []
            else:
                out[k] = [v_str]
    return out


@app.post("/api/document-analyze", response_model=DocumentResponse)
async def analyze_document(request: DocumentRequest, api_key: str = Depends(verify_api_key)):
    try:
        # Lazy imports to prevent top-level invocation failures on Vercel
        try:
            from DocumentParser import parse_document
            from AIProcessor import generate_analysis
        except ImportError as ie:
            raise HTTPException(status_code=500, detail=f"Module Import Error: {str(ie)}")

        # Decode the file once
        try:
            file_bytes = base64.b64decode(request.fileBase64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64 string")

        # File size validation (4MB limit for Vercel)
        max_size = 4 * 1024 * 1024
        if len(file_bytes) > max_size:
            raise HTTPException(status_code=413, detail="File too large")

        # File type validation
        supported_types = ['pdf', 'docx', 'doc', 'image', 'png', 'jpg', 'jpeg', 'webp']
        file_type_lower = request.fileType.lower().strip()
        if file_type_lower not in supported_types:
            raise HTTPException(status_code=415, detail="Unsupported file type")

        # Extract text locally for all file types to ensure fallback providers
        extracted_text = parse_document(request.fileBase64, request.fileType)
        
        # Call LLM API with diagnostic feedback
        analysis_result = generate_analysis(file_bytes, request.fileType, extracted_text)
        
        # Assemble Response
        # if generate_analysis returns a status error (fallback failed), we handle it via DocumentResponse
        is_success = "error_details" not in analysis_result or not analysis_result["error_details"]

        try:
            entities = EntitiesResponse.model_validate(
                _safe_entities_payload(analysis_result.get("entities"))
            )
            
            # Map to flat response requested by user
            return DocumentResponse(
                status="success" if is_success else "error",
                policy_number=entities.policy_number[0] if entities.policy_number else "",
                name=entities.insured_name[0] if entities.insured_name else "",
                vehicle_no=entities.vehicle_number[0] if entities.vehicle_number else "",
                policy_start_date=entities.policy_start_date[0] if entities.policy_start_date else "",
                policy_end_date=entities.policy_end_date[0] if entities.policy_end_date else "",
                od=entities.od_premium[0] if entities.od_premium else "",
                tp=entities.tp_premium[0] if entities.tp_premium else "",
                net_premium=entities.net_premium[0] if entities.net_premium else "",
                gross_premium=entities.gross_premium[0] if entities.gross_premium else "",
                premium=entities.gross_premium[0] if entities.gross_premium else "", # Alias for example compatibility
                error_details=analysis_result.get("error_details", "")
            )
        except ValidationError as ve:
            raise HTTPException(
                status_code=500,
                detail=f"Response validation failed: {ve}",
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"CRITICAL SYSTEM ERROR: {error_trace}")

        # Determine error type for user-friendly message
        error_msg = str(e)
        if 'size' in error_msg.lower() or len(error_msg) > 4*1024*1024:
            detail = "File too large"
        elif 'type' in error_msg.lower() or 'format' in error_msg.lower():
            detail = "Unsupported file type"
        else:
            detail = "Processing Failed"
        
        raise HTTPException(status_code=500, detail=detail)

# Health check for Vercel deployment status
@app.get("/api/health")
def health_check():
    import sys
    return {
        "status": "healthy",
        "python_version": sys.version,
        "active_providers": ["Gemini", "Groq", "OpenRouter", "HuggingFace"]
    }

@app.get("/")
def read_root():
    return {"message": "Intelligent Document Processor is active.", "version": "1.1.0"}


handler = Mangum(app, lifespan="off")
