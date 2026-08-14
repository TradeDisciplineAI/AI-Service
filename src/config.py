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

indicator_settings = IndicatorSettings()
