import pytest
import uuid
from unittest.mock import MagicMock
from qdrant_client import QdrantClient
from src.schemas import TradeExecutionRecord, SignalAction
from src.rag.vector_store import QdrantTradeVectorStore, RAGStorageError

@pytest.fixture
def memory_vector_store():
    """
    Fixture creating an in-memory QdrantTradeVectorStore for fast, isolated test runs.
    """
    client = QdrantClient(":memory:")
    return QdrantTradeVectorStore(client=client, collection_name="test_trade_history")

def test_qdrant_in_memory_initialization(memory_vector_store):
    """
    Verifies that the target Qdrant collection is created with 384 dimensions.
    """
    collections = memory_vector_store.client.get_collections().collections
    assert any(c.name == "test_trade_history" for c in collections)

def test_init_collection_idempotent_double_call(memory_vector_store):
    """
    Verifies calling init_collection() multiple times is safe and does not wipe or recreate collection.
    """
    # Store initial trade
    record = TradeExecutionRecord(
        trade_id="TRD-IDEMPOTENT-1",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2400.0,
        exit_price=2450.0,
        pnl=500.0,
        pnl_percentage=2.08,
        strategy_used="MomentumBreakout",
        timestamp="2026-08-17T09:00:00Z"
    )
    memory_vector_store.store_trade(record)
    assert memory_vector_store.count_trades() == 1

    # Call init_collection again
    memory_vector_store.init_collection()
    assert memory_vector_store.count_trades() == 1

def test_record_to_text_formatting(memory_vector_store):
    """
    Verifies record_to_text explicitly formats symbol, action, strategy, pnl, and emotion note.
    """
    record = TradeExecutionRecord(
        trade_id="TRD-TEXT-SPEC",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2450.0,
        exit_price=2420.0,
        pnl=-300.0,
        pnl_percentage=-1.22,
        strategy_used="MomentumBreakout",
        emotion_note="Panic sell on red candle spike",
        timestamp="2026-08-17T09:30:00Z"
    )
    formatted = memory_vector_store.record_to_text(record)
    assert "Symbol: RELIANCE" in formatted
    assert "Action: BUY" in formatted
    assert "Strategy: MomentumBreakout" in formatted
    assert "Outcome: LOSS" in formatted
    assert "PnL: -300.00 (-1.22%)" in formatted
    assert "Market Note: Panic sell on red candle spike" in formatted

def test_duplicate_store_trade_upsert_idempotency(memory_vector_store):
    """
    Verifies duplicate store_trade() calls for the same trade_id update the point idempotently without creating duplicates.
    """
    record1 = TradeExecutionRecord(
        trade_id="TRD-DUP-100",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2450.0,
        exit_price=2500.0,
        pnl=2500.0,
        pnl_percentage=2.04,
        strategy_used="MomentumBreakout",
        emotion_note="Initial entry",
        timestamp="2026-08-17T09:30:00Z"
    )
    vec_id_1 = memory_vector_store.store_trade(record1)
    assert memory_vector_store.count_trades() == 1

    # Second call with updated exit price and PnL for same trade_id
    record2 = TradeExecutionRecord(
        trade_id="TRD-DUP-100",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2450.0,
        exit_price=2520.0,
        pnl=3500.0,
        pnl_percentage=2.86,
        strategy_used="MomentumBreakout",
        emotion_note="Updated trailing stop exit",
        timestamp="2026-08-17T09:35:00Z"
    )
    vec_id_2 = memory_vector_store.store_trade(record2)
    
    assert vec_id_1 == vec_id_2  # Deterministic UUID point match
    assert memory_vector_store.count_trades() == 1  # No duplicate point created
    
    payload = memory_vector_store.get_trade_by_id("TRD-DUP-100")
    assert payload["pnl"] == 3500.0
    assert payload["emotion_note"] == "Updated trailing stop exit"

def test_generate_embedding(memory_vector_store):
    """
    Verifies vector embedding generation outputs exactly 384 float dimensions.
    """
    text = "Symbol: RELIANCE | Action: BUY | Strategy: MomentumBreakout | Outcome: WIN | PnL: 150.00 (1.20%) | Market Note: Healthy breakout"
    vector = memory_vector_store.generate_embedding(text)
    assert isinstance(vector, list)
    assert len(vector) == 384
    assert all(isinstance(x, float) for x in vector)

def test_rag_storage_error_handling():
    """
    Verifies RAGStorageError is raised when Qdrant client encounters a storage exception.
    """
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [MagicMock(name="test_history")]
    mock_client.upsert.side_effect = Exception("Connection refused by Qdrant server")

    store = QdrantTradeVectorStore(client=mock_client, collection_name="test_history")
    
    record = TradeExecutionRecord(
        trade_id="TRD-ERR-1",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=100.0,
        exit_price=105.0,
        pnl=5.0,
        pnl_percentage=5.0,
        strategy_used="Test",
        timestamp="2026-08-17T10:00:00Z"
    )

    with pytest.raises(RAGStorageError) as exc_info:
        store.store_trade(record)
    assert "Qdrant storage failed" in str(exc_info.value)
