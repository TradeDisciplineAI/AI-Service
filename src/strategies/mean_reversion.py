from typing import Any

from src.schemas import SignalAction, StrategySignal, TechnicalIndicatorsResult
from src.strategies.base_strategy import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "MeanReversion"

    def evaluate(
        self, technicals: TechnicalIndicatorsResult, market_scan: dict[str, Any]
    ) -> StrategySignal:
        price = technicals.current_price
        lower_band = technicals.bollinger.lower
        upper_band = technicals.bollinger.upper
        rsi = technicals.rsi
        histogram = technicals.macd.histogram

        is_near_lower_band = price <= (lower_band * 1.005)
        is_oversold = rsi < 35.0
        is_histogram_reversing_up = histogram >= -0.5

        is_near_upper_band = price >= (upper_band * 0.995)
        is_overbought = rsi > 65.0
        is_histogram_reversing_down = histogram <= 0.5

        if is_near_lower_band and is_oversold and is_histogram_reversing_up:
            reason = (
                f"Mean Reversion triggered: Price ({price:.2f}) near lower Bollinger band ({lower_band:.2f}), "
                f"RSI oversold ({rsi:.1f}), MACD histogram turning up ({histogram:.4f})."
            )
            return StrategySignal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                score=0.85,
                reason=reason,
            )

        if is_near_upper_band and is_overbought and is_histogram_reversing_down:
            reason = (
                f"Mean Reversion (Bearish) triggered: Price ({price:.2f}) near upper Bollinger band ({upper_band:.2f}), "
                f"RSI overbought ({rsi:.1f}), MACD histogram turning down ({histogram:.4f})."
            )
            return StrategySignal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                score=0.85,
                reason=reason,
            )

        return StrategySignal(
            strategy_name=self.name,
            action=SignalAction.HOLD,
            score=0.0,
            reason="Mean reversion conditions not met.",
        )
