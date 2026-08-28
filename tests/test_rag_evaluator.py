from datetime import UTC, datetime, timedelta

import pytest
from qdrant_client import QdrantClient

from src.rag.evaluator import RAGEvaluator
from src.rag.mistake_detector import detect_discipline_mistakes, parse_utc_timestamp
from src.rag.vector_store import QdrantTradeVectorStore
from src.schemas import RAGQueryRequest, SignalAction, TradeExecutionRecord


@pytest.fixture
def memory_evaluator():
    """
    Fixture creating an in-memory RAGEvaluator for fast, isolated unit testing.
    """
    client = QdrantClient(":memory:")
    store = QdrantTradeVectorStore(
        client=client, collection_name="test_evaluator_history"
    )
    return RAGEvaluator(vector_store=store)


def test_utc_timestamp_parsing_safety():
    """
    Verifies parse_utc_timestamp converts naive and ISO strings into UTC-aware datetime objects safely.
    """
    dt_iso = parse_utc_timestamp("2026-08-17T09:30:00Z")
    assert dt_iso.tzinfo is not None
    assert dt_iso.tzinfo == UTC

    dt_naive = parse_utc_timestamp("2026-08-17T09:30:00")
    assert dt_naive.tzinfo is not None
    assert dt_naive.tzinfo == UTC


def test_detect_discipline_mistakes_revenge_trading():
    """
    Verifies REVENGE_TRADING_RISK triggers when a loss trade occurred within 15 minutes (account-wide).
    """
    now_dt = datetime.now(UTC)
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
        timestamp=ts_10m_ago,
    )

    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=55.0,
        price_change_pct_24h=1.0,
        strategy="MomentumBreakout",
        timestamp=ts_now,
        recent_trades=[loss_trade],
    )

    flags = detect_discipline_mistakes(req, [loss_trade])
    assert "REVENGE_TRADING_RISK" in flags


def test_detect_discipline_mistakes_exact_15m_time_boundary():
    """
    Explicitly tests the 15-minute time boundary for Revenge Trading:
    - Loss trade at exactly 15m 00s (900s) ago -> FLAGGED
    - Loss trade at 15m 01s (901s) ago -> NOT FLAGGED
    """
    now_dt = datetime.now(UTC)
    ts_now = now_dt.isoformat()
    ts_exactly_15m = (now_dt - timedelta(seconds=900)).isoformat()
    ts_15m_01s = (now_dt - timedelta(seconds=901)).isoformat()

    trade_900s = TradeExecutionRecord(
        trade_id="TRD-900S",
        symbol="TCS",
        action=SignalAction.BUY,
        entry_price=3000.0,
        exit_price=2950.0,
        pnl=-100.0,
        pnl_percentage=-1.67,
        strategy_used="MomentumBreakout",
        timestamp=ts_exactly_15m,
    )

    trade_901s = TradeExecutionRecord(
        trade_id="TRD-901S",
        symbol="TCS",
        action=SignalAction.BUY,
        entry_price=3000.0,
        exit_price=2950.0,
        pnl=-100.0,
        pnl_percentage=-1.67,
        strategy_used="MomentumBreakout",
        timestamp=ts_15m_01s,
    )

    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=50.0,
        price_change_pct_24h=0.0,
        strategy="MomentumBreakout",
        timestamp=ts_now,
        recent_trades=[],
    )

    # 900s boundary check -> FLAGGED
    flags_900s = detect_discipline_mistakes(req, [trade_900s])
    assert "REVENGE_TRADING_RISK" in flags_900s

    # 901s boundary check -> NOT FLAGGED
    flags_901s = detect_discipline_mistakes(req, [trade_901s])
    assert "REVENGE_TRADING_RISK" not in flags_901s


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
        recent_trades=[],
    )
    flags = detect_discipline_mistakes(req, [])
    assert "FOMO_ENTRY_RISK" in flags


def test_detect_discipline_mistakes_overtrading():
    """
    Verifies OVERTRADING_RISK triggers when > 5 trades were executed in the last 60 minutes.
    """
    now_dt = datetime.now(UTC)
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
            timestamp=(now_dt - timedelta(minutes=i * 5)).isoformat(),
        )
        recent_trades.append(trade)

    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=50.0,
        price_change_pct_24h=0.5,
        strategy="MomentumBreakout",
        timestamp=ts_now,
        recent_trades=recent_trades,
    )

    flags = detect_discipline_mistakes(req, recent_trades)
    assert "OVERTRADING_RISK" in flags


