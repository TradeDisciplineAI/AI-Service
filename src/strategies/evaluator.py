import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple
from src.schemas import (
    TechnicalIndicatorsResult, 
    TradeSignal, 
    SignalAction, 
    ConfidenceMode, 
    StrategySignal
)
from src.strategies.base_strategy import BaseStrategy
from src.strategies.momentum_breakout import MomentumBreakoutStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.ema_crossover import EMACrossoverStrategy

logger = logging.getLogger(__name__)

# Strategy Priority for Deterministic Tie-Breaking
STRATEGY_PRIORITY = {
    "MomentumBreakout": 1,
    "MeanReversion": 2,
    "EMACrossover": 3
}

class StrategyEvaluator:
    def __init__(self, strategies: Optional[List[BaseStrategy]] = None):
        self.strategies = strategies or [
            MomentumBreakoutStrategy(),
            MeanReversionStrategy(),
            EMACrossoverStrategy()
        ]

    def _detect_input_availability(
        self, 
        sentiment: Optional[Dict[str, Any]], 
        rag_context: Optional[Dict[str, Any]]
    ) -> Tuple[bool, bool, ConfidenceMode, float, Dict[str, float], float, float]:
        """
        Detects availability of Agent 2 (Sentiment) and Agent 6 (RAG) inputs.
        Returns: (has_sentiment, has_rag, mode, required_threshold, weights, norm_sentiment_score, norm_rag_score)
        """
        has_sentiment = False
        norm_sentiment = 0.50  # Neutral fallback
        
        if (
            sentiment is not None 
            and isinstance(sentiment, dict) 
            and "error" not in sentiment
        ):
            # Check for sentiment_score or conviction_score
            raw_score = sentiment.get("sentiment_score")
            if raw_score is None and "conviction_score" in sentiment:
                # Agent 2 outputs conviction_score 1..10
                raw_score = (sentiment["conviction_score"] / 5.0) - 1.0  # Convert 1..10 to -1.0..+1.0
                
            if raw_score is not None:
                has_sentiment = True
                # Clamp raw sentiment to [-1.0, 1.0]
                clamped_score = max(-1.0, min(1.0, float(raw_score)))
                # Normalize to [0.0, 1.0]
                norm_sentiment = (clamped_score + 1.0) / 2.0

        has_rag = False
        norm_rag = 0.50  # Neutral fallback
        
        if (
            rag_context is not None 
            and isinstance(rag_context, dict) 
            and "error" not in rag_context
        ):
            rag_adj = rag_context.get("confidence_adjustment")
            # Explicit non-None check (0.0 IS a valid RAG adjustment)
            if rag_adj is not None:
                has_rag = True
                # Clamp RAG score to [0.0, 1.0]
                norm_rag = max(0.0, min(1.0, 0.50 + float(rag_adj)))

        # Mode, Weights, and Required Threshold Determination
        if has_sentiment and has_rag:
            mode = ConfidenceMode.FULL_INTEGRATION
            threshold = 0.65
            weights = {"ta": 0.50, "sentiment": 0.30, "rag": 0.20}
        elif has_sentiment and not has_rag:
            mode = ConfidenceMode.RAG_OFFLINE
            threshold = 0.75
            weights = {"ta": 0.625, "sentiment": 0.375, "rag": 0.0}
        elif not has_sentiment and has_rag:
            mode = ConfidenceMode.SENTIMENT_OFFLINE
            threshold = 0.75
            weights = {"ta": 0.714, "sentiment": 0.0, "rag": 0.286}
        else:
            mode = ConfidenceMode.TECHNICAL_ONLY
            threshold = 0.80
            weights = {"ta": 1.000, "sentiment": 0.0, "rag": 0.0}

        return has_sentiment, has_rag, mode, threshold, weights, norm_sentiment, norm_rag

    def evaluate_all(
        self,
        technicals: TechnicalIndicatorsResult,
        market_scan: Dict[str, Any],
        sentiment_analysis: Optional[Dict[str, Any]] = None,
        rag_context: Optional[Dict[str, Any]] = None
    ) -> TradeSignal:
        """
        Master Agent 3 Evaluator:
        1. Runs all strategies concurrently.
        2. Applies deterministic tie-breaking for primary strategy selection.
        3. Computes ATR-based Stop Loss & 1:2 R:R Take Profit targets.
        4. Detects input degradation and applies Dynamic Threshold Scaling & Weight Renormalization.
        5. Enforces confidence & R:R gates before emitting BUY/HOLD.
        """
        symbol = technicals.symbol
        entry_price = technicals.current_price
        atr = technicals.atr

        # 1. Evaluate All Strategies
        strategy_signals: List[StrategySignal] = []
        active_signals: List[StrategySignal] = []

        for strat in self.strategies:
            try:
                sig = strat.evaluate(technicals, market_scan)
                strategy_signals.append(sig)
                if sig.action == SignalAction.BUY and sig.score > 0.0:
                    active_signals.append(sig)
            except Exception as e:
                logger.error(f"Error evaluating strategy {strat.name}: {e}")

        # 2. Select Winning Strategy & Determine Score_TA (Zero-Strategy Guard)
        reasons = []
        if not active_signals:
            score_ta = 0.0
            primary_strategy = "None"
            reasons.append("No active technical strategies triggered BUY signal.")
        else:
            # Sort by score descending, then by priority index ascending (tie-breaking)
            active_signals.sort(
                key=lambda s: (-s.score, STRATEGY_PRIORITY.get(s.strategy_name, 99))
            )
            winning_sig = active_signals[0]
            score_ta = winning_sig.score
            primary_strategy = winning_sig.strategy_name
            reasons.append(winning_sig.reason)

        # 3. Detect Mode, Renormalized Weights, and Required Threshold
        (
            has_sent, 
            has_rag, 
            mode, 
            threshold, 
            weights, 
            norm_sentiment, 
            norm_rag
        ) = self._detect_input_availability(sentiment_analysis, rag_context)

        # 4. Compute Composite Confidence Score
        confidence_final = (
            (weights["ta"] * score_ta) +
            (weights["sentiment"] * norm_sentiment) +
            (weights["rag"] * norm_rag)
        )
        confidence_final = max(0.0, min(1.0, round(confidence_final, 4)))

        # 5. Target Price Math (1.5x ATR Stop Loss & 1:2 R:R Take Profit)
        stop_loss = round(entry_price - (1.5 * atr), 2)
        risk_amount = entry_price - stop_loss
        if risk_amount <= 0:
            risk_amount = max(entry_price * 0.005, 0.01)
            stop_loss = round(entry_price - risk_amount, 2)

        take_profit = round(entry_price + (2.0 * risk_amount), 2)
        risk_reward_ratio = round((take_profit - entry_price) / (entry_price - stop_loss), 2)

        # 6. Execution Gate (Confidence >= Threshold AND R:R >= 1.5)
        is_confidence_passed = confidence_final >= threshold
        is_rr_passed = risk_reward_ratio >= 1.5

        if active_signals and is_confidence_passed and is_rr_passed:
            final_action = SignalAction.BUY
            reasons.append(f"Confidence score {confidence_final:.2f} met required threshold ({threshold:.2f}) under mode {mode.value}.")
        else:
            final_action = SignalAction.HOLD
            if not active_signals:
                reasons.append("Filtered to HOLD: No strategy triggered.")
            elif not is_confidence_passed:
                reasons.append(f"Filtered to HOLD: Confidence ({confidence_final:.2f}) below required threshold ({threshold:.2f}) for mode {mode.value}.")
            elif not is_rr_passed:
                reasons.append(f"Filtered to HOLD: Risk:Reward ({risk_reward_ratio:.2f}) below 1.5 minimum limit.")

        signal_id = f"SIG-{uuid.uuid4().hex[:8].upper()}"

        return TradeSignal(
            signal_id=signal_id,
            symbol=symbol,
            action=final_action,
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=risk_reward_ratio,
            confidence_score=confidence_final,
            confidence_mode=mode,
            required_threshold=threshold,
            primary_strategy=primary_strategy,
            reasons=reasons,
            technicals_summary={
                "rsi": technicals.rsi,
                "ema_trend": technicals.ema.trend,
                "macd_histogram": technicals.macd.histogram,
                "bollinger_bandwidth": technicals.bollinger.bandwidth,
                "atr": technicals.atr
            }
        )
