from abc import ABC, abstractmethod
from typing import Dict, Any
from src.schemas import TechnicalIndicatorsResult, StrategySignal

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name identifier."""
        pass

    @abstractmethod
    def evaluate(
        self, 
        technicals: TechnicalIndicatorsResult, 
        market_scan: Dict[str, Any]
    ) -> StrategySignal:
        """
        Evaluates current technical indicators and market scan flags,
        returning a StrategySignal (action, score, reason).
        """
        pass
