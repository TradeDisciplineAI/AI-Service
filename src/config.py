import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndicatorSettings(BaseSettings):
    RSI_PERIOD: int = 14
    EMA_FAST_PERIOD: int = 9
    EMA_SLOW_PERIOD: int = 21
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    BOLLINGER_PERIOD: int = 20
    BOLLINGER_STD_DEV: float = 2.0
    ATR_PERIOD: int = 14

    # Caching
    INDICATOR_CACHE_SIZE: int = 1024

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class RAGSettings(BaseSettings):
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "trade_history"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_VECTOR_SIZE: int = 384
    QDRANT_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


indicator_settings = IndicatorSettings()
rag_settings = RAGSettings()


class RiskSettings(BaseSettings):
    MAX_POSITION_VALUE: float = 50000.00
    MAX_TRADE_RISK: float = 2000.00
    MIN_RISK_REWARD: float = 1.50
    MAX_STOP_DISTANCE_PERCENT: float = 10.0
    MAX_PORTFOLIO_EXPOSURE: float = 150000.00
    MAX_SINGLE_ASSET_EXPOSURE: float = 50000.00

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


risk_settings = RiskSettings()


class ExecutionSettings(BaseSettings):
    """Settings for Agent 5 paper execution and market-service integration."""

    MARKET_SERVICE_INTERNAL_URL: str = "http://localhost:8001"
    MARKET_SERVICE_INTERNAL_SECRET: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


execution_settings = ExecutionSettings()
