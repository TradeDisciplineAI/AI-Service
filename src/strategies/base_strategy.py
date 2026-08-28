from abc import ABC, abstractmethod
from typing import Any

from src.schemas import StrategySignal, TechnicalIndicatorsResult


class BaseStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name identifier."""
        pass

    @abstractmethod
    def evaluate(
        self, technicals: TechnicalIndicatorsResult, market_scan: dict[str, Any]
    ) -> StrategySignal:
        """
        Evaluates current technical indicators and market scan flags,
        returning a StrategySignal (action, score, reason).
        """
        pass
