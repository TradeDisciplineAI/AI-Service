import pytest
from src.schemas import (
    TechnicalIndicatorsResult, 
    MACDResult, 
    EMAResult, 
    BollingerBandsResult,
    SignalAction,
    ConfidenceMode,
    TradeSignal
)
from src.strategies.momentum_breakout import MomentumBreakoutStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.ema_crossover import EMACrossoverStrategy
from src.strategies.evaluator import StrategyEvaluator

@pytest.fixture
def mock_technicals():
    return TechnicalIndicatorsResult(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=58.5,
        macd=MACDResult(macd_line=2.4, signal_line=1.8, histogram=0.6),
        ema=EMAResult(ema_9=2442.0, ema_21=2430.0, trend="UPTREND"),
        bollinger=BollingerBandsResult(upper=2470.0, middle=2440.0, lower=2410.0, bandwidth=0.024),
        atr=20.0,
        summary={"momentum": "NEUTRAL"}
    )

def test_momentum_breakout_strategy_trigger(mock_technicals):
    strat = MomentumBreakoutStrategy()
    scan = {"breakout_detected": True, "volume_surge": True}
    sig = strat.evaluate(mock_technicals, scan)
    assert sig.action == SignalAction.BUY
    assert sig.score == 0.90
    assert sig.strategy_name == "MomentumBreakout"

def test_mean_reversion_strategy_trigger():
    strat = MeanReversionStrategy()
    oversold_technicals = TechnicalIndicatorsResult(
        symbol="RELIANCE",
        current_price=2400.0,
        rsi=28.0,
        macd=MACDResult(macd_line=-5.0, signal_line=-6.0, histogram=1.0),
        ema=EMAResult(ema_9=2410.0, ema_21=2420.0, trend="DOWNTREND"),
        bollinger=BollingerBandsResult(upper=2460.0, middle=2430.0, lower=2400.0, bandwidth=0.025),
        atr=18.0
    )
    sig = strat.evaluate(oversold_technicals, {})
    assert sig.action == SignalAction.BUY
    assert sig.score == 0.85
    assert sig.strategy_name == "MeanReversion"

def test_ema_crossover_strategy_trigger():
    strat = EMACrossoverStrategy()
    cross_technicals = TechnicalIndicatorsResult(
        symbol="RELIANCE",
        current_price=2450.0,
        rsi=52.0,
        macd=MACDResult(macd_line=1.0, signal_line=0.5, histogram=0.5),
        ema=EMAResult(ema_9=2445.0, ema_21=2440.0, trend="BULLISH_CROSS"),
        bollinger=BollingerBandsResult(upper=2470.0, middle=2440.0, lower=2410.0, bandwidth=0.024),
        atr=15.0
    )
    sig = strat.evaluate(cross_technicals, {})
    assert sig.action == SignalAction.BUY
    assert sig.score == 0.80
    assert sig.strategy_name == "EMACrossover"

def test_full_integration_mode_weights_and_threshold(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}
    sentiment = {"sentiment_score": 0.60}  # norm = 0.80
    rag = {"confidence_adjustment": 0.10}  # norm = 0.60

    result = evaluator.evaluate_all(mock_technicals, scan, sentiment, rag)
    assert isinstance(result, TradeSignal)
    assert result.confidence_mode == ConfidenceMode.FULL_INTEGRATION
    assert result.required_threshold == 0.65
    # Expected: (0.50 * 0.90) + (0.30 * 0.80) + (0.20 * 0.60) = 0.45 + 0.24 + 0.12 = 0.81
    assert result.confidence_score == 0.81
    assert result.action == SignalAction.BUY

