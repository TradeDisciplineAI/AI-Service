import logging
from fastapi import APIRouter, HTTPException, status
from src.schemas import Agent3EvaluateRequest, TradeSignal
from src.agent3_graph import agent3_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent3", tags=["Agent 3 - Strategy Engine"])

@router.post("/evaluate", response_model=TradeSignal, status_code=status.HTTP_200_OK)
async def evaluate_ticker(request: Agent3EvaluateRequest):
    """
    Evaluates market technicals, multi-strategies, sentiment, and RAG context for a ticker.
    Emits a risk-managed TradeSignal (BUY/HOLD/SELL, Entry, Stop Loss, Take Profit, Confidence Score).
    """
    try:
        initial_state = {
            "ticker": request.ticker.upper(),
            "market_scan_json": request.market_scan_json,
            "sentiment_analysis_json": request.sentiment_analysis_json,
            "rag_context_json": request.rag_context_json,
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
                detail=f"Agent 3 workflow failed to generate final trade signal for {request.ticker}."
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
