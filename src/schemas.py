from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

# API Request Blueprint
class AnalyzeRequest(BaseModel):
    ticker: str

# Agent 3 Master REST Request Blueprint
class Agent3EvaluateRequest(BaseModel):
    ticker: str = Field(description="Stock or Crypto symbol e.g., 'RELIANCE'")
    market_scan_json: Optional[Dict[str, Any]] = Field(default=None, description="Optional pre-fetched candles or Agent 1 scan output")
    sentiment_analysis_json: Optional[Dict[str, Any]] = Field(default=None, description="Optional pre-fetched Agent 2 sentiment analysis")
    rag_context_json: Optional[Dict[str, Any]] = Field(default=None, description="Optional pre-fetched Agent 6 RAG context")

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

# Signal Action Enum
class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

# Auditable Operating Confidence Mode Enum
class ConfidenceMode(str, Enum):
    FULL_INTEGRATION = "FULL_INTEGRATION"
    RAG_OFFLINE = "RAG_OFFLINE"
    SENTIMENT_OFFLINE = "SENTIMENT_OFFLINE"
    TECHNICAL_ONLY = "TECHNICAL_ONLY"

# Individual Strategy Evaluation Output
class StrategySignal(BaseModel):
    strategy_name: str
    action: SignalAction
    score: float = Field(ge=0.0, le=1.0)
    reason: str

# Master Agent 3 Trade Signal Output Contract
class TradeSignal(BaseModel):
    signal_id: str
    symbol: str
    action: SignalAction
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_mode: ConfidenceMode
    required_threshold: float
    primary_strategy: str
    reasons: List[str] = Field(default_factory=list)
    technicals_summary: Dict[str, Any] = Field(default_factory=dict)