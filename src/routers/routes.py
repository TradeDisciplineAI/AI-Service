import os
import logging
import json
import concurrent.futures
import time
from datetime import datetime, timezone
from typing import Dict, Tuple, Any

SCAN_CACHE: Dict[str, Tuple[float, Any]] = {}
ANALYZE_CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.agent1_graph import agent1_app
# Import our schema (the blueprint) from schemas.py
from src.schemas import AnalyzeRequest, BatchAnalyzeRequest

from src.agent2_graph import agent2_app
from src.tools.yfinance_tool import fetch_market_data
from src.tools.news_api_tool import fetch_financial_news
from src.tools.reddit_tool import fetch_reddit_sentiment
from src.tools.twitter_tool import fetch_twitter_sentiment
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Import our database connection and tables
from src.database import SessionLocal, AIAnalysis, StockNews, MarketSignals
logger = logging.getLogger(__name__)

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/health")
def health_check():
    return {"status": "healthy"}

@router.get("/ai-usage")
async def get_ai_usage(db: Session = Depends(get_db)):
    """Counts how many AI API calls were successfully made today based on database records."""
    today = datetime.now(timezone.utc).date()
    
    try:
        # Count news AI analyses done today
        news_count = db.query(AIAnalysis).filter(
            func.date(AIAnalysis.created_at) == today
        ).count()
        
        # Count market signals generated today
        market_count = db.query(MarketSignals).filter(
            func.date(MarketSignals.updated_at) == today
        ).count()
        
        total_calls = news_count + market_count
        
        return {
            "date": str(today),
            "news_analyses_today": news_count,
            "market_scans_today": market_count,
            "total_successful_ai_calls": total_calls,
            "estimated_free_tier_remaining": max(0, 20 - total_calls),
            "message": "Note: This only counts successful API calls that saved to the database. Failed calls due to rate limits are not counted."
        }
    except Exception as e:
        logger.error(f"Error checking AI usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to check AI usage")