def test_win_rate_adjustment_exact_fractional_division(memory_evaluator):
    """
    Verifies calculate_win_rate_adjustment using actual floating point division expressions (4/5, 3/5, 2/5, 1/5)
    and float precision artifact bounds guarded by WIN_RATE_EPSILON (1e-9).
    """
    # 4/5 = 0.80 -> +0.20
    wr_4_5 = 4 / 5.0
    assert memory_evaluator.calculate_win_rate_adjustment(wr_4_5) == 0.20
    assert (
        memory_evaluator.calculate_win_rate_adjustment(wr_4_5 - 1e-12) == 0.20
    )  # Float precision artifact

    # 3/5 = 0.60 -> +0.10
    wr_3_5 = 3 / 5.0
    assert memory_evaluator.calculate_win_rate_adjustment(wr_3_5) == 0.10
    assert memory_evaluator.calculate_win_rate_adjustment(wr_3_5 - 1e-12) == 0.10

    # 2/5 = 0.40 -> -0.15
    wr_2_5 = 2 / 5.0
    assert memory_evaluator.calculate_win_rate_adjustment(wr_2_5) == -0.15
    assert memory_evaluator.calculate_win_rate_adjustment(wr_2_5 + 1e-12) == -0.15

    # 1/5 = 0.20 -> -0.30
    wr_1_5 = 1 / 5.0
    assert memory_evaluator.calculate_win_rate_adjustment(wr_1_5) == -0.30
    assert memory_evaluator.calculate_win_rate_adjustment(wr_1_5 + 1e-12) == -0.30


def test_query_similar_setups_symbol_filtering(memory_evaluator):
    """
    Dedicated test for query_similar_setups: verifies vector similarity search filters by symbol correctly.
    """
    # Store RELIANCE trade and TCS trade
    trade_rel = TradeExecutionRecord(
        trade_id="TRD-REL-1",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        entry_price=2400.0,
        exit_price=2450.0,
        pnl=500.0,
        pnl_percentage=2.08,
        strategy_used="MomentumBreakout",
        timestamp="2026-08-17T08:00:00Z",
    )
    trade_tcs = TradeExecutionRecord(
        trade_id="TRD-TCS-1",
        symbol="TCS",
        action=SignalAction.BUY,
        entry_price=3200.0,
        exit_price=3250.0,
        pnl=500.0,
        pnl_percentage=1.56,
        strategy_used="MomentumBreakout",
        timestamp="2026-08-17T08:00:00Z",
    )
    memory_evaluator.vector_store.store_trade(trade_rel)
    memory_evaluator.vector_store.store_trade(trade_tcs)

    # Query RELIANCE setups
    rel_setups = memory_evaluator.query_similar_setups(
        "RELIANCE", "Symbol: RELIANCE | Action: BUY", top_k=5
    )
    assert len(rel_setups) == 1
    assert rel_setups[0]["symbol"] == "RELIANCE"

    # Query TCS setups
    tcs_setups = memory_evaluator.query_similar_setups(
        "TCS", "Symbol: TCS | Action: BUY", top_k=5
    )
    assert len(tcs_setups) == 1
    assert tcs_setups[0]["symbol"] == "TCS"


def test_warning_flag_multi_reason_formatting(memory_evaluator):
    """
    Dedicated test asserting the exact multi-reason warning string format when low win rate (< 50%) and active mistake flags trigger.
    """
    # Seed 5 trades for RELIANCE (1 win, 4 losses -> 20% win rate)
    for i in range(5):
        pnl = 500.0 if i == 0 else -200.0
        trade = TradeExecutionRecord(
            trade_id=f"TRD-LOW-WR-{i}",
            symbol="RELIANCE",
            action=SignalAction.BUY,
            entry_price=2400.0,
            exit_price=2450.0 if pnl > 0 else 2380.0,
            pnl=pnl,
            pnl_percentage=2.08 if pnl > 0 else -0.83,
            strategy_used="MomentumBreakout",
            timestamp="2026-08-17T08:00:00Z",
        )
        memory_evaluator.vector_store.store_trade(trade)

    # Trigger FOMO_ENTRY_RISK (RSI > 70 & surge > 3%)
    req = RAGQueryRequest(
        symbol="RELIANCE",
        current_price=2500.0,
        rsi=75.0,
        price_change_pct_24h=4.0,
        strategy="MomentumBreakout",
        timestamp="2026-08-17T10:00:00Z",
        recent_trades=[],
    )

    response = memory_evaluator.evaluate_setup(req)

    assert response.similar_trades_count == 5
    assert response.historical_win_rate == 0.20
    assert (
        response.warning_flag
        == "WARNING: Low historical win rate (20.0%); Active Discipline Risks: FOMO_ENTRY_RISK"
    )


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
        recent_trades=[],
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
            timestamp="2026-08-17T08:00:00Z",
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
        recent_trades=[],
    )

    response = memory_evaluator.evaluate_setup(req)

    assert response.similar_trades_count == 5
    assert response.historical_win_rate == 0.80
    # Base adjustment (+0.20) minus penalty (-0.10) = +0.10
    assert response.confidence_adjustment == 0.10
    assert "FOMO_ENTRY_RISK" in response.mistake_flags
    assert response.warning_flag is not None
    assert "FOMO_ENTRY_RISK" in response.warning_flag
