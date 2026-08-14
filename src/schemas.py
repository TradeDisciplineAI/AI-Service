from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# API Request Blueprint
class AnalyzeRequest(BaseModel):
    ticker: str

# Candle Blueprint
class OHLCVCandle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

# MACD Blueprint
class MACDResult(BaseModel):
    macd_line: float
    signal_line: float
    histogram: float

# EMA Blueprint
class EMAResult(BaseModel):
    ema_9: float
    ema_21: float
    trend: str  # "BULLISH_CROSS", "BEARISH_CROSS", "UPTREND", "DOWNTREND", "NEUTRAL"

# Bollinger Bands Blueprint
class BollingerBandsResult(BaseModel):
    upper: float
    middle: float
    lower: float
    bandwidth: float

# Complete Technical Analysis Output Contract
class TechnicalIndicatorsResult(BaseModel):
    symbol: str
    current_price: float
    rsi: float
    macd: MACDResult
    ema: EMAResult
    bollinger: BollingerBandsResult
    atr: float
    summary: Dict[str, Any] = Field(default_factory=dict)