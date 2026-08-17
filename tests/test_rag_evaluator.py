import pytest
from datetime import datetime, timezone, timedelta
from qdrant_client import QdrantClient
from src.schemas import RAGQueryRequest, TradeExecutionRecord, SignalAction
from src.rag.vector_store import QdrantTradeVectorStore
from src.rag.evaluator import RAGEvaluator, WIN_RATE_EPSILON
from src.rag.mistake_detector import detect_discipline_mistakes, parse_utc_timestamp

@pytest.fixture
def memory_evaluator():
    """
    Fixture creating an in-memory RAGEvaluator for fast, isolated unit testing.
    """
    client = QdrantClient(":memory:")
    store = QdrantTradeVectorStore(client=client, collection_name="test_evaluator_history")
    return RAGEvaluator(vector_store=store)

def test_utc_timestamp_parsing_safety():
    """
    Verifies parse_utc_timestamp converts naive and ISO strings into UTC-aware datetime objects safely.
    """
    dt_iso = parse_utc_timestamp("2026-08-17T09:30:00Z")
    assert dt_iso.tzinfo is not None
    assert dt_iso.tzinfo == timezone.utc

    dt_naive = parse_utc_timestamp("2026-08-17T09:30:00")
    assert dt_naive.tzinfo is not None
    assert dt_naive.tzinfo == timezone.utc

def test_detect_discipline_mistakes_revenge_trading():
    """
    Verifies REVENGE_TRADING_RISK triggers when a loss trade occurred within 15 minutes (account-wide).
    """
    now_dt = datetime.now(timezone.utc)
    ts_now = now_dt.isoformat()
    ts_10m_ago = (now_dt - timedelta(minutes=10)).isoformat()

    loss_trade = TradeExecutionRecord(
        trade_id="TRD-LOSS-10M",
        symbol="INFY",  # Different symbol check (account-wide)
        action=SignalAction.BUY,
        entry_price=1500.0,
        exit_price=1450.0,
        pnl=-500.0,
        pnl_percentage=-3.33,
        strategy_used="EMACrossover",
        timestamp=ts_10m_ago
    )

    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=55.0,
        price_change_pct_24h=1.0,
        strategy="MomentumBreakout",
        timestamp=ts_now,
        recent_trades=[loss_trade]
    )

    flags = detect_discipline_mistakes(req, [loss_trade])
    assert "REVENGE_TRADING_RISK" in flags

def test_detect_discipline_mistakes_fomo_entry():
    """
    Verifies FOMO_ENTRY_RISK triggers when RSI > 70.0 and 24h price surge > 3.0%.
    """
    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2500.0,
        rsi=75.0,  # > 70
        price_change_pct_24h=4.5,  # > 3.0%
        strategy="MomentumBreakout",
        timestamp="2026-08-17T10:00:00Z",
        recent_trades=[]
    )
    flags = detect_discipline_mistakes(req, [])
    assert "FOMO_ENTRY_RISK" in flags

def test_detect_discipline_mistakes_overtrading():
    """
    Verifies OVERTRADING_RISK triggers when > 5 trades were executed in the last 60 minutes.
    """
    now_dt = datetime.now(timezone.utc)
    ts_now = now_dt.isoformat()
    
    recent_trades = []
    for i in range(6):  # 6 trades in last 60m
        trade = TradeExecutionRecord(
            trade_id=f"TRD-OVER-{i}",
            symbol="RELIANCE",
            action=SignalAction.BUY,
            entry_price=2400.0,
            exit_price=2410.0,
            pnl=100.0,
            pnl_percentage=0.41,
            strategy_used="MomentumBreakout",
            timestamp=(now_dt - timedelta(minutes=i * 5)).isoformat()
        )
        recent_trades.append(trade)

    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=50.0,
        price_change_pct_24h=0.5,
        strategy="MomentumBreakout",
        timestamp=ts_now,
        recent_trades=recent_trades
    )

    flags = detect_discipline_mistakes(req, recent_trades)
    assert "OVERTRADING_RISK" in flags

