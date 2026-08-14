import logging
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache
import pandas as pd
import numpy as np

from src.config import indicator_settings, IndicatorSettings
from src.schemas import TechnicalIndicatorsResult, MACDResult, EMAResult, BollingerBandsResult

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

logger = logging.getLogger(__name__)

def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """
    Vectorized RSI calculation with strict boundary handling:
    - Pure Green Uptrend (Zero losses, positive gains) -> 100.0
    - Pure Red Downtrend (Zero gains, positive losses) -> 0.0
    - Flat / Zero Movement (Zero gains & zero losses)  -> 50.0 (Neutral)
    """
    if len(series) < 2:
        return 50.0
        
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    
    loss_val = float(loss.iloc[-1]) if not loss.empty else 0.0
    gain_val = float(gain.iloc[-1]) if not gain.empty else 0.0
    
    # Boundary Guard 1: Zero losses
    if pd.isna(loss_val) or loss_val == 0.0:
        return 100.0 if gain_val > 0.0 else 50.0

    # Boundary Guard 2: Zero gains
    if pd.isna(gain_val) or gain_val == 0.0:
        return 0.0
    
    rs = gain_val / loss_val
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(np.clip(rsi, 0.0, 100.0))

def calculate_atr(df: pd.DataFrame, current_price: float, period: int = 14) -> float:
    """
    Vectorized ATR calculation with a minimum 0.1% volatility floor
    to prevent degenerate zero-stop loss triggers on flat Doji candles.
    """
    if len(df) < 2:
        return max(round(current_price * 0.001, 2), 0.01)

    high = df['high']
    low = df['low']
    close = df['close']
    close_prev = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean().iloc[-1]
    
    # Minimum volatility floor: 0.1% of current price or 0.01 absolute
    min_atr_floor = max(current_price * 0.001, 0.01)
    
    if pd.isna(atr) or atr <= min_atr_floor:
        atr = (high - low).mean()
        
    if pd.isna(atr) or atr <= min_atr_floor:
        atr = min_atr_floor
        
    return float(max(atr, min_atr_floor))

@lru_cache(maxsize=1024)
def _cached_indicator_calc(
    symbol: str, 
    last_timestamp: str, 
    candle_count: int, 
    close_tuple: Tuple[float, ...],
    high_tuple: Tuple[float, ...],
    low_tuple: Tuple[float, ...],
    open_tuple: Tuple[float, ...],
    volume_tuple: Tuple[float, ...],
    rsi_period: int = 14,
    ema_fast: int = 9,
    ema_slow: int = 21,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bollinger_period: int = 20,
    bollinger_std: float = 2.0,
    atr_period: int = 14
) -> Dict[str, Any]:
    """
    Internal LRU cached calculator keyed ONLY on primitive hashable types (strings, ints, floats, tuples).
    Pydantic BaseSettings objects never reach this function, ensuring zero unhashable TypeError crashes.
    """
    df = pd.DataFrame({
        'open': open_tuple,
        'high': high_tuple,
        'low': low_tuple,
        'close': close_tuple,
        'volume': volume_tuple
    })
    
    # Handle NaNs: forward-fill then backward-fill leading NaNs
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    df.fillna(0.0, inplace=True)
    
    current_price = float(df['close'].iloc[-1])

    # 1. RSI Calculation
    if HAS_PANDAS_TA and len(df) >= rsi_period:
        try:
            rsi_series = df.ta.rsi(length=rsi_period)
            rsi_val = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else calculate_rsi(df['close'], rsi_period)
        except Exception:
            rsi_val = calculate_rsi(df['close'], rsi_period)
    else:
        rsi_val = calculate_rsi(df['close'], min(rsi_period, len(df)))

    # 2. EMA Calculation (Fast & Slow)
    ema_9_val = float(df['close'].ewm(span=ema_fast, adjust=False).mean().iloc[-1])
    ema_21_val = float(df['close'].ewm(span=ema_slow, adjust=False).mean().iloc[-1])
    
    if ema_9_val > ema_21_val:
        trend = "BULLISH_CROSS" if len(df) > 1 and df['close'].iloc[-2] <= ema_21_val else "UPTREND"
    elif ema_9_val < ema_21_val:
        trend = "BEARISH_CROSS" if len(df) > 1 and df['close'].iloc[-2] >= ema_21_val else "DOWNTREND"
    else:
        trend = "NEUTRAL"
        
    # 3. MACD Calculation
    ema_fast_series = df['close'].ewm(span=macd_fast, adjust=False).mean()
    ema_slow_series = df['close'].ewm(span=macd_slow, adjust=False).mean()
    macd_line = ema_fast_series - ema_slow_series
    signal_line = macd_line.ewm(span=macd_signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    macd_val = float(macd_line.iloc[-1])
    sig_val = float(signal_line.iloc[-1])
    hist_val = float(histogram.iloc[-1])
    
    # 4. Bollinger Bands Calculation
    period = min(bollinger_period, len(df))
    middle_band = float(df['close'].rolling(window=period, min_periods=1).mean().iloc[-1])
    std_dev = df['close'].rolling(window=period, min_periods=1).std().iloc[-1]
    std_dev = 0.0 if pd.isna(std_dev) else float(std_dev)
    
    upper_band = float(middle_band + (bollinger_std * std_dev))
    lower_band = float(middle_band - (bollinger_std * std_dev))
    bandwidth = float((upper_band - lower_band) / middle_band) if middle_band > 0 else 0.0
    
    # 5. ATR Calculation
    atr_val = calculate_atr(df, current_price, period=min(atr_period, len(df)))
    
    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "rsi": round(rsi_val, 2),
        "macd": {
            "macd_line": round(macd_val, 4),
            "signal_line": round(sig_val, 4),
            "histogram": round(hist_val, 4)
        },
        "ema": {
            "ema_9": round(ema_9_val, 2),
            "ema_21": round(ema_21_val, 2),
            "trend": trend
        },
        "bollinger": {
            "upper": round(upper_band, 2),
            "middle": round(middle_band, 2),
            "lower": round(lower_band, 2),
            "bandwidth": round(bandwidth, 4)
        },
        "atr": round(atr_val, 2),
        "summary": {
            "candles_analyzed": len(df),
            "momentum": "OVERSOLD" if rsi_val < 30 else ("OVERBOUGHT" if rsi_val > 70 else "NEUTRAL")
        }
    }