def test_rag_offline_mode_renormalized_weights_and_threshold(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}
    sentiment = {"sentiment_score": 0.60}  # norm = 0.80
    rag_offline = None

    result = evaluator.evaluate_all(mock_technicals, scan, sentiment, rag_offline)
    assert result.confidence_mode == ConfidenceMode.RAG_OFFLINE
    assert result.required_threshold == 0.75
    # Expected: (0.625 * 0.90) + (0.375 * 0.80) = 0.5625 + 0.30 = 0.8625
    assert result.confidence_score == 0.8625
    assert result.action == SignalAction.BUY

def test_sentiment_offline_mode_renormalized_weights_and_threshold(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}
    sentiment_offline = {"error": "Timeout connecting to NewsAPI"}
    rag = {"confidence_adjustment": 0.10}  # norm = 0.60

    result = evaluator.evaluate_all(mock_technicals, scan, sentiment_offline, rag)
    assert result.confidence_mode == ConfidenceMode.SENTIMENT_OFFLINE
    assert result.required_threshold == 0.75
    # Expected: (0.714 * 0.90) + (0.286 * 0.60) = 0.6426 + 0.1716 = 0.8142
    assert result.confidence_score == 0.8142
    assert result.action == SignalAction.BUY

def test_technical_only_mode_renormalized_weights_and_threshold(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}

    result = evaluator.evaluate_all(mock_technicals, scan, None, None)
    assert result.confidence_mode == ConfidenceMode.TECHNICAL_ONLY
    assert result.required_threshold == 0.80
    # Expected: 1.000 * 0.90 = 0.90 >= 0.80 -> BUY
    assert result.confidence_score == 0.90
    assert result.action == SignalAction.BUY

def test_zero_strategies_firing_fallback(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {}  # No breakout or volume surge
    # Change trend to neutral
    mock_technicals.ema.trend = "NEUTRAL"
    mock_technicals.rsi = 50.0

    result = evaluator.evaluate_all(mock_technicals, scan, None, None)
    assert result.action == SignalAction.HOLD
    assert result.primary_strategy == "None"
    assert "Filtered to HOLD: No strategy triggered." in result.reasons

def test_rag_adjustment_zero_is_valid(mock_technicals):
    """Verify explicit zero adjustment is treated as valid RAG data, not missing."""
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}
    sentiment = {"sentiment_score": 0.60}
    rag_zero = {"confidence_adjustment": 0.0}  # Valid 0.0 adjustment!

    result = evaluator.evaluate_all(mock_technicals, scan, sentiment, rag_zero)
    assert result.confidence_mode == ConfidenceMode.FULL_INTEGRATION
    assert result.required_threshold == 0.65

def test_score_rag_clamping(mock_technicals):
    """Verify out-of-bounds RAG adjustments (+0.80 or -0.80) are clamped to [0.0, 1.0]."""
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}
    sentiment = {"sentiment_score": 0.0}  # norm = 0.50
    rag_extreme = {"confidence_adjustment": 0.90}  # 0.50 + 0.90 = 1.40 -> Clamped to 1.00

    result = evaluator.evaluate_all(mock_technicals, scan, sentiment, rag_extreme)
    # Expected: (0.50 * 0.90) + (0.30 * 0.50) + (0.20 * 1.00) = 0.45 + 0.15 + 0.20 = 0.80
    assert result.confidence_score == 0.80

def test_atr_target_price_and_risk_reward_math(mock_technicals):
    evaluator = StrategyEvaluator()
    scan = {"breakout_detected": True, "volume_surge": True}

    result = evaluator.evaluate_all(mock_technicals, scan, None, None)
    # current_price = 2450.0, atr = 20.0
    # stop_loss = 2450.0 - (1.5 * 20.0) = 2420.0
    # risk = 30.0
    # take_profit = 2450.0 + (2.0 * 30.0) = 2510.0
    # R:R = (2510.0 - 2450.0) / (2450.0 - 2420.0) = 60.0 / 30.0 = 2.0
    assert result.entry_price == 2450.0
    assert result.stop_loss == 2420.0
    assert result.take_profit == 2510.0
    assert result.risk_reward_ratio == 2.0
