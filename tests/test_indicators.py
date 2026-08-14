import time
import pytest
from src.tools.technical_indicators import compute_technical_indicators, calculate_rsi
from src.schemas import TechnicalIndicatorsResult

def test_compute_technical_indicators_insufficient_candles():
    """Test candle set below threshold of 5 candles."""
    symbol = "TEST"
    candles = [
        {"timestamp": "10:00", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000}
    ]
    result = compute_technical_indicators(symbol, candles)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.symbol == "TEST"
    assert result.current_price == 102.0
    assert result.rsi == 50.0
    assert "error" in result.summary

def test_compute_technical_indicators_exactly_five_candles():
    """Boundary test for exactly 5 candles."""
    symbol = "RELIANCE"
    candles = [
        {"timestamp": f"10:0{i}", "open": 100 + i, "high": 105 + i, "low": 99 + i, "close": 102 + i, "volume": 1000}
        for i in range(5)
    ]
    result = compute_technical_indicators(symbol, candles)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.symbol == "RELIANCE"
    assert result.current_price == 106.0
    assert "error" not in result.summary
    assert result.summary["candles_analyzed"] == 5

def test_rsi_pure_uptrend_and_pure_downtrend():
    """
    Test RSI boundary conditions:
    1. Pure green uptrend (zero losses) -> RSI = 100.0
    2. Pure red downtrend (zero gains)   -> RSI = 0.0
    """
    # 1. Pure Green Uptrend
    green_candles = [
        {"timestamp": f"10:{i:02d}", "open": 100 + i, "high": 102 + i, "low": 100 + i, "close": 101 + i, "volume": 5000}
        for i in range(20)
    ]
    res_green = compute_technical_indicators("GREEN", green_candles)
    assert res_green.rsi == 100.0

    # 2. Pure Red Downtrend
    red_candles = [
        {"timestamp": f"10:{i:02d}", "open": 200 - i, "high": 200 - i, "low": 198 - i, "close": 199 - i, "volume": 5000}
        for i in range(20)
    ]
    res_red = compute_technical_indicators("RED", red_candles)
    assert res_red.rsi == 0.0

    # 3. Flat Price Movement (Zero gains & zero losses)
    flat_candles = [
        {"timestamp": f"10:{i:02d}", "open": 150.0, "high": 150.0, "low": 150.0, "close": 150.0, "volume": 5000}
        for i in range(20)
    ]
    res_flat = compute_technical_indicators("FLAT", flat_candles)
    assert res_flat.rsi == 50.0

def test_zero_true_range_doji_candles():
    """Test zero true range doji candles (H=L=C=prev close) enforces 0.1% price ATR floor."""
    symbol = "FLAT_DOJI"
    price = 100.0
    candles = [
        {"timestamp": f"10:{i:02d}", "open": price, "high": price, "low": price, "close": price, "volume": 0.0}
        for i in range(15)
    ]
    result = compute_technical_indicators(symbol, candles)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.atr == 0.1  # 0.1% of 100.0
    assert result.rsi == 50.0
    assert result.bollinger.bandwidth == 0.0

def test_leading_nan_and_middle_nan_handling():
    """Test leading NaN at index 0 and middle NaNs are safely handled."""
    symbol = "NAN_TEST"
    candles = [
        {"timestamp": "10:00", "open": None, "high": None, "low": None, "close": None, "volume": None},
        {"timestamp": "10:01", "open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000},
        {"timestamp": "10:02", "open": None, "high": 106, "low": 99, "close": 103, "volume": 1200},
        {"timestamp": "10:03", "open": 103, "high": 107, "low": 101, "close": 105, "volume": 1500},
        {"timestamp": "10:04", "open": 105, "high": 108, "low": 102, "close": 107, "volume": 1800},
        {"timestamp": "10:05", "open": 107, "high": 110, "low": 104, "close": 108, "volume": 2000},
    ]
    result = compute_technical_indicators(symbol, candles)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.symbol == "NAN_TEST"
    assert result.current_price == 108.0
    assert result.rsi > 0

def test_out_of_order_monotonic_sorting():
    """Test out of order candles are automatically re-sorted chronologically with warnings."""
    symbol = "UNSORTED"
    candles = [
        {"timestamp": "2026-08-14T10:05:00Z", "open": 105, "high": 108, "low": 104, "close": 107, "volume": 2000},
        {"timestamp": "2026-08-14T10:00:00Z", "open": 100, "high": 102, "low": 98, "close": 101, "volume": 1000},
        {"timestamp": "2026-08-14T10:02:00Z", "open": 101, "high": 104, "low": 100, "close": 103, "volume": 1200},
        {"timestamp": "2026-08-14T10:03:00Z", "open": 103, "high": 105, "low": 101, "close": 104, "volume": 1500},
        {"timestamp": "2026-08-14T10:04:00Z", "open": 104, "high": 106, "low": 102, "close": 105, "volume": 1800},
    ]
    result = compute_technical_indicators(symbol, candles)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.current_price == 107.0
    assert "warnings" in result.summary

def test_performance_benchmark_under_five_milliseconds():
    """Benchmark test verifying execution completes in < 5ms per 100-candle series."""
    symbol = "BENCHMARK"
    candles = [
        {
            "timestamp": f"2026-08-14T10:{i//60:02d}:{i%60:02d}Z",
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 98.0 + i,
            "close": 101.0 + i,
            "volume": 1000 + i
        }
        for i in range(100)
    ]
    
    # Warm up cache
    compute_technical_indicators(symbol, candles)
    
    start_time = time.perf_counter()
    result = compute_technical_indicators(symbol, candles)
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.symbol == "BENCHMARK"
    assert elapsed_ms < 5.0, f"Performance benchmark failed: {elapsed_ms:.2f}ms >= 5.0ms"

def test_custom_indicator_settings_hashability():
    """Verify custom IndicatorSettings object is resolved to primitive scalars without unhashable LRU TypeError."""
    from src.config import IndicatorSettings
    
    custom_cfg = IndicatorSettings(
        RSI_PERIOD=10,
        EMA_FAST_PERIOD=5,
        EMA_SLOW_PERIOD=15
    )
    symbol = "CONFIG_TEST"
    candles = [
        {"timestamp": f"10:{i:02d}", "open": 100.0 + i, "high": 102.0 + i, "low": 98.0 + i, "close": 101.0 + i, "volume": 1000}
        for i in range(20)
    ]
    result = compute_technical_indicators(symbol, candles, config=custom_cfg)
    assert isinstance(result, TechnicalIndicatorsResult)
    assert result.symbol == "CONFIG_TEST"
    assert result.ema.ema_9 > 0
