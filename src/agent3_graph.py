import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from src.models import Agent3State
from src.schemas import TechnicalIndicatorsResult, TradeSignal, SignalAction, ConfidenceMode
from src.tools.technical_indicators import compute_technical_indicators
from src.strategies.evaluator import StrategyEvaluator
from src.tools.yfinance_tool import fetch_market_data

logger = logging.getLogger(__name__)

# Master Strategy Evaluator Instance
strategy_evaluator = StrategyEvaluator()

def ingest_inputs_node(state: Agent3State) -> Agent3State:
    """
    Node 1: Ingests market scan candles, sentiment analysis, and RAG memory inputs.
    Runs fallback market data fetch if candles are missing.
    """
    ticker = state.get("ticker", "UNKNOWN")
    errors: List[str] = list(state.get("errors") or [])
    
    market_scan = state.get("market_scan_json")
    
    # Check if candles exist in market_scan
    has_candles = (
        market_scan is not None 
        and isinstance(market_scan, dict) 
        and bool(market_scan.get("candles"))
    )
    
    if not has_candles:
        try:
            # Fallback: Fetch raw market data for ticker
            logger.info(f"Market scan candles missing for {ticker}. Running fetch_market_data fallback.")
            raw_candles = fetch_market_data(ticker)
            if isinstance(raw_candles, list) and len(raw_candles) > 0:
                market_scan = {
                    "symbol": ticker,
                    "candles": raw_candles,
                    "breakout_detected": False,
                    "volume_surge": False
                }
            else:
                errors.append(f"Market data fetch returned zero candles for {ticker}.")
                market_scan = {"symbol": ticker, "candles": [], "breakout_detected": False, "volume_surge": False}
        except Exception as e:
            logger.error(f"Error fetching fallback market data for {ticker}: {e}")
            errors.append(f"Market data fetch failed: {str(e)}")
            market_scan = {"symbol": ticker, "candles": [], "breakout_detected": False, "volume_surge": False}

    return {
        **state,
        "market_scan_json": market_scan,
        "errors": errors
    }

def compute_technicals_node(state: Agent3State) -> Agent3State:
    """
    Node 2: Computes vectorized technical indicators (RSI, MACD, EMA, Bollinger, ATR).
    """
    ticker = state.get("ticker", "UNKNOWN")
    errors: List[str] = list(state.get("errors") or [])
    market_scan = state.get("market_scan_json") or {}
    candles = market_scan.get("candles") or []

    try:
        technicals = compute_technical_indicators(ticker, candles)
        technicals_dict = technicals.model_dump()
        if technicals.summary.get("insufficient_candles"):
            errors.append(f"Insufficient candles ({len(candles)}) for technical indicators calculation.")
    except Exception as e:
        logger.error(f"Error computing technical indicators for {ticker}: {e}")
        errors.append(f"Technical indicators calculation failed: {str(e)}")
        # Construct fallback technicals
        technicals_dict = {
            "symbol": ticker,
            "current_price": 0.0,
            "rsi": 50.0,
            "macd": {"macd_line": 0.0, "signal_line": 0.0, "histogram": 0.0},
            "ema": {"ema_9": 0.0, "ema_21": 0.0, "trend": "NEUTRAL"},
            "bollinger": {"upper": 0.0, "middle": 0.0, "lower": 0.0, "bandwidth": 0.0},
            "atr": 0.01,
            "summary": {"error": str(e), "insufficient_candles": True}
        }

    return {
        **state,
        "technicals_json": technicals_dict,
        "errors": errors
    }

def evaluate_strategies_node(state: Agent3State) -> Agent3State:
    """
    Node 3: Evaluates multi-strategies, computes ATR price targets, renormalizes weights,
    and synthesizes the final TradeSignal.
    """
    ticker = state.get("ticker", "UNKNOWN")
    errors: List[str] = list(state.get("errors") or [])
    
    technicals_dict = state.get("technicals_json") or {}
    market_scan = state.get("market_scan_json") or {}
    sentiment = state.get("sentiment_analysis_json")
    rag = state.get("rag_context_json")

    try:
        technicals = TechnicalIndicatorsResult.model_validate(technicals_dict)
        trade_signal = strategy_evaluator.evaluate_all(
            technicals=technicals,
            market_scan=market_scan,
            sentiment_analysis=sentiment,
            rag_context=rag
        )
        
        # Append pipeline errors to trade signal reasons if any exist
        if errors:
            trade_signal.reasons.extend([f"Pipeline Note: {err}" for err in errors])
            
        trade_signal_dict = trade_signal.model_dump()
    except Exception as e:
        logger.error(f"Error evaluating strategies for {ticker}: {e}")
        errors.append(f"Strategy evaluation failed: {str(e)}")
        fallback_signal = TradeSignal(
            signal_id=f"SIG-ERR-{ticker}",
            symbol=ticker,
            action=SignalAction.HOLD,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            risk_reward_ratio=0.0,
            confidence_score=0.0,
            confidence_mode=ConfidenceMode.TECHNICAL_ONLY,
            required_threshold=0.80,
            primary_strategy="None",
            reasons=[f"Execution failed: {str(e)}"] + errors,
            technicals_summary={}
        )
        trade_signal_dict = fallback_signal.model_dump()

    return {
        **state,
        "final_trade_signal": trade_signal_dict,
        "errors": errors
    }

# Build LangGraph State Machine Workflow
workflow = StateGraph(Agent3State)

workflow.add_node("ingest_inputs", ingest_inputs_node)
workflow.add_node("compute_technicals", compute_technicals_node)
workflow.add_node("evaluate_strategies", evaluate_strategies_node)

workflow.set_entry_point("ingest_inputs")
workflow.add_edge("ingest_inputs", "compute_technicals")
workflow.add_edge("compute_technicals", "evaluate_strategies")
workflow.add_edge("evaluate_strategies", END)

# Compile Executable Application
agent3_app = workflow.compile()