@router.post("/scan-batch")
async def scan_market_batch(request: BatchAnalyzeRequest, db: Session = Depends(get_db)): 
    try:
        tickers = [t.upper() for t in request.tickers]
        logger.info(f"Received batch request for Agent 1 to scan {len(tickers)} tickers")
        
        cache_key = ",".join(sorted(tickers))
        if cache_key in SCAN_CACHE:
            expiry, cached_res = SCAN_CACHE[cache_key]
            if time.time() < expiry:
                logger.info(f"Returning cached /scan-batch for {len(tickers)} tickers")
                return cached_res
        
        # 1. Gather all market data concurrently
        market_data_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {executor.submit(fetch_market_data, ticker): ticker for ticker in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    market_data_map[ticker] = future.result()
                except Exception as e:
                    logger.error(f"Error fetching data for {ticker}: {e}")
                    market_data_map[ticker] = {"error": str(e)}

        # 2. Prepare the massive context string
        combined_text = ""
        valid_tickers = []
        for ticker, data in market_data_map.items():
            if "error" not in data:
                valid_tickers.append(ticker)
                combined_text += f"\n[{ticker}]\n{data.get('text_for_ai', '')}\n"

        if not valid_tickers:
            return {"status": "error", "message": "Failed to fetch market data for any tickers."}

        # 3. Call AI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1, max_retries=0)
        system_prompt = f"""You are Agent 1, the Market Scanner.
        Analyze this 5-minute intraday price action and volume for the following stocks: {valid_tickers}.
        1. Determine if each stock is experiencing a 'Breakout', a 'Reversal', or 'Consolidating'.
        2. Identify if there is a massive surge in Volume.
        3. Estimate the nearest Key Support and Resistance price levels.
        
        [RECENT CANDLES]
        {combined_text}
        """
        
        schema_prompt = """
        Return ONLY a valid JSON object matching this exact format, where the keys are the stock tickers:
        {
            "AAPL": {
                "breakout_detected": true,
                "volume_surge": true,
                "reversal_detected": false,
                "trend_direction": "UP",
                "key_support_level": 150.00,
                "key_resistance_level": 155.00,
                "summary": "Short explanation."
            }
        }
        """
        
        response = None
        for attempt in range(6):
            try:
                response = await run_in_threadpool(
                    llm.invoke, 
                    [HumanMessage(content=system_prompt), HumanMessage(content=schema_prompt)]
                )
                break
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(f"Agent 1 Batch: Google Rate Limit hit! Waiting 65s (Attempt {attempt+1}/6)...")
                    await run_in_threadpool(time.sleep, 65)
                    if attempt == 5:
                        raise e
                else:
                    raise e
                    
        content = response.content
        if isinstance(content, list):
            content = "".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
        
        raw_text = str(content).strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        try:
            ai_json = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Failed to parse Agent 1 Batch JSON: {e}")
            ai_json = {}
        
        # 4. Upsert into database
        saved_count = 0
        for ticker in valid_tickers:
            t_data = ai_json.get(ticker, {})
            market_dict = market_data_map[ticker]
            
            final_dict = {
                "symbol": market_dict.get("symbol", ticker),
                "exchange": "NSE" if ticker.endswith(".NS") or ticker.endswith(".BO") else "NASDAQ",
                "current_price": market_dict.get("current_price", 0.0),
                "timestamp": market_dict.get("timestamp", ""),
                "breakout_detected": t_data.get("breakout_detected", False),
                "volume_surge": t_data.get("volume_surge", False),
                "reversal_detected": t_data.get("reversal_detected", False),
                "trend_direction": t_data.get("trend_direction", "UNKNOWN"),
                "key_support_level": t_data.get("key_support_level", 0.0),
                "key_resistance_level": t_data.get("key_resistance_level", 0.0),
                "summary": t_data.get("summary", ""),
                "ohlcv_candles": market_dict.get("ohlcv_candles", [])
            }
            
            existing_signal = db.query(MarketSignals).filter(MarketSignals.ticker == ticker).first()
            if existing_signal:
                existing_signal.scan_data = final_dict
            else:
                db.add(MarketSignals(ticker=ticker, scan_data=final_dict))
            saved_count += 1
            
        db.commit()
        response_dict = {"status": "success", "message": f"Saved {saved_count} tickers to database!"}
        SCAN_CACHE[cache_key] = (time.time() + CACHE_TTL, response_dict)
        return response_dict
        
    except Exception as e:
        logger.error(f"Error in /scan-batch endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))







@router.post("/analyze-batch")
async def analyze_stock_batch(request: BatchAnalyzeRequest, db: Session = Depends(get_db)): 
    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY in .env")
        
    try:
        tickers = [t.upper() for t in request.tickers]
        logger.info(f"Received batch request to analyze {len(tickers)} tickers")
        
        cache_key = ",".join(sorted(tickers))
        if cache_key in ANALYZE_CACHE:
            expiry, cached_res = ANALYZE_CACHE[cache_key]
            if time.time() < expiry:
                logger.info(f"Returning cached /analyze-batch for {len(tickers)} tickers")
                return cached_res
        
        # 1. Gather all news data concurrently
        news_data_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            def fetch_all(ticker):
                return {
                    "news": fetch_financial_news(ticker),
                    "reddit": fetch_reddit_sentiment(ticker),
                    "twitter": fetch_twitter_sentiment(ticker)
                }
            
            future_to_ticker = {executor.submit(fetch_all, ticker): ticker for ticker in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    news_data_map[ticker] = future.result()
                except Exception as e:
                    logger.error(f"Error fetching news for {ticker}: {e}")
                    news_data_map[ticker] = {"error": str(e)}

        # 2. Prepare context
        valid_tickers = []
        combined_text = ""
        for ticker, data in news_data_map.items():
            if "error" not in data:
                valid_tickers.append(ticker)
                # Trim to avoid exceeding context or confusing AI with too much noise per stock
                news_str = str(data['news'])[:2000]
                reddit_str = str(data['reddit'])[:2000]
                twitter_str = str(data['twitter'])[:2000]
                combined_text += f"\n[{ticker}]\nNEWS: {news_str}\nREDDIT: {reddit_str}\nTWITTER: {twitter_str}\n"

        if not valid_tickers:
            return {"status": "error", "message": "Failed to fetch news data for any tickers."}

        # 3. Call AI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1, max_retries=0)
        system_prompt = f"""You are Agent 2, the News & Sentiment Analyzer.
        Analyze the following real-time data for the following stocks: {valid_tickers}. 
        Calculate the overall sentiment and conviction score for each.
        Also, extract the 5 most important news headlines or social media posts for each.

        [NEWS DATA]
        {combined_text}
        """
        
        schema_prompt = """
        Return ONLY a valid JSON object matching this exact format, where the keys are the stock tickers:
        {
            "AAPL": {
                "ticker": "AAPL",
                "overall_sentiment": "Bullish",
                "conviction_score": 8,
                "summary": "Short 2 sentence summary here.",
                "top_headlines": [
                    {
                        "title": "Headline 1",
                        "description": "Short explanation of the headline."
                    }
                ]
            }
        }
        """
        
        response = None
        for attempt in range(6):
            try:
                response = await run_in_threadpool(
                    llm.invoke, 
                    [HumanMessage(content=system_prompt), HumanMessage(content=schema_prompt)]
                )
                break
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(f"Agent 2 Batch: Google Rate Limit hit! Waiting 65s (Attempt {attempt+1}/6)...")
                    await run_in_threadpool(time.sleep, 65)
                    if attempt == 5:
                        raise e
                else:
                    raise e
                    
        content = response.content
        if isinstance(content, list):
            content = "".join([c["text"] if isinstance(c, dict) and "text" in c else str(c) for c in content])
        
        raw_text = str(content).strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        try:
            ai_json = json.loads(raw_text)
        except Exception as e:
            logger.error(f"Failed to parse Agent 2 Batch JSON: {e}")
            ai_json = {}
        
        # 4. Upsert into database
        saved_count = 0
        for ticker in valid_tickers:
            final_dict = ai_json.get(ticker, {})
            if not final_dict:
                continue
                
            final_dict["ticker"] = ticker # Ensure ticker is present
            top_headlines = final_dict.get("top_headlines", [])
            
            latest_analysis = db.query(AIAnalysis).filter(
                AIAnalysis.ticker == ticker
            ).order_by(AIAnalysis.created_at.desc()).first()
            
            is_new_news = True
            if latest_analysis and latest_analysis.analysis_data:
                old_headlines = latest_analysis.analysis_data.get("top_headlines", [])
                if old_headlines == top_headlines:
                    is_new_news = False
                    
            if is_new_news:
                db.add(AIAnalysis(ticker=ticker, analysis_data=final_dict))
            else:
                latest_analysis.created_at = datetime.now(timezone.utc)
                
            existing_news = db.query(StockNews).filter(StockNews.ticker == ticker).first()
            if existing_news:
                existing_news.headlines = top_headlines
                existing_news.created_at = datetime.now(timezone.utc)
            else:
                db.add(StockNews(ticker=ticker, headlines=top_headlines))
                
            saved_count += 1
            
        db.commit()
        response_dict = {"status": "success", "message": f"Saved {saved_count} tickers news to database!"}
        ANALYZE_CACHE[cache_key] = (time.time() + CACHE_TTL, response_dict)
        return response_dict
        
    except Exception as e:
        logger.error(f"Error in /analyze-batch endpoint: {str(e)}")
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

@router.get("/market-signals/{ticker}")
def get_market_signals(ticker: str, db: Session = Depends(get_db)):
    """
    Fetches the latest Agent 1 Market Analysis from the database.
    """
    try:
        # Ask the database for the row matching this ticker
        signal = db.query(MarketSignals).filter(MarketSignals.ticker == ticker.upper()).first()
        
        if not signal:
            raise HTTPException(status_code=404, detail=f"No market signals found for {ticker}")
            
        # Return the exact JSON that Agent 1 generated!
        return {
            "ticker": signal.ticker,
            "last_updated": signal.updated_at,
            "agent1_analysis": signal.scan_data
        }
        
    except Exception as e:
        logger.error(f"Error fetching market signals for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))