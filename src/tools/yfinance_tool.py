import logging
from datetime import UTC, datetime

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_market_data(ticker: str, limit: int = 30) -> dict:
    """Fetches 5-minute intraday market data (defaults to 30 recent candles for technical analysis)."""
    logger.info(f"Scanning intraday market data for {ticker} (limit={limit})")

    try:
        stock = yf.Ticker(ticker)
        # Pull 5-minute candles for the last 5 days to ensure sufficient candle history
        df = stock.history(period="5d", interval="5m")

        if df.empty:
            # Fallback to period="1d" if period="5d" returned empty
            df = stock.history(period="1d", interval="5m")

        if df.empty:
            return {"error": "No data found"}

        candles = []
        text_summary = []

        # Grab the last 30 candles (or specified limit) for indicator calculation
        recent_df = df.tail(limit)
        for date, row in recent_df.iterrows():
            time_str = (
                date.strftime("%H:%M") if hasattr(date, "strftime") else str(date)
            )
            candle = {
                "timestamp": time_str,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            candles.append(candle)
            text_summary.append(
                f"[{time_str}] Close: {candle['close']} | Vol: {candle['volume']}"
            )

        current_price = candles[-1]["close"]

        return {
            "symbol": ticker,
            "current_price": current_price,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ohlcv_candles": candles,
            "text_for_ai": "\n".join(text_summary[-4:]),
        }

    except Exception as e:
        logger.error(f"yfinance Error for {ticker}: {e}")
        return {"error": str(e)}
