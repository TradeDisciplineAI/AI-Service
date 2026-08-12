import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load keys before anything else
load_dotenv()

from src.agent2_graph import agent2_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent 2: News & Sentiment API")

# Request model for the API
class AnalyzeRequest(BaseModel):
    ticker: str

@app.get("/health")
def health_check():
    """Used by Docker to ensure the container is alive."""
    return {"status": "healthy"}

@app.post("/analyze")
def analyze_stock(request: AnalyzeRequest):
    """Agent 3 will send a POST request here to trigger Agent 2."""
    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY in .env")
        
    try:
        inputs = {"ticker": request.ticker.upper()}
        logger.info(f"Received request to analyze {inputs['ticker']}")
        
        result = agent2_app.invoke(inputs)
        return result.get("final_analysis_json")
        
    except Exception as e:
        logger.error(f"Agent workflow failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))