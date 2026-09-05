import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.rag.evaluator import RAGEvaluator
from src.rag.vector_store import QdrantTradeVectorStore, RAGStorageError
from src.schemas import (
    RAGContextResponse,
    RAGIngestResponse,
    RAGQueryRequest,
    TradeExecutionRecord,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent6", tags=["Agent 6 RAG Engine"])

# Module-level singletons (lazy initialization)
_vector_store: QdrantTradeVectorStore | None = None
_evaluator: RAGEvaluator | None = None


def get_vector_store() -> QdrantTradeVectorStore:
    """
    Returns or lazily initializes the QdrantTradeVectorStore singleton.
    Allows dependency overrides in unit testing environments.
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantTradeVectorStore()
    return _vector_store


def get_evaluator(
    store: QdrantTradeVectorStore = Depends(get_vector_store),
) -> RAGEvaluator:
    """
    Returns or lazily initializes the RAGEvaluator singleton.
    """
    global _evaluator
    if _evaluator is None or _evaluator.vector_store != store:
        _evaluator = RAGEvaluator(vector_store=store)
    return _evaluator


@router.post(
    "/ingest", response_model=RAGIngestResponse, status_code=status.HTTP_201_CREATED
)
def ingest_trade(
    record: TradeExecutionRecord,
    store: QdrantTradeVectorStore = Depends(get_vector_store),
):
    """
    Ingests a completed trade execution fill record into Qdrant Vector DB memory.
    Catches RAGStorageError and raises HTTP 503 Service Unavailable cleanly.
    """
    try:
        vector_id = store.store_trade(record)
        return RAGIngestResponse(
            status="stored", trade_id=record.trade_id, vector_id=vector_id
        )
    except RAGStorageError as e:
        logger.error(f"Storage failure ingesting trade '{record.trade_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qdrant Vector DB Storage Unavailable: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error ingesting trade '{record.trade_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error ingesting trade: {str(e)}",
        ) from e


@router.post(
    "/evaluate", response_model=RAGContextResponse, status_code=status.HTTP_200_OK
)
def evaluate_trade_setup(
    request: RAGQueryRequest, ev: RAGEvaluator = Depends(get_evaluator)
):
    """
    Evaluates a setup memory request for Agent 3:
    Retrieves recent trade history, detects behavioral discipline mistakes,
    queries vector memory for similar historical setups, and computes a bounded confidence adjustment.
    Catches RAGStorageError and raises HTTP 503 Service Unavailable cleanly.
    """
    try:
        response = ev.evaluate_setup(request)
        return response
    except RAGStorageError as e:
        logger.error(f"Storage failure evaluating setup for '{request.symbol}': {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qdrant Vector DB Storage Unavailable: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error evaluating setup for '{request.symbol}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error evaluating trade setup: {str(e)}",
        ) from e
