from unittest.mock import patch, MagicMock
import pandas as pd
from src.tools.yfinance_tool import fetch_market_data

def test_fetch_market_data_returns_at_least_30_candles():
    # Mock yfinance ticker history returning 35 rows
    dates = pd.date_range(end=pd.Timestamp.now(), periods=35, freq="5min")
    mock_df = pd.DataFrame({
        "Open": [100.0 + i for i in range(35)],
        "High": [105.0 + i for i in range(35)],
        "Low": [99.0 + i for i in range(35)],
        "Close": [102.0 + i for i in range(35)],
        "Volume": [1000 + i * 10 for i in range(35)],
    }, index=dates)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = fetch_market_data("TSLA")

    assert "error" not in result
    assert result["symbol"] == "TSLA"
    assert len(result["ohlcv_candles"]) == 30
    assert result["current_price"] == 136.0  # 102 + 34
    
    first_candle = result["ohlcv_candles"][0]
    assert "timestamp" in first_candle
    assert "open" in first_candle
    assert "high" in first_candle
    assert "low" in first_candle
    assert "close" in first_candle
    assert "volume" in first_candle

def test_fetch_market_data_handles_empty_response():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = fetch_market_data("INVALID_TICKER")

    assert "error" in result
    assert result["error"] == "No data found"

