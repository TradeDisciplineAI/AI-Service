from typing import Dict, Any
from src.strategies.base_strategy import BaseStrategy
from src.schemas import TechnicalIndicatorsResult, StrategySignal, SignalAction

class MomentumBreakoutStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "MomentumBreakout"

    def evaluate(
        self, 
        technicals: TechnicalIndicatorsResult, 
        market_scan: Dict[str, Any]
    ) -> StrategySignal:
        breakout = market_scan.get("breakout_detected", False)
        volume_surge = market_scan.get("volume_surge", False)
        ema_trend = technicals.ema.trend
        rsi = technicals.rsi

        # Trigger conditions
        is_breakout_or_volume = breakout or volume_surge
        is_uptrend = ema_trend in ["UPTREND", "BULLISH_CROSS"]
        is_healthy_rsi = 50.0 <= rsi <= 72.0  # Conservative upper buffer below 75

        if is_breakout_or_volume and is_uptrend and is_healthy_rsi:
            reason = (
                f"Momentum Breakout triggered: Volume/Price breakout active, "
                f"EMA trend is {ema_trend}, RSI is healthy ({rsi:.1f})."
            )
            return StrategySignal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                score=0.90,
                reason=reason
            )

        return StrategySignal(
            strategy_name=self.name,
            action=SignalAction.HOLD,
            score=0.0,
            reason="Breakout momentum conditions not met."
        )