def compute_technical_indicators(
    symbol: str, 
    candles: List[Dict[str, Any]], 
    config: Optional[IndicatorSettings] = None
) -> TechnicalIndicatorsResult:
    """
    Computes vectorized Technical Indicators (RSI, MACD, EMA 9/21, Bollinger Bands, ATR)
    from raw OHLCV candle dictionaries.
    
    Accepts an optional custom `IndicatorSettings` object and resolves period values 
    to hashable primitive integers before invoking the cached function.
    Returns a strictly validated Pydantic model `TechnicalIndicatorsResult`.
    """
    # Resolve settings object to primitive hashable ints/floats
    cfg = config if config is not None else indicator_settings
    
    # 1. Structured Logging & Minimum Candle Guard
    if not candles or len(candles) < 5:
        logger.warning(f"Insufficient candles provided for {symbol}: {len(candles) if candles else 0} (minimum required: 5)")
        last_price = candles[-1].get("close", 100.0) if candles else 100.0
        fallback_dict = {
            "symbol": symbol,
            "current_price": float(last_price),
            "rsi": 50.0,
            "macd": MACDResult(macd_line=0.0, signal_line=0.0, histogram=0.0),
            "ema": EMAResult(ema_9=float(last_price), ema_21=float(last_price), trend="NEUTRAL"),
            "bollinger": BollingerBandsResult(upper=float(last_price * 1.02), middle=float(last_price), lower=float(last_price * 0.98), bandwidth=0.04),
            "atr": max(round(float(last_price) * 0.001, 2), 0.01),
            "summary": {"error": "Insufficient candle data for calculation", "candles_analyzed": len(candles) if candles else 0}
        }
        return TechnicalIndicatorsResult.model_validate(fallback_dict)
        
    df = pd.DataFrame(candles)
    warnings = []
    
    # 2. Monotonicity & Chronological Order Validation
    if 'timestamp' in df.columns:
        df['dt'] = pd.to_datetime(df['timestamp'], errors='coerce', format='mixed')
        if not df['dt'].is_monotonic_increasing:
            logger.warning(f"Candles for {symbol} were out of order. Re-sorting chronologically.")
            warnings.append("Candles out of order - re-sorted chronologically")
            df.sort_values('dt', inplace=True)
            df.reset_index(drop=True, inplace=True)

    # 3. Numeric conversions & Leading-NaN handling
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[col] = 0.0

    df.ffill(inplace=True)
    df.bfill(inplace=True)
    df.fillna(0.0, inplace=True)

    # Prepare immutable tuples for LRU cached execution
    close_tuple = tuple(df['close'].tolist())
    high_tuple = tuple(df['high'].tolist())
    low_tuple = tuple(df['low'].tolist())
    open_tuple = tuple(df['open'].tolist())
    volume_tuple = tuple(df['volume'].tolist())
    last_timestamp = str(df['timestamp'].iloc[-1]) if 'timestamp' in df.columns else str(len(df))

    # Invoke LRU cached calculator with primitive hashable scalars ONLY
    raw_result = _cached_indicator_calc(
        symbol=symbol,
        last_timestamp=last_timestamp,
        candle_count=len(df),
        close_tuple=close_tuple,
        high_tuple=high_tuple,
        low_tuple=low_tuple,
        open_tuple=open_tuple,
        volume_tuple=volume_tuple,
        rsi_period=cfg.RSI_PERIOD,
        ema_fast=cfg.EMA_FAST_PERIOD,
        ema_slow=cfg.EMA_SLOW_PERIOD,
        macd_fast=cfg.MACD_FAST,
        macd_slow=cfg.MACD_SLOW,
        macd_signal=cfg.MACD_SIGNAL,
        bollinger_period=cfg.BOLLINGER_PERIOD,
        bollinger_std=cfg.BOLLINGER_STD_DEV,
        atr_period=cfg.ATR_PERIOD
    )
    
    if warnings:
        raw_result["summary"]["warnings"] = warnings

    # Return strictly validated Pydantic model for module boundary enforcement
    return TechnicalIndicatorsResult.model_validate(raw_result)
