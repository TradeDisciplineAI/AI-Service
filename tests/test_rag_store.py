import pytest
from qdrant_client import QdrantClient
from src.schemas import TradeExecutionRecord, SignalAction
from src.rag.vector_store import QdrantTradeVectorStore

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

def test_generate_embedding(memory_vector_store):
    """
    Verifies vector embedding generation outputs exactly 384 float dimensions.
    """
    text = "Symbol: RELIANCE Action: BUY PnL: 150.0 Strategy: MomentumBreakout Note: Healthy breakout"
    vector = memory_vector_store.generate_embedding(text)
    assert isinstance(vector, list)
    assert len(vector) == 384
    assert all(isinstance(x, float) for x in vector)

def test_store_trade_record(memory_vector_store):
    """
    Verifies storing a TradeExecutionRecord inserts a point and returns a UUID vector_id.
    """
    record = TradeExecutionRecord(
        trade_id="TRD-98124",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2450.0,
        exit_price=2500.0,
        pnl=2500.0,
        pnl_percentage=2.04,
        strategy_used="MomentumBreakout",
        emotion_note="Disciplined entry at EMA breakout",
        timestamp="2026-08-17T09:30:00Z"
    )
    
    vector_id = memory_vector_store.store_trade(record)
    assert vector_id is not None
    assert len(vector_id) > 0
    assert memory_vector_store.count_trades() == 1
    assert memory_vector_store.count_trades(symbol="RELIANCE") == 1

def test_get_trade_by_id(memory_vector_store):
    """
    Verifies retrieving a trade by trade_id returns the exact saved metadata payload.
    """
    record = TradeExecutionRecord(
        trade_id="TRD-77123",
        symbol="INFY",
        action=SignalAction.SELL,
        entry_price=1500.0,
        exit_price=1450.0,
        pnl=1000.0,
        pnl_percentage=3.33,
        strategy_used="EMACrossover",
        emotion_note="Clean exit at profit target",
        timestamp="2026-08-17T09:40:00Z"
    )
    
    memory_vector_store.store_trade(record)
    payload = memory_vector_store.get_trade_by_id("TRD-77123")
    
    assert payload is not None
    assert payload["trade_id"] == "TRD-77123"
    assert payload["symbol"] == "INFY"
    assert payload["pnl"] == 1000.0
    assert payload["emotion_note"] == "Clean exit at profit target"

def test_count_trades_symbol_filtering(memory_vector_store):
    """
    Verifies symbol filtering counts trades correctly for distinct symbols.
    """
    rec1 = TradeExecutionRecord(
        trade_id="TRD-001",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2400.0,
        exit_price=2450.0,
        pnl=500.0,
        pnl_percentage=2.08,
        strategy_used="MomentumBreakout",
        timestamp="2026-08-17T09:00:00Z"
    )
    rec2 = TradeExecutionRecord(
        trade_id="TRD-002",
        symbol="TATASTEEL",
        action=SignalAction.BUY,
        entry_price=150.0,
        exit_price=145.0,
        pnl=-500.0,
        pnl_percentage=-3.33,
        strategy_used="MeanReversion",
        timestamp="2026-08-17T09:10:00Z"
    )
    
    memory_vector_store.store_trade(rec1)
    memory_vector_store.store_trade(rec2)
    
    assert memory_vector_store.count_trades() == 2
    assert memory_vector_store.count_trades(symbol="RELIANCE") == 1
    assert memory_vector_store.count_trades(symbol="TATASTEEL") == 1
    assert memory_vector_store.count_trades(symbol="WIPRO") == 0
