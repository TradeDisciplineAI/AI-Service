import uuid
import logging
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from src.config import rag_settings
from src.schemas import TradeExecutionRecord

logger = logging.getLogger(__name__)

# Attempt fastembed import, fallback to deterministic hash vectorizer if model download fails or offline
try:
    from fastembed import TextEmbedding
    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False


class QdrantTradeVectorStore:
    """
    Agent 6 RAG Vector Database Store.
    Manages Qdrant 384-dim dense vector embeddings and metadata payload storage
    for completed trade executions.
    """
    def __init__(self, client: Optional[QdrantClient] = None, collection_name: Optional[str] = None):
        self.collection_name = collection_name or rag_settings.QDRANT_COLLECTION
        self.vector_size = rag_settings.EMBEDDING_VECTOR_SIZE

        if client is not None:
            self.client = client
        else:
            try:
                self.client = QdrantClient(host=rag_settings.QDRANT_HOST, port=rag_settings.QDRANT_PORT)
            except Exception as e:
                logger.warning(f"Could not connect to Qdrant host at {rag_settings.QDRANT_HOST}:{rag_settings.QDRANT_PORT}. Falling back to in-memory mode: {e}")
                self.client = QdrantClient(":memory:")

        # Initialize Embedding Model
        self.embed_model = None
        if _FASTEMBED_AVAILABLE:
            try:
                self.embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            except Exception as e:
                logger.warning(f"Could not load FastEmbed model BAAI/bge-small-en-v1.5: {e}. Using deterministic vectorizer fallback.")

        self.init_collection()

    def init_collection(self) -> None:
        """
        Ensures the target Qdrant vector collection exists with Cosine similarity metric.
        """
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info(f"Creating Qdrant collection '{self.collection_name}' with vector size {self.vector_size}.")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection '{self.collection_name}': {e}")
            raise e

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional dense vector embedding for the input text string.
        Uses FastEmbed if loaded, else uses normalized hashing vectorizer fallback.
        """
        if self.embed_model is not None:
            try:
                embeddings = list(self.embed_model.embed([text]))
                vector = list(embeddings[0])
                if len(vector) == self.vector_size:
                    return [float(x) for x in vector]
            except Exception as e:
                logger.warning(f"FastEmbed embedding generation failed: {e}. Using deterministic fallback vectorizer.")

        # Deterministic 384-dim normalized hashing fallback vectorizer
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.RandomState(int.from_bytes(seed[:4], byteorder="big"))
        raw_vec = rng.randn(self.vector_size)
        norm = np.linalg.norm(raw_vec)
        unit_vec = (raw_vec / (norm if norm > 0 else 1.0)).tolist()
        return [float(x) for x in unit_vec]

    def record_to_text(self, record: TradeExecutionRecord) -> str:
        """
        Converts a TradeExecutionRecord into a rich text string for dense vector embedding.
        """
        outcome = "WIN" if record.pnl > 0 else ("LOSS" if record.pnl < 0 else "BREAKEVEN")
        note = f" Note: {record.emotion_note}" if record.emotion_note else ""
        return (
            f"Symbol: {record.symbol.upper()} Action: {record.action} Outcome: {outcome} "
            f"PnL: {record.pnl:.2f} ({record.pnl_percentage:.2f}%) Strategy: {record.strategy_used}{note}"
        )

    def store_trade(self, record: TradeExecutionRecord) -> str:
        """
        Stores a completed trade execution record into Qdrant.
        Returns the generated Qdrant Point UUID string.
        """
        text_repr = self.record_to_text(record)
        vector = self.generate_embedding(text_repr)
        vector_id = str(uuid.uuid4())

        payload = record.model_dump()
        payload["text_repr"] = text_repr

        point = PointStruct(
            id=vector_id,
            vector=vector,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        logger.info(f"Stored trade execution '{record.trade_id}' in Qdrant with point_id '{vector_id}'.")
        return vector_id

    def get_trade_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a stored trade record by trade_id payload field.
        """
        try:
            records, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="trade_id", match=MatchValue(value=trade_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            if records:
                return records[0].payload
        except Exception as e:
            logger.error(f"Error fetching trade_id '{trade_id}' from Qdrant: {e}")
        return None

    def count_trades(self, symbol: Optional[str] = None) -> int:
        """
        Returns total number of stored trades in collection, optionally filtered by symbol.
        """
        try:
            if symbol:
                count_res = self.client.count(
                    collection_name=self.collection_name,
                    count_filter=Filter(
                        must=[FieldCondition(key="symbol", match=MatchValue(value=symbol.upper()))]
                    )
                )
            else:
                count_res = self.client.count(collection_name=self.collection_name)
            return count_res.count
        except Exception as e:
            logger.error(f"Error counting trades in Qdrant: {e}")
            return 0
