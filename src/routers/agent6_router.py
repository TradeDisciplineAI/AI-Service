import logging
from fastapi import APIRouter, HTTPException, status
from src.schemas import TradeExecutionRecord, RAGIngestResponse, RAGQueryRequest, RAGContextResponse
from src.rag.vector_store import QdrantTradeVectorStore, RAGStorageError
from src.rag.evaluator import RAGEvaluator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent6", tags=["Agent 6 RAG Engine"])

# Initialize storage and evaluator singletons
vector_store = QdrantTradeVectorStore()
evaluator = RAGEvaluator(vector_store=vector_store)


@router.post("/ingest", response_model=RAGIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_trade(record: TradeExecutionRecord):
    """
    Ingests a completed trade execution fill record into Qdrant Vector DB memory.
    Catches RAGStorageError and raises HTTP 503 Service Unavailable cleanly.
    """
    try:
        response = vector_store.store_trade(record)
        return response
    except RAGStorageError as e:
        logger.error(f"Storage failure ingesting trade '{record.trade_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qdrant Vector DB Storage Unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error ingesting trade '{record.trade_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error ingesting trade: {str(e)}"
        )


@router.post("/evaluate", response_model=RAGContextResponse, status_code=status.HTTP_200_OK)
def evaluate_trade_setup(request: RAGQueryRequest):
    """
    Evaluates a setup memory request for Agent 3:
    Retrieves recent trade history, detects behavioral discipline mistakes,
    queries vector memory for similar historical setups, and computes a bounded confidence adjustment.
    """
    try:
        response = evaluator.evaluate_setup(request)
        return response
    except Exception as e:
        logger.error(f"Unexpected error evaluating setup for '{request.symbol}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error evaluating trade setup: {str(e)}"
        )
