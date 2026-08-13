import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

# Import our schema (the blueprint) from schemas.py
from src.schemas import AnalyzeRequest 

from src.agent2_graph import agent2_app
# Make sure StockNews is imported here!
from src.database import SessionLocal, AIAnalysis, StockNews

logger = logging.getLogger(__name__)

router = APIRouter()

# OPTIMIZATION 1: Dependency Injection for the Database
# This automatically opens and closes database sessions safely for every route
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/health")
def health_check():
    return {"status": "healthy"}

@router.post("/analyze")
async def analyze_stock(request: AnalyzeRequest, db: Session = Depends(get_db)): # <--- Async & DB Injection
    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY in .env")
        
    try:
        inputs = {"ticker": request.ticker.upper()}
        logger.info(f"Received request to analyze {inputs['ticker']}")
        
        # OPTIMIZATION 3: Run the AI in a background thread so it doesn't freeze the API!
        result = await run_in_threadpool(agent2_app.invoke, inputs)
        final_json = result.get("final_analysis_json", {})
        
        # Extract the headlines list from the AI's output (default to empty list if missing)
        top_headlines = final_json.get("top_headlines", [])
        
        # --- Upsert AI Analysis ---
        existing_analysis = db.query(AIAnalysis).filter(AIAnalysis.ticker == inputs["ticker"]).first()
        if existing_analysis:
            existing_analysis.analysis_data = final_json
            existing_analysis.created_at = datetime.now(timezone.utc)
            logger.info(f"Updated existing AI analysis for {inputs['ticker']}")
        else:
            db.add(AIAnalysis(ticker=inputs["ticker"], analysis_data=final_json))
            logger.info(f"Created new AI analysis for {inputs['ticker']}")
            
        # --- Upsert Stock News ---
        existing_news = db.query(StockNews).filter(StockNews.ticker == inputs["ticker"]).first()
        if existing_news:
            existing_news.headlines = top_headlines
            existing_news.created_at = datetime.now(timezone.utc)
            logger.info(f"Updated existing news for {inputs['ticker']}")
        else:
            db.add(StockNews(ticker=inputs["ticker"], headlines=top_headlines))
            logger.info(f"Created new news record for {inputs['ticker']}")
            
        # Commit all changes to the database at once
        db.commit()
        
        # 3. Return the JSON to the user
        return final_json
        
    except Exception as e:
        logger.error(f"Agent workflow failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{ticker}")
async def get_stock_history(ticker: str, db: Session = Depends(get_db)): # <--- Async & DB Injection
    """Retrieves all historical AI analyses for a specific stock ticker."""
    try:
        # Search the database for this ticker, ordering by newest first
        history = db.query(AIAnalysis).filter(
            AIAnalysis.ticker == ticker.upper()
        ).order_by(AIAnalysis.created_at.desc()).all()
        
        if not history:
            return {"message": f"No historical data found for {ticker.upper()}", "data": []}
            
        # Package the database rows into a clean JSON list
        results = []
        for record in history:
            results.append({
                "id": record.id,
                "ticker": record.ticker,
                "created_at": record.created_at,
                "analysis_data": record.analysis_data
            })
            
        return {"data": results}
        
    except Exception as e:
        logger.error(f"Failed to fetch history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/news/{ticker}")
async def get_stock_news(ticker: str, db: Session = Depends(get_db)): # <--- Async & DB Injection
    """Retrieves only the news headlines for a specific stock."""
    try:
        news_record = db.query(StockNews).filter(StockNews.ticker == ticker.upper()).first()
        
        if not news_record:
            return {"message": f"No news found for {ticker.upper()}", "headlines": []}
            
        return {
            "ticker": news_record.ticker, 
            "headlines": news_record.headlines, 
            "last_updated": news_record.created_at
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch news: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))