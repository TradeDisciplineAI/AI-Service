import pytest
from fastapi.testclient import TestClient

from src.agent3_graph import agent3_app
from src.main import app
from src.schemas import ConfidenceMode, SignalAction, TradeSignal

client = TestClient(app)


@pytest.fixture
def sample_market_scan():
    return {
        "symbol": "RELIANCE",
        "breakout_detected": True,
        "volume_surge": True,
        "candles": [
            {
                "timestamp": f"2026-08-14T10:{i // 60:02d}:{i % 60:02d}Z",
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 98.0 + i,
                "close": 101.0 + i,
                "volume": 1000 + i,
            }
            for i in range(25)
        ],
    }


@pytest.fixture
def sample_sentiment():
    return {"conviction_score": 8, "overall_sentiment": "Bullish"}


@pytest.fixture
def sample_rag():
    return {"confidence_adjustment": 0.30}


@pytest.mark.asyncio
async def test_agent3_graph_full_integration_mode(
    sample_market_scan, sample_sentiment, sample_rag
):
    """Verify state machine execution in FULL_INTEGRATION mode."""
    initial_state = {
        "ticker": "RELIANCE",
        "market_scan_json": sample_market_scan,
        "sentiment_analysis_json": sample_sentiment,
        "rag_context_json": sample_rag,
        "technicals_json": None,
        "final_trade_signal": None,
        "errors": [],
    }

    final_state = await agent3_app.ainvoke(initial_state)
    assert final_state["final_trade_signal"] is not None

    trade_signal = TradeSignal.model_validate(final_state["final_trade_signal"])
    assert trade_signal.symbol == "RELIANCE"
    assert trade_signal.confidence_mode == ConfidenceMode.FULL_INTEGRATION
    assert trade_signal.required_threshold == 0.65
    assert trade_signal.action == SignalAction.BUY


@pytest.mark.asyncio
async def test_agent3_graph_rag_offline_mode(sample_market_scan, sample_sentiment):
    """Verify state machine execution in RAG_OFFLINE mode."""
    initial_state = {
        "ticker": "RELIANCE",
        "market_scan_json": sample_market_scan,
        "sentiment_analysis_json": sample_sentiment,
        "rag_context_json": None,
        "technicals_json": None,
        "final_trade_signal": None,
        "errors": [],
    }

    final_state = await agent3_app.ainvoke(initial_state)
    trade_signal = TradeSignal.model_validate(final_state["final_trade_signal"])
    assert trade_signal.confidence_mode == ConfidenceMode.RAG_OFFLINE
    assert trade_signal.required_threshold == 0.75
    assert trade_signal.action == SignalAction.BUY


@pytest.mark.asyncio
async def test_agent3_graph_sentiment_offline_mode(sample_market_scan, sample_rag):
    """Verify state machine execution in SENTIMENT_OFFLINE mode."""
    initial_state = {
        "ticker": "RELIANCE",
        "market_scan_json": sample_market_scan,
        "sentiment_analysis_json": None,
        "rag_context_json": sample_rag,
        "technicals_json": None,
        "final_trade_signal": None,
        "errors": [],
    }

    final_state = await agent3_app.ainvoke(initial_state)
    trade_signal = TradeSignal.model_validate(final_state["final_trade_signal"])
    assert trade_signal.confidence_mode == ConfidenceMode.SENTIMENT_OFFLINE
    assert trade_signal.required_threshold == 0.75
    assert trade_signal.action == SignalAction.BUY


@pytest.mark.asyncio
async def test_agent3_graph_technical_only_mode(sample_market_scan):
    """Verify state machine execution in TECHNICAL_ONLY mode."""
    initial_state = {
        "ticker": "RELIANCE",
        "market_scan_json": sample_market_scan,
        "sentiment_analysis_json": None,
        "rag_context_json": None,
        "technicals_json": None,
        "final_trade_signal": None,
        "errors": [],
    }

    final_state = await agent3_app.ainvoke(initial_state)
    trade_signal = TradeSignal.model_validate(final_state["final_trade_signal"])
    assert trade_signal.confidence_mode == ConfidenceMode.TECHNICAL_ONLY
    assert trade_signal.required_threshold == 0.80
    assert trade_signal.action == SignalAction.BUY


def test_agent3_router_evaluate_endpoint(
    sample_market_scan, sample_sentiment, sample_rag
):
    """Verify FastAPI POST /agent3/evaluate HTTP endpoint."""
    payload = {
        "ticker": "RELIANCE",
        "market_scan_json": sample_market_scan,
        "sentiment_analysis_json": sample_sentiment,
        "rag_context_json": sample_rag,
    }

    response = client.post("/agent3/evaluate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["symbol"] == "RELIANCE"
    assert data["action"] == "BUY"
    assert data["confidence_mode"] == "FULL_INTEGRATION"
    assert data["entry_price"] > 0
    assert data["stop_loss"] > 0
    assert data["take_profit"] > 0
