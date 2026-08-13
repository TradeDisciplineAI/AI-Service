import yfinance as yf
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def fetch_market_data(ticker: str) -> dict:
    """Fetches 5-minute intraday data."""
    logger.info(f"Agent 1: Scanning intraday market data for {ticker}")
    
    try:
        stock = yf.Ticker(ticker)
        # Pull 5-minute candles for the last 1 day
        df = stock.history(period="1d", interval="5m")
        
        if df.empty:
            return {"error": "No data found"}
            
        candles = []
        text_summary = []
        
        # Grab the last 4 candles
        recent_df = df.tail(4)
        for date, row in recent_df.iterrows():
            candle = {
                "timestamp": date.strftime('%H:%M'),
                "open": round(row['Open'], 2),
                "high": round(row['High'], 2),
                "low": round(row['Low'], 2),
                "close": round(row['Close'], 2),
                "volume": int(row['Volume'])
            }
            candles.append(candle)
            text_summary.append(f"[{candle['timestamp']}] Close: {candle['close']} | Vol: {candle['volume']}")
            
        current_price = candles[-1]['close']
        
        return {
            "symbol": ticker,
            "current_price": current_price,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ohlcv_candles": candles,
            "text_for_ai": "\n".join(text_summary) # The AI only needs to read this string
        }
        
    except Exception as e:
        logger.error(f"yfinance Error: {e}")
        return {"error": str(e)}