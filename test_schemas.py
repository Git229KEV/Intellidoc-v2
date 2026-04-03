import os
import sys

# Mock environment
os.environ["GEMINI_API_KEY"] = "mock"
os.environ["GROQ_API_KEY"] = "mock"

try:
    from backend.AIProcessor import generate_analysis, AnalysisSchema, EntitiesSchema
    from backend.main import DocumentResponse, EntitiesResponse
    print("SUCCESS: Both AIProcessor and main models imported.")
    
    # Test model instantiation
    entities = EntitiesSchema(names=["Test"])
    analysis = AnalysisSchema(summary="Test", entities=entities, sentiment="Positive", confidence_score=0.9)
    print("SUCCESS: AIProcessor models validated.")
    
    doc_resp = DocumentResponse(
        status="success", 
        fileName="test.pdf", 
        summary="test", 
        entities=EntitiesResponse(names=["test"]), # Pydantic v2 allows casting
        sentiment="Neutral", 
        confidence_score=0.9,
        error_details=""
    )
    print("SUCCESS: main models validated.")
    
except Exception as e:
    print(f"FAILURE: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
