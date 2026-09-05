import logging
from datetime import UTC, datetime

from src.schemas import RAGQueryRequest, TradeExecutionRecord

logger = logging.getLogger(__name__)


def parse_utc_timestamp(ts: str) -> datetime:
    """
    Safely parses an ISO timestamp string into a UTC-aware datetime object.
    Prevents naive-vs-aware datetime comparison TypeErrors.
    """
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception as e:
        logger.warning(
            f"Error parsing timestamp '{ts}': {e}. Falling back to current UTC time."
        )
        return datetime.now(UTC)


def detect_discipline_mistakes(
    request: RAGQueryRequest, recent_trades: list[TradeExecutionRecord]
) -> list[str]:
    """
    Evaluates trader behavioral discipline risk patterns.

    Risk Flags:
    1. `REVENGE_TRADING_RISK`: Account-wide check! Flags if any loss trade (pnl < 0) was executed
       within 15 minutes (900 seconds) prior to the request timestamp.
    2. `FOMO_ENTRY_RISK`: Setup-level check! Flags if RSI > 70.0 combined with 24h price surge > 3.0%.
    3. `OVERTRADING_RISK`: Account-wide check! Flags if more than 5 trades were executed
       within the last 60 minutes (3600 seconds) prior to the request timestamp.
    """
    mistake_flags: list[str] = []
    req_dt = parse_utc_timestamp(request.timestamp)

    # 1. Revenge Trading Detector (Account-wide across all symbols)
    for trade in recent_trades:
        if trade.pnl < 0:
            trade_dt = parse_utc_timestamp(trade.timestamp)
            time_diff = (req_dt - trade_dt).total_seconds()
            if 0 <= time_diff <= 900:  # Within 15 minutes (900 seconds)
                mistake_flags.append("REVENGE_TRADING_RISK")
                logger.warning(
                    f"REVENGE_TRADING_RISK flagged: Loss trade '{trade.trade_id}' occurred {time_diff:.1f}s ago."
                )
                break

    # 2. FOMO Entry Detector (RSI > 70 & 24h price surge > 3%)
    if request.rsi > 70.0 and request.price_change_pct_24h > 3.0:
        mistake_flags.append("FOMO_ENTRY_RISK")
        logger.warning(
            f"FOMO_ENTRY_RISK flagged for {request.symbol}: RSI is {request.rsi} with +{request.price_change_pct_24h}% surge."
        )

    # 3. Overtrading Detector (Account-wide > 5 trades in last 60 minutes)
    trades_in_last_hour = 0
    for trade in recent_trades:
        trade_dt = parse_utc_timestamp(trade.timestamp)
        time_diff = (req_dt - trade_dt).total_seconds()
        if 0 <= time_diff <= 3600:  # Within 60 minutes
            trades_in_last_hour += 1

    if trades_in_last_hour > 5:
        mistake_flags.append("OVERTRADING_RISK")
        logger.warning(
            f"OVERTRADING_RISK flagged: {trades_in_last_hour} trades executed in the last 60 minutes (max allowed: 5)."
        )

    return mistake_flags