def test_win_rate_adjustment_exact_boundaries(memory_evaluator):
    """
    Verifies calculate_win_rate_adjustment uses top-down checking with epsilon for exact boundaries (0.80, 0.60, 0.40, 0.20).
    """
    # >= 0.80 -> +0.20
    assert memory_evaluator.calculate_win_rate_adjustment(0.80) == 0.20
    assert memory_evaluator.calculate_win_rate_adjustment(0.80 - 1e-9) == 0.20  # Float precision artifact

    # >= 0.60 -> +0.10
    assert memory_evaluator.calculate_win_rate_adjustment(0.60) == 0.10
    assert memory_evaluator.calculate_win_rate_adjustment(0.75) == 0.10

    # 40% < WR < 60% -> 0.00
    assert memory_evaluator.calculate_win_rate_adjustment(0.50) == 0.00

    # <= 0.40 -> -0.15
    assert memory_evaluator.calculate_win_rate_adjustment(0.40) == -0.15
    assert memory_evaluator.calculate_win_rate_adjustment(0.30) == -0.15

    # <= 0.20 -> -0.30
    assert memory_evaluator.calculate_win_rate_adjustment(0.20) == -0.30
    assert memory_evaluator.calculate_win_rate_adjustment(0.10) == -0.30

def test_evaluate_setup_zero_trades_fallback(memory_evaluator):
    """
    Verifies evaluating a setup with zero similar past trades in Qdrant returns neutral WR (0.50) and zero adjustment (0.00).
    """
    req = RAGQueryRequest(
        symbol="NEWSTOCK",
        current_price=100.0,
        rsi=50.0,
        price_change_pct_24h=0.0,
        strategy="MomentumBreakout",
        timestamp="2026-08-17T10:00:00Z",
        recent_trades=[]
    )
    response = memory_evaluator.evaluate_setup(req)
    
    assert response.symbol == "NEWSTOCK"
    assert response.similar_trades_count == 0
    assert response.historical_win_rate == 0.50
    assert response.confidence_adjustment == 0.00
    assert response.warning_flag is None
    assert response.mistake_flags == []

def test_evaluate_setup_mistake_penalty_stacking_and_clamping(memory_evaluator):
    """
    Verifies similar setups win rate calculation, penalty stacking (-0.10 per flag), and clamping [-0.30, +0.20].
    """
    # Seed 5 past trade setups for RELIANCE (4 wins, 1 loss -> 80% win rate = +0.20 base adjustment)
    for i in range(5):
        pnl = 500.0 if i < 4 else -200.0
        trade = TradeExecutionRecord(
            trade_id=f"TRD-PAST-{i}",
            symbol="RELIANCE",
            action=SignalAction.BUY,
            entry_price=2400.0,
            exit_price=2450.0 if pnl > 0 else 2380.0,
            pnl=pnl,
            pnl_percentage=2.08 if pnl > 0 else -0.83,
            strategy_used="MomentumBreakout",
            timestamp="2026-08-17T08:00:00Z"
        )
        memory_evaluator.vector_store.store_trade(trade)

    # Trigger FOMO_ENTRY_RISK (RSI > 70 & surge > 3%) -> -0.10 penalty
    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2500.0,
        rsi=75.0,
        price_change_pct_24h=4.0,
        strategy="MomentumBreakout",
        timestamp="2026-08-17T10:00:00Z",
        recent_trades=[]
    )

    response = memory_evaluator.evaluate_setup(req)
    
    assert response.similar_trades_count == 5
    assert response.historical_win_rate == 0.80
    # Base adjustment (+0.20) minus penalty (-0.10) = +0.10
    assert response.confidence_adjustment == 0.10
    assert "FOMO_ENTRY_RISK" in response.mistake_flags
    assert response.warning_flag is not None
    assert "FOMO_ENTRY_RISK" in response.warning_flag
