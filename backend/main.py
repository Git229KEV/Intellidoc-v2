import os
import base64
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from DocumentParser import parse_document
from AIProcessor import generate_analysis

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
    names: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    unique_identifiers: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    contact_details: list[str] = Field(default_factory=list)

class DocumentResponse(BaseModel):
    status: str
    fileName: str
    summary: str
    entities: EntitiesResponse
    sentiment: str
    confidence_score: float = Field(..., description="Neural synthesis confidence")
    error_details: str = Field(default="", description="Detailed error logs for fallback debugging")

@app.post("/api/document-analyze", response_model=DocumentResponse)
async def analyze_document(request: DocumentRequest, api_key: str = Depends(verify_api_key)):
    try:
        # Decode the file once
        try:
            file_bytes = base64.b64decode(request.fileBase64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64 string")

        # Extract text locally for all file types to ensure fallback providers
        extracted_text = parse_document(request.fileBase64, request.fileType)
        
        # Call LLM API with diagnostic feedback
        analysis_result = generate_analysis(file_bytes, request.fileType, extracted_text)
        
        # Assemble Response
        # if generate_analysis returns a status error (fallback failed), we handle it via DocumentResponse
        is_success = "error_details" not in analysis_result or not analysis_result["error_details"]
        
        return DocumentResponse(
            status="success" if is_success else "error",
            fileName=request.fileName,
            summary=analysis_result.get("summary", "Analysis failed."),
            entities=EntitiesResponse(**analysis_result.get("entities", {})),
            sentiment=analysis_result.get("sentiment", "Neutral"),
            confidence_score=float(analysis_result.get("confidence_score", 0.0)),
            error_details=analysis_result.get("error_details", "")
        )
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"CRITICAL SYSTEM ERROR: {error_trace}")
        
        return DocumentResponse(
            status="error",
            fileName=request.fileName,
            summary="A critical system error occurred during analysis.",
            entities=EntitiesResponse(),
            sentiment="Neutral",
            confidence_score=0.0,
            error_details=f"System Crash: {str(e)}"
        )

from mangum import Mangum
handler = Mangum(app)

@app.get("/")
def read_root():
    return {"message": "Intelligent Document Processor is active.", "version": "1.1.0"}
