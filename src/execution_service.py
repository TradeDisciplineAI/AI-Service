"""
Agent 5: Paper Execution Service
Handles the AI-Service side of the execution pipeline:
  - Ownership validation
  - Status gate (RISK_APPROVED required)
  - Idempotency via execution_intents table
  - Concurrency protection (proposal row lock on SQLite-compatible path)
  - Delegation to market-service for the actual fill
  - TradeProposal status transitions
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import urllib.request
import urllib.error
import json

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status as http_status

from src.config import execution_settings
from src.database import ExecutionIntent, TradeProposal
from src.schemas import ExecutionResultResponse, PaperExecutionRequest, PaperExecutionResponse

logger = logging.getLogger(__name__)

# Valid states that can be executed — only RISK_APPROVED is allowed.
_EXECUTABLE_STATUS = "RISK_APPROVED"

# Specific rejection messages for non-RISK_APPROVED statuses
_STATUS_REJECTION: dict[str, str] = {
    "PENDING_RISK": "Proposal has not been risk-evaluated yet (status: PENDING_RISK). Run Agent 4 risk evaluation first.",
    "RISK_REJECTED": "Proposal was rejected by Agent 4 risk engine (status: RISK_REJECTED). Execution is not permitted.",
    "NEEDS_REVIEW": "Proposal requires manual review (status: NEEDS_REVIEW). Execution is not permitted until risk review is cleared.",
    "EXECUTION_PENDING": "Proposal execution is already in progress (status: EXECUTION_PENDING).",
    "EXECUTED": "Proposal has already been executed (status: EXECUTED).",
    "EXECUTION_FAILED": "A previous execution attempt failed (status: EXECUTION_FAILED). Review the failure before retrying.",
}


def _generate_execution_id() -> str:
    """Generate a unique EXE-XXXXXXXX execution identifier."""
    return f"EXE-{uuid.uuid4().hex[:8].upper()}"


def _call_market_service(payload: PaperExecutionRequest) -> PaperExecutionResponse:
    """
    HTTP call to market-service internal paper fill endpoint.
    Uses stdlib urllib to avoid adding httpx/requests dependency.
    Raises RuntimeError on any non-201 response.
    """
    base_url = execution_settings.MARKET_SERVICE_INTERNAL_URL.rstrip("/")
    url = f"{base_url}/internal/paper-executions"
    secret = execution_settings.MARKET_SERVICE_INTERNAL_SECRET

    body = json.dumps({
        "proposal_id": str(payload.proposal_id),
        "execution_id": payload.execution_id,
        "portfolio_id": str(payload.portfolio_id),
        "user_id": str(payload.user_id),
        "symbol": payload.symbol,
        "action": payload.action,
        "requested_quantity": payload.requested_quantity,
        "stop_loss": payload.stop_loss,
        "take_profit": payload.take_profit,
        "primary_strategy": payload.primary_strategy,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": secret,
    }

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_body = json.loads(resp.read().decode("utf-8"))
            return PaperExecutionResponse(
                execution_id=response_body["execution_id"],
                proposal_id=UUID(response_body["proposal_id"]),
                symbol=response_body["symbol"],
                action=response_body["action"],
                filled_quantity=response_body["filled_quantity"],
                execution_price=response_body["execution_price"],
                executed_at=datetime.fromisoformat(response_body["executed_at"]),
            )
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"market-service returned HTTP {e.code}: {body_text}") from e
    except Exception as e:
        raise RuntimeError(f"market-service call failed: {e}") from e


class ExecutionService:
    """Agent 5 execution service — AI-Service side."""

    def execute_proposal(
        self,
        db: Session,
        proposal_id: UUID,
        requesting_user_id: UUID,
    ) -> ExecutionResultResponse:
        """
        Main entry point for POST /trade-proposals/{proposal_id}/execute.

        Steps:
        1. Load proposal — 404 if not found.
        2. Ownership check — 403 if user mismatch.
        3. Portfolio required — 400 if no portfolio_id.
        4. Status gate — only RISK_APPROVED proceeds; specific 400 for all others.
        5. Idempotency — if ExecutionIntent already exists, return existing result
           (or 409 if still PENDING / FAILED).
        6. Concurrency protection — insert ExecutionIntent with UNIQUE proposal_id;
           IntegrityError means a concurrent request won the race.
        7. Transition proposal → EXECUTION_PENDING.
        8. Call market-service.
        9a. On success → EXECUTED, intent → COMPLETED.
        9b. On failure → EXECUTION_FAILED, intent → FAILED; raise 502.
        """
        # ── 1. Load proposal ────────────────────────────────────────────────
        proposal = db.query(TradeProposal).filter(TradeProposal.id == proposal_id).first()
        if not proposal:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Trade proposal {proposal_id} not found.",
            )

        # ── 2. Ownership check ───────────────────────────────────────────────
        if proposal.user_id != requesting_user_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="You do not own this trade proposal.",
            )

        # ── 3. Portfolio required ────────────────────────────────────────────
        if not proposal.portfolio_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Proposal has no associated portfolio. A portfolio is required for paper execution.",
            )

        # ── 4. Status gate ───────────────────────────────────────────────────
        current_status = proposal.status

        # Idempotency: already executed — check for existing intent/result
        if current_status == "EXECUTED":
            intent = (
                db.query(ExecutionIntent)
                .filter(ExecutionIntent.proposal_id == proposal_id)
                .first()
            )
            if intent and intent.status == "COMPLETED":
                # Return reconstructed result from proposal data
                return self._build_result_from_proposal(proposal, intent)
            # EXECUTED status without a COMPLETED intent is a data inconsistency — surface it
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="Proposal is already in EXECUTED status but execution record is incomplete.",
            )

        # Specific rejection for all non-RISK_APPROVED statuses
        if current_status != _EXECUTABLE_STATUS:
            detail = _STATUS_REJECTION.get(
                current_status,
                f"Proposal cannot be executed in its current status: {current_status}.",
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        # ── 5 & 6. Idempotency + Concurrency protection ──────────────────────
        # Attempt to INSERT execution_intent. UNIQUE constraint on proposal_id
        # prevents duplicate intents — this is our race-condition guard.
        intent = ExecutionIntent(
            proposal_id=proposal_id,
            status="PENDING",
        )
        db.add(intent)
        try:
            db.flush()  # flush to catch IntegrityError before commit
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="An execution for this proposal is already in progress or has been attempted. "
                       "Check proposal status before retrying.",
            )

        # ── 7. Transition → EXECUTION_PENDING ────────────────────────────────
        proposal.status = "EXECUTION_PENDING"
        proposal.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(intent)

        # ── 8. Build market-service payload (no client-supplied price) ────────
        exec_id = _generate_execution_id()
        payload = PaperExecutionRequest(
            proposal_id=proposal_id,
            execution_id=exec_id,
            portfolio_id=proposal.portfolio_id,
            user_id=requesting_user_id,
            symbol=proposal.symbol,
            action=proposal.action,
            requested_quantity=proposal.requested_quantity,
            stop_loss=float(proposal.stop_loss),
            take_profit=float(proposal.take_profit),
            primary_strategy=proposal.primary_strategy,
        )

        # ── 9. Call market-service ────────────────────────────────────────────
        try:
            fill = _call_market_service(payload)
        except RuntimeError as e:
            logger.error("market-service fill failed for proposal %s: %s", proposal_id, e)
            proposal.status = "EXECUTION_FAILED"
            proposal.updated_at = datetime.now(timezone.utc)
            intent.status = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail=f"Paper execution failed: market-service error — {e}",
            )

        # ── 9a. Success — finalize ────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        proposal.status = "EXECUTED"
        proposal.updated_at = now
        intent.status = "COMPLETED"
        intent.completed_at = now
        db.commit()
        db.refresh(proposal)
        db.refresh(intent)

        return ExecutionResultResponse(
            execution_id=fill.execution_id,
            proposal_id=proposal.id,
            symbol=proposal.symbol,
            action=proposal.action,
            requested_quantity=proposal.requested_quantity,
            filled_quantity=fill.filled_quantity,
            execution_price=fill.execution_price,
            stop_loss=float(proposal.stop_loss),
            take_profit=float(proposal.take_profit),
            primary_strategy=proposal.primary_strategy,
            executed_at=fill.executed_at,
            proposal_status="EXECUTED",
        )

    def _build_result_from_proposal(
        self,
        proposal: TradeProposal,
        intent: ExecutionIntent,
    ) -> ExecutionResultResponse:
        """
        Reconstruct ExecutionResultResponse for an already-EXECUTED proposal.
        Used for idempotent re-requests.
        Note: filled_quantity and execution_price are not stored in AI-Service;
        we return requested_quantity and entry_price as best-effort for idempotent reads.
        Market-service is the source of truth for fill details.
        """
        return ExecutionResultResponse(
            execution_id="(see market-service for fill details)",
            proposal_id=proposal.id,
            symbol=proposal.symbol,
            action=proposal.action,
            requested_quantity=proposal.requested_quantity,
            filled_quantity=proposal.requested_quantity,
            execution_price=float(proposal.entry_price),
            stop_loss=float(proposal.stop_loss),
            take_profit=float(proposal.take_profit),
            primary_strategy=proposal.primary_strategy,
            executed_at=intent.completed_at or datetime.now(timezone.utc),
            proposal_status="EXECUTED",
        )
