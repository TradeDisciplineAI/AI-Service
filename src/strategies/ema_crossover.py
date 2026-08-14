from typing import Dict, Any
from src.strategies.base_strategy import BaseStrategy
from src.schemas import TechnicalIndicatorsResult, StrategySignal, SignalAction

class EMACrossoverStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "EMACrossover"

    def evaluate(
        self, 
        technicals: TechnicalIndicatorsResult, 
        market_scan: Dict[str, Any]
    ) -> StrategySignal:
        ema_trend = technicals.ema.trend
        ema_9 = technicals.ema.ema_9
        ema_21 = technicals.ema.ema_21
        rsi = technicals.rsi

        # Trigger conditions
        is_bullish_cross = (ema_trend == "BULLISH_CROSS") or (ema_trend == "UPTREND" and ema_9 > ema_21)
        is_sufficient_momentum = rsi >= 45.0

        if is_bullish_cross and is_sufficient_momentum:
            reason = (
                f"EMA Crossover triggered: 9 EMA ({ema_9:.2f}) > 21 EMA ({ema_21:.2f}) "
                f"trend is {ema_trend}, RSI momentum is {rsi:.1f}."
            )
            return StrategySignal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                score=0.80,
                reason=reason
            )

        return StrategySignal(
            strategy_name=self.name,
            action=SignalAction.HOLD,
            score=0.0,
            reason="EMA crossover trend conditions not met."
        )
