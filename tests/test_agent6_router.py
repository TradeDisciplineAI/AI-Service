import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.main import app
from src.schemas import RAGIngestResponse
from src.rag.vector_store import RAGStorageError

client = TestClient(app)

def test_agent6_ingest_endpoint_success():
    """
    Verifies POST /agent6/ingest stores a trade record and returns HTTP 201 Created.
    """
    payload = {
        "trade_id": "TRD-API-100",
        "symbol": "RELIANCE",
        "action": "BUY",
        "entry_price": 2400.0,
        "exit_price": 2450.0,
        "pnl": 500.0,
        "pnl_percentage": 2.08,
        "strategy_used": "MomentumBreakout",
        "emotion_note": "Great entry",
        "timestamp": "2026-08-17T10:00:00Z"
    }

    mock_res = RAGIngestResponse(status="stored", trade_id="TRD-API-100", vector_id="mock-uuid-123")
    with patch("src.routers.agent6_router.vector_store.store_trade", return_value=mock_res):
        res = client.post("/agent6/ingest", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "stored"
        assert data["trade_id"] == "TRD-API-100"

def test_agent6_ingest_endpoint_503_on_rag_storage_error():
    """
    Verifies POST /agent6/ingest catches RAGStorageError and raises HTTP 503 Service Unavailable cleanly.
    """
    payload = {
        "trade_id": "TRD-ERR-503",
        "symbol": "RELIANCE",
        "action": "BUY",
        "entry_price": 2400.0,
        "exit_price": 2380.0,
        "pnl": -200.0,
        "pnl_percentage": -0.83,
        "strategy_used": "MomentumBreakout",
        "timestamp": "2026-08-17T10:00:00Z"
    }

    with patch("src.routers.agent6_router.vector_store.store_trade", side_effect=RAGStorageError("Qdrant connection refused")):
        res = client.post("/agent6/ingest", json=payload)
        assert res.status_code == 503
        data = res.json()
        assert "Qdrant Vector DB Storage Unavailable" in data["detail"]

def test_agent6_evaluate_endpoint_success():
    """
    Verifies POST /agent6/evaluate evaluates setup memory and returns HTTP 200 OK with RAGContextResponse.
    """
    payload = {
        "symbol": "RELIANCE",
        "current_price": 2450.0,
        "rsi": 55.0,
        "price_change_pct_24h": 1.0,
        "strategy": "MomentumBreakout",
        "timestamp": "2026-08-17T10:00:00Z",
        "recent_trades": []
    }

    res = client.post("/agent6/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert "confidence_adjustment" in data
    assert "historical_win_rate" in data
