from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from uuid import UUID
from datetime import datetime

# API Request Blueprint
class AnalyzeRequest(BaseModel):
    ticker: str

class BatchAnalyzeRequest(BaseModel):
    tickers: List[str]


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

# === AGENT 6: LEARNING AGENT / RAG SCHEMAS ===

class TradeExecutionRecord(BaseModel):
    trade_id: str = Field(description="Unique trade UUID e.g., 'TRD-98124'")
    symbol: str = Field(description="Stock or Crypto symbol e.g., 'RELIANCE'")
    action: SignalAction = Field(description="Action BUY or SELL")
    entry_price: float = Field(gt=0.0, description="Actual entry fill price")
    exit_price: float = Field(gt=0.0, description="Actual exit fill price")
    pnl: float = Field(description="Realized PnL amount in currency")
    pnl_percentage: float = Field(description="Realized PnL percentage e.g., 5.2 or -2.1")
    strategy_used: str = Field(description="Strategy name e.g., 'MomentumBreakout'")
    emotion_note: Optional[str] = Field(default=None, description="Optional trader note or mistake flag e.g., 'FOMO buy after spike'")
    timestamp: str = Field(description="ISO timestamp of trade completion")

class RAGIngestResponse(BaseModel):
    status: str = Field(default="stored", description="Ingestion status e.g. 'stored'")
    trade_id: str = Field(description="Trade ID stored")
    vector_id: str = Field(description="Qdrant point ID")


class TradeProposalCreate(BaseModel):
    user_id: UUID
    portfolio_id: Optional[UUID] = None
    symbol: str
    action: SignalAction
    requested_quantity: int
    signal_id: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float
    primary_strategy: str


class TradeProposalResponse(BaseModel):
    id: UUID
    user_id: UUID
    portfolio_id: Optional[UUID] = None
    signal_id: str
    symbol: str
    action: SignalAction
    requested_quantity: int
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float
    primary_strategy: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }
class RAGQueryRequest(BaseModel):
    symbol: str = Field(description="Target stock or crypto symbol e.g., 'RELIANCE'")
    current_price: float = Field(gt=0.0, description="Current market price")
    rsi: float = Field(ge=0.0, le=100.0, description="Current RSI value")
    price_change_pct_24h: float = Field(default=0.0, description="24h price change percentage e.g. 3.5")
    strategy: str = Field(default="MomentumBreakout", description="Strategy being evaluated")
    timestamp: str = Field(description="ISO timestamp of evaluation request")
    recent_trades: Optional[List[TradeExecutionRecord]] = Field(default=None, description="Optional override for unit testing recent trades")

class RAGContextResponse(BaseModel):
    symbol: str = Field(description="Symbol evaluated")
    similar_trades_count: int = Field(ge=0, description="Number of similar historical setups retrieved from Qdrant")
    historical_win_rate: float = Field(ge=0.0, le=1.0, description="Historical win rate ratio")
    confidence_adjustment: float = Field(ge=-0.30, le=0.20, description="Bounded RAG confidence score adjustment")
    warning_flag: Optional[str] = Field(default=None, description="Formatted warning text string if win rate < 50% or risks active")
    mistake_flags: List[str] = Field(default_factory=list, description="List of detected behavioral risk flags e.g. ['REVENGE_TRADING_RISK']")


# === AGENT 4: RISK EVALUATION SCHEMAS ===

class RiskCheckResultSchema(BaseModel):
    check_name: str
    passed: bool
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    actual_value: str
    limit_value: str
    message: str

class RiskEvaluationResponse(BaseModel):
    id: UUID
    proposal_id: UUID
    decision: str  # "RISK_APPROVED", "RISK_REJECTED", "NEEDS_REVIEW"
    risk_score: int
    max_risk: float
    estimated_reward: float
    risk_reward_ratio: float
    portfolio_exposure: float
    checks: List[RiskCheckResultSchema]
    reasons: List[str]
    evaluated_at: datetime

    model_config = {
        "from_attributes": True
    }



# === AGENT 5: PAPER EXECUTION SCHEMAS ===

class PaperExecutionRequest(BaseModel):
    """Payload sent from AI-Service to market-service internal endpoint."""
    proposal_id: UUID
    execution_id: str
    portfolio_id: UUID
    user_id: UUID
    symbol: str
    action: str  # "BUY" | "SELL"
    requested_quantity: int
    stop_loss: float
    take_profit: float
    primary_strategy: str


class PaperExecutionResponse(BaseModel):
    """Response from market-service internal fill endpoint."""
    execution_id: str
    proposal_id: UUID
    symbol: str
    action: str
    filled_quantity: int
    execution_price: float
    executed_at: datetime


class ExecutionResultResponse(BaseModel):
    """Returned by POST /trade-proposals/{id}/execute on success."""
    execution_id: str
    proposal_id: UUID
    symbol: str
    action: str
    requested_quantity: int
    filled_quantity: int
    execution_price: float
    stop_loss: float
    take_profit: float
    primary_strategy: str
    executed_at: datetime
    proposal_status: str  # "EXECUTED"

    model_config = {
        "from_attributes": True
    }
