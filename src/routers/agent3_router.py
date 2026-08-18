import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.schemas import Agent3EvaluateRequest, TradeSignal
from src.agent3_graph import agent3_app
from src.agent1_graph import agent1_app
from src.agent2_graph import agent2_app
from src.tools.yfinance_tool import fetch_market_data
from src.database import SessionLocal, MarketSignals, AIAnalysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent3", tags=["Agent 3 - Strategy Engine"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def resolve_market_scan(ticker: str, db: Session, provided: Optional[dict]) -> Optional[dict]:
    """Resolves Agent 1 market scan payload: uses provided dict, DB cached signal, or executes Agent 1 graph with timeout."""
    if provided is not None and isinstance(provided, dict) and "error" not in provided:
        return provided

    # Check DB for existing market signal
    try:
        existing_signal = db.query(MarketSignals).filter(MarketSignals.ticker == ticker).first()
        if existing_signal and existing_signal.scan_data and "error" not in existing_signal.scan_data:
            logger.info(f"Loaded persisted Agent 1 market scan for {ticker} from DB.")
            return existing_signal.scan_data
    except Exception as e:
        logger.warning(f"Could not load persisted market signal for {ticker}: {e}")

    # Fallback to executing Agent 1 graph directly with 6-second timeout
    try:
        logger.info(f"Executing Agent 1 market scanner graph for {ticker}...")
        agent1_res = await asyncio.wait_for(
            run_in_threadpool(agent1_app.invoke, {"ticker": ticker}),
            timeout=6.0
        )
        scan = agent1_res.get("final_scan_json")
        if scan and "error" not in scan:
            try:
                existing = db.query(MarketSignals).filter(MarketSignals.ticker == ticker).first()
                if existing:
                    existing.scan_data = scan
                else:
                    db.add(MarketSignals(ticker=ticker, scan_data=scan))
                db.commit()
            except Exception as dberr:
                logger.warning(f"Failed to persist Agent 1 scan: {dberr}")
            return scan
    except Exception as e:
        logger.warning(f"Agent 1 graph execution skipped/failed for {ticker}: {e}")

    # Fallback to direct python candle fetch if LLM market scanner fails or times out
    try:
        logger.info(f"Using direct market data fallback for Agent 1 scan for {ticker}")
        fetched = fetch_market_data(ticker, limit=30)
        if fetched and "error" not in fetched:
            raw_candles = fetched.get("ohlcv_candles") or []
            return {
                "symbol": ticker,
                "current_price": fetched.get("current_price", 0.0),
                "candles": raw_candles,
                "breakout_detected": False,
                "volume_surge": False,
                "trend_direction": "NEUTRAL"
            }
    except Exception as e:
        logger.error(f"Direct market data fallback failed for {ticker}: {e}")

    return None

async def resolve_sentiment_analysis(ticker: str, db: Session, provided: Optional[dict]) -> Optional[dict]:
    """Resolves Agent 2 sentiment analysis payload: uses provided dict, DB cached analysis, or executes Agent 2 graph with timeout."""
    if provided is not None and isinstance(provided, dict) and "error" not in provided:
        return provided

    # Check DB for existing analysis
    try:
        existing_analysis = db.query(AIAnalysis).filter(AIAnalysis.ticker == ticker).first()
        if existing_analysis and existing_analysis.analysis_data and "error" not in existing_analysis.analysis_data:
            logger.info(f"Loaded persisted Agent 2 sentiment analysis for {ticker} from DB.")
            return existing_analysis.analysis_data
    except Exception as e:
        logger.warning(f"Could not load persisted sentiment analysis for {ticker}: {e}")

    # Fallback to executing Agent 2 graph directly with 6-second timeout
    try:
        logger.info(f"Executing Agent 2 sentiment analyzer graph for {ticker}...")
        agent2_res = await asyncio.wait_for(
            run_in_threadpool(agent2_app.invoke, {"ticker": ticker}),
            timeout=6.0
        )
        analysis = agent2_res.get("final_analysis_json")
        if analysis and "error" not in analysis:
            try:
                existing = db.query(AIAnalysis).filter(AIAnalysis.ticker == ticker).first()
                if existing:
                    existing.analysis_data = analysis
                else:
                    db.add(AIAnalysis(ticker=ticker, analysis_data=analysis))
                db.commit()
            except Exception as dberr:
                logger.warning(f"Failed to persist Agent 2 analysis: {dberr}")
            return analysis
    except Exception as e:
        logger.warning(f"Agent 2 graph execution skipped/failed for {ticker}: {e}")

    # Fallback to default neutral sentiment payload if scrapers/LLM fail or time out
    logger.info(f"Using default neutral sentiment fallback for {ticker}")
    return {
        "ticker": ticker,
        "overall_sentiment": "Neutral",
        "conviction_score": 5,
        "summary": "Default neutral sentiment fallback."
    }

@router.post("/evaluate", response_model=TradeSignal, status_code=status.HTTP_200_OK)
async def evaluate_ticker(request: Agent3EvaluateRequest, db: Session = Depends(get_db)):
    """
    Evaluates market technicals, multi-strategies, sentiment, and RAG context for a ticker.
    Automatically orchestrates Agent 1 (Market Scan) and Agent 2 (Sentiment) if not explicitly provided.
    Emits a risk-managed TradeSignal (BUY/HOLD/SELL, Entry, Stop Loss, Take Profit, Confidence Score).
    """
    try:
        ticker = request.ticker.upper().strip()

        # Orchestrate Agent 1 & Agent 2 inputs if missing
        market_scan = await resolve_market_scan(ticker, db, request.market_scan_json)
        sentiment_analysis = await resolve_sentiment_analysis(ticker, db, request.sentiment_analysis_json)

        # Baseline RAG context for Agent 6 integration
        rag_context = request.rag_context_json or {"confidence_adjustment": 0.0, "notes": "Baseline RAG context"}

        # Log Debug Execution Trace
        logger.info(
            f"[Agent3 Orchestration Trace] ticker={ticker} | "
            f"market_scan_json_present={bool(market_scan)} | "
            f"sentiment_analysis_json_present={bool(sentiment_analysis)} | "
            f"rag_context_json_present={bool(rag_context)}"
        )

        initial_state = {
            "ticker": ticker,
            "market_scan_json": market_scan,
            "sentiment_analysis_json": sentiment_analysis,
            "rag_context_json": rag_context,
            "technicals_json": None,
            "final_trade_signal": None,
            "errors": []
        }

        # Non-blocking async execution of compiled LangGraph workflow
        final_state = await agent3_app.ainvoke(initial_state)
        
        trade_signal_dict = final_state.get("final_trade_signal")
        if not trade_signal_dict:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent 3 workflow failed to generate final trade signal for {ticker}."
            )

        logger.info(
            f"[Agent3 Output Signal] ticker={ticker} | "
            f"action={trade_signal_dict.get('action')} | "
            f"confidence_mode={trade_signal_dict.get('confidence_mode')} | "
            f"confidence_score={trade_signal_dict.get('confidence_score')} | "
            f"primary_strategy={trade_signal_dict.get('primary_strategy')}"
        )

        return TradeSignal.model_validate(trade_signal_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Agent 3 request for {request.ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Agent 3 processing error: {str(e)}"
        )

