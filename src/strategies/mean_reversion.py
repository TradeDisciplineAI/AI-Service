from typing import Dict, Any
from src.strategies.base_strategy import BaseStrategy
from src.schemas import TechnicalIndicatorsResult, StrategySignal, SignalAction

class MeanReversionStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "MeanReversion"

    def evaluate(
        self, 
        technicals: TechnicalIndicatorsResult, 
        market_scan: Dict[str, Any]
    ) -> StrategySignal:
        price = technicals.current_price
        lower_band = technicals.bollinger.lower
        rsi = technicals.rsi
        histogram = technicals.macd.histogram

        # Trigger conditions
        is_near_lower_band = price <= (lower_band * 1.005)
        is_oversold = rsi < 35.0
        is_histogram_reversing = histogram >= -0.5

        if is_near_lower_band and is_oversold and is_histogram_reversing:
            reason = (
                f"Mean Reversion triggered: Price ({price:.2f}) near lower Bollinger band ({lower_band:.2f}), "
                f"RSI oversold ({rsi:.1f}), MACD histogram turning up ({histogram:.4f})."
            )
            return StrategySignal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                score=0.85,
                reason=reason
            )

        return StrategySignal(
            strategy_name=self.name,
            action=SignalAction.HOLD,
            score=0.0,
            reason="Mean reversion oversold conditions not met."
        )
