import logging
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.rag.mistake_detector import detect_discipline_mistakes, parse_utc_timestamp
from src.rag.vector_store import QdrantTradeVectorStore
from src.schemas import RAGContextResponse, RAGQueryRequest, TradeExecutionRecord

logger = logging.getLogger(__name__)

# Epsilon tolerance guarding against float precision artifacts in boundary comparisons
WIN_RATE_EPSILON: float = 1e-9


class RAGEvaluator:
    """
    Agent 6 RAG Evaluator.
    Retrieves recent trade history via Qdrant payload scroll, detects behavioral discipline mistakes,
    queries vector memory for similar historical setups, and computes a bounded confidence adjustment
    (-0.30 to +0.20) for Agent 3.
    """

    def __init__(self, vector_store: QdrantTradeVectorStore | None = None):
        self.vector_store = vector_store or QdrantTradeVectorStore()

    def get_recent_trades(
        self, query_timestamp: str, window_minutes: int = 60
    ) -> list[TradeExecutionRecord]:
        """
        Retrieves account-wide recent trade execution records executed within the last window_minutes
        via payload-filtered Qdrant scroll.
        """
        recent_records: list[TradeExecutionRecord] = []
        req_dt = parse_utc_timestamp(query_timestamp)

        try:
            records, _ = self.vector_store.client.scroll(
                collection_name=self.vector_store.collection_name,
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            for point in records:
                payload = point.payload or {}
                trade_ts = payload.get("timestamp")
                if trade_ts:
                    trade_dt = parse_utc_timestamp(trade_ts)
                    time_diff = (req_dt - trade_dt).total_seconds()
                    if 0 <= time_diff <= (window_minutes * 60):
                        try:
                            # Reconstruct TradeExecutionRecord model
                            clean_payload = {
                                k: v for k, v in payload.items() if k != "text_repr"
                            }
                            record = TradeExecutionRecord.model_validate(clean_payload)
                            recent_records.append(record)
                        except Exception as val_err:
                            logger.warning(
                                f"Error validating payload into TradeExecutionRecord: {val_err}"
                            )
        except Exception as e:
            logger.error(f"Error scrolling recent trades from Qdrant: {e}")

        return recent_records

    def query_similar_setups(
        self, symbol: str, text_query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Queries Qdrant vector memory for top_k similar past trade setups for the specified symbol.
        Supports both query_points() and search() API methods across QdrantClient versions.
        """
        similar_trades: list[dict[str, Any]] = []
        try:
            query_vector = self.vector_store.generate_embedding(text_query)
            query_filter = Filter(
                must=[
                    FieldCondition(key="symbol", match=MatchValue(value=symbol.upper()))
                ]
            )

            results = []
            if hasattr(self.vector_store.client, "query_points"):
                response = self.vector_store.client.query_points(
                    collection_name=self.vector_store.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
                results = getattr(response, "points", [])
            elif hasattr(self.vector_store.client, "search"):
                results = self.vector_store.client.search(
                    collection_name=self.vector_store.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )

            for res in results:
                payload = getattr(res, "payload", None)
                if payload:
                    similar_trades.append(payload)
        except Exception as e:
            logger.error(f"Error querying similar setups from Qdrant for {symbol}: {e}")

        return similar_trades

    def calculate_win_rate_adjustment(self, win_rate: float) -> float:
        """
        Computes base confidence adjustment from historical win rate using top-down boundary-safe math.

        Bands:
        - Win Rate >= 0.80 - 1e-9 -> +0.20
        - Win Rate >= 0.60 - 1e-9 -> +0.10
        - 0.40 < Win Rate < 0.60   ->  0.00
        - Win Rate <= 0.40 + 1e-9 -> -0.15
        - Win Rate <= 0.20 + 1e-9 -> -0.30
        """
        if win_rate >= (0.80 - WIN_RATE_EPSILON):
            return 0.20
        elif win_rate >= (0.60 - WIN_RATE_EPSILON):
            return 0.10
        elif win_rate <= (0.20 + WIN_RATE_EPSILON):
            return -0.30
        elif win_rate <= (0.40 + WIN_RATE_EPSILON):
            return -0.15
        else:
            return 0.00

    def evaluate_setup(self, request: RAGQueryRequest) -> RAGContextResponse:
        """
        Evaluates setup memory and behavioral discipline context for Agent 3.
        """
        # 1. Retrieve Recent Trades (Self-contained Qdrant scroll query unless test override provided)
        if request.recent_trades is not None:
            recent_trades = request.recent_trades
        else:
            recent_trades = self.get_recent_trades(request.timestamp, window_minutes=60)

        # 2. Detect Discipline Mistakes
        mistake_flags = detect_discipline_mistakes(request, recent_trades)

        # 3. Query Qdrant for Similar Past Setups
        query_text = f"Symbol: {request.symbol.upper()} | Action: BUY | Strategy: {request.strategy}"
        similar_setups = self.query_similar_setups(request.symbol, query_text, top_k=5)
        similar_trades_count = len(similar_setups)

        # 4. Zero-Similar-Trades Neutral Fallback Guard
        if similar_trades_count == 0:
            historical_win_rate = 0.50
            base_adjustment = 0.00
            logger.info(
                f"Zero similar past trades found in Qdrant for {request.symbol}. Applying neutral fallback (Win Rate: 0.50, Adj: 0.00)."
            )
        else:
            # Calculate Win Rate from retrieved similar setups
            wins = sum(1 for trade in similar_setups if trade.get("pnl", 0.0) > 0)
            historical_win_rate = wins / float(similar_trades_count)
            base_adjustment = self.calculate_win_rate_adjustment(historical_win_rate)

        # 5. Apply Mistake Penalty Deductions (-0.10 additively per active flag)
        penalty_deduction = len(mistake_flags) * 0.10
        total_adjustment = base_adjustment - penalty_deduction

        # 6. Clamp Final Confidence Adjustment Strictly to [-0.30, +0.20]
        clamped_adjustment = max(-0.30, min(0.20, total_adjustment))

        # 7. Multi-Reason Warning Flag Formatting
        warning_reasons: list[str] = []
        if similar_trades_count > 0 and historical_win_rate < 0.50:
            warning_reasons.append(
                f"Low historical win rate ({historical_win_rate * 100:.1f}%)"
            )
        if mistake_flags:
            warning_reasons.append(
                f"Active Discipline Risks: {', '.join(mistake_flags)}"
            )

        warning_flag = (
            "WARNING: " + "; ".join(warning_reasons) if warning_reasons else None
        )

        return RAGContextResponse(
            symbol=request.symbol.upper(),
            similar_trades_count=similar_trades_count,
            historical_win_rate=round(historical_win_rate, 4),
            confidence_adjustment=round(clamped_adjustment, 4),
            warning_flag=warning_flag,
            mistake_flags=mistake_flags,
        )
