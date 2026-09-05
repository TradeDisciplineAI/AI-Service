import hashlib
import logging
import uuid
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.config import rag_settings
from src.schemas import TradeExecutionRecord

logger = logging.getLogger(__name__)

# Attempt fastembed import
try:
    from fastembed import TextEmbedding

    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False


class RAGStorageError(Exception):
    """Raised when Qdrant storage operations fail due to network or connection errors."""

    pass


class QdrantTradeVectorStore:
    """
    Agent 6 RAG Vector Database Store.
    Manages Qdrant 384-dim dense vector embeddings and metadata payload storage
    for completed trade executions.
    """

    def __init__(
        self, client: QdrantClient | None = None, collection_name: str | None = None
    ):
        self.collection_name = collection_name or rag_settings.QDRANT_COLLECTION
        self.vector_size = rag_settings.EMBEDDING_VECTOR_SIZE
        self.model_name = rag_settings.EMBEDDING_MODEL_NAME
        self.using_fallback: bool = False

        if client is not None:
            self.client = client
        else:
            try:
                self.client = QdrantClient(
                    host=rag_settings.QDRANT_HOST, port=rag_settings.QDRANT_PORT
                )
            except Exception as e:
                logger.critical(
                    f"CRITICAL: Could not connect to Qdrant host at {rag_settings.QDRANT_HOST}:{rag_settings.QDRANT_PORT}. Falling back to in-memory mode: {e}"
                )
                self.client = QdrantClient(":memory:")

        # Initialize Embedding Model with Loud Fallback Logging
        self.embed_model = None
        if _FASTEMBED_AVAILABLE:
            try:
                self.embed_model = TextEmbedding(model_name=self.model_name)
                logger.info(
                    f"Successfully loaded FastEmbed semantic model '{self.model_name}' (vector size: {self.vector_size})."
                )
            except Exception as e:
                self.using_fallback = True
                logger.critical(
                    f"CRITICAL RAG FALLBACK: Failed to load FastEmbed model '{self.model_name}': {e}. "
                    f"Fallback hashing vectorizer is ACTIVE. Semantic similarity queries will be degraded."
                )
        else:
            self.using_fallback = True
            logger.critical(
                "CRITICAL RAG FALLBACK: fastembed package is not installed. "
                "Fallback hashing vectorizer is ACTIVE. Semantic similarity queries will be degraded."
            )

        self.init_collection()

    def init_collection(self) -> None:
        """
        Ensures the target Qdrant vector collection exists with Cosine similarity metric.
        Safe and idempotent across service restarts.
        """
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info(
                    f"Creating Qdrant collection '{self.collection_name}' with vector size {self.vector_size}."
                )
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size, distance=Distance.COSINE
                    ),
                )
            else:
                logger.info(
                    f"Qdrant collection '{self.collection_name}' already exists. Skipping creation."
                )
        except Exception as e:
            logger.error(
                f"Error initializing Qdrant collection '{self.collection_name}': {e}"
            )
            raise RAGStorageError(
                f"Failed to initialize Qdrant collection: {str(e)}"
            ) from e

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generates a 384-dimensional dense vector embedding for input text.
        Uses FastEmbed semantic embedding model if available, else uses normalized hashing vectorizer fallback with CRITICAL logging.
        """
        if self.embed_model is not None and not self.using_fallback:
            try:
                embeddings = list(self.embed_model.embed([text]))
                vector = list(embeddings[0])
                if len(vector) == self.vector_size:
                    return [float(x) for x in vector]
            except Exception as e:
                logger.critical(
                    f"CRITICAL RAG RETRIEVAL FAILURE: FastEmbed runtime error: {e}. Falling back to hashing vectorizer."
                )

        # Deterministic 384-dim normalized hashing fallback vectorizer
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.RandomState(int.from_bytes(seed[:4], byteorder="big"))
        raw_vec = rng.randn(self.vector_size)
        norm = np.linalg.norm(raw_vec)
        unit_vec = (raw_vec / (norm if norm > 0 else 1.0)).tolist()
        return [float(x) for x in unit_vec]

    def record_to_text(self, record: TradeExecutionRecord) -> str:
        """
        Explicitly constructs a rich text string representation from TradeExecutionRecord fields.

        Field Details:
        - `outcome` is a derived string ("WIN", "LOSS", or "BREAKEVEN"). Uses epsilon tolerance (abs(pnl) < 1e-5)
          to prevent floating-point representation artifacts (e.g. 0.0000000000000001) from misclassifying flat trades.
        - `emotion_note` is conditionally appended only if present. If `record.emotion_note` is None or empty,
          the " | Market Note: ..." segment is omitted completely to prevent stringified "None" vector pollution.

        Lifecycle Note:
        When a trade is updated (e.g. initial entry -> exit/PnL filled), store_trade() re-embeds the updated
        text representation so the vector accurately reflects the complete trade outcome in semantic space.
        """
        # Epsilon-based outcome calculation robust against float precision artifacts
        if abs(record.pnl) < 1e-5:
            outcome = "BREAKEVEN"
        elif record.pnl > 0:
            outcome = "WIN"
        else:
            outcome = "LOSS"

        base_text = (
            f"Symbol: {record.symbol.upper()} | Action: {record.action.value} | Strategy: {record.strategy_used} | "
            f"Outcome: {outcome} | PnL: {record.pnl:.2f} ({record.pnl_percentage:.2f}%)"
        )

        # Omit Market Note segment when emotion_note is None or whitespace to avoid vector space pollution
        if record.emotion_note and record.emotion_note.strip():
            base_text += f" | Market Note: {record.emotion_note.strip()}"

        return base_text

    def get_vector_id_for_trade(self, trade_id: str) -> str:
        """
        Generates a deterministic Qdrant point UUID derived from trade_id.
        Ensures duplicate store_trade() calls for the same trade_id perform an idempotent upsert.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, trade_id))

    def store_trade(self, record: TradeExecutionRecord) -> str:
        """
        Stores a completed trade execution record into Qdrant.
        Uses deterministic point ID so re-storing identical trade_id updates the point idempotently.
        """
        text_repr = self.record_to_text(record)
        vector = self.generate_embedding(text_repr)
        vector_id = self.get_vector_id_for_trade(record.trade_id)

        payload = record.model_dump()
        payload["text_repr"] = text_repr

        point = PointStruct(id=vector_id, vector=vector, payload=payload)

        try:
            self.client.upsert(collection_name=self.collection_name, points=[point])
            logger.info(
                f"Stored trade execution '{record.trade_id}' in Qdrant with point_id '{vector_id}'."
            )
            return vector_id
        except Exception as e:
            logger.error(f"Failed to store trade '{record.trade_id}' in Qdrant: {e}")
            raise RAGStorageError(
                f"Qdrant storage failed for trade '{record.trade_id}': {str(e)}"
            ) from e

    def get_trade_by_id(self, trade_id: str) -> dict[str, Any] | None:
        """
        Retrieves a stored trade record by trade_id payload field.
        """
        try:
            records, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="trade_id", match=MatchValue(value=trade_id))
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if records:
                return records[0].payload
        except Exception as e:
            logger.error(f"Error fetching trade_id '{trade_id}' from Qdrant: {e}")
        return None

    def count_trades(self, symbol: str | None = None) -> int:
        """
        Returns total number of stored trades in collection, optionally filtered by symbol.
        """
        try:
            if symbol:
                count_res = self.client.count(
                    collection_name=self.collection_name,
                    count_filter=Filter(
                        must=[
                            FieldCondition(
                                key="symbol", match=MatchValue(value=symbol.upper())
                            )
                        ]
                    ),
                )
            else:
                count_res = self.client.count(collection_name=self.collection_name)
            return count_res.count
        except Exception as e:
            logger.error(f"Error counting trades in Qdrant: {e}")
            return 0
