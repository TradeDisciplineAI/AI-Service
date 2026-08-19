"""
Agent 5: Paper Execution — comprehensive test suite.

Tests cover:
1.  Successful execution of RISK_APPROVED proposal
2.  PENDING_RISK rejected
3.  RISK_REJECTED rejected
4.  NEEDS_REVIEW rejected
5.  Wrong user rejected (403)
6.  Missing portfolio rejected (400)
7.  Duplicate execution / idempotency
8.  Concurrent execution protection (IntegrityError path)
9.  Successful status transition to EXECUTED
10. market-service failure → EXECUTION_FAILED
11. Execution intent failure handling
12. Immutable proposal values are forwarded correctly
13. Live execution price is NOT supplied by the client
14. Proposal not found → 404
15. Missing user_id → 400
"""

import pytest
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID

from fastapi.testclient import TestClient
from fastapi import status

from src.main import app
from src.database import SessionLocal, TradeProposal, ExecutionIntent, Base, engine
from src.schemas import SignalAction, PaperExecutionResponse

client = TestClient(app)


@pytest.fixture
def db():
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


def _create_proposal(
    db,
    user_id=None,
    portfolio_id=None,
    symbol="TSLA",
    action="BUY",
    status_val="PENDING_RISK",
    entry_price=339.34,
    stop_loss=330.00,
    take_profit=358.02,
):
    """Helper: insert a TradeProposal directly into the DB."""
    uid = user_id or uuid4()
    pid = portfolio_id or uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=uid,
        portfolio_id=pid,
        signal_id=f"SIG-{uuid4().hex[:8].upper()}",
        symbol=symbol,
        action=action,
        requested_quantity=10,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence_score=0.85,
        primary_strategy="MomentumBreakout",
        status=status_val,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def _make_fill_response(proposal, exec_id="EXE-TEST1234"):
    """Helper: build a PaperExecutionResponse matching a proposal."""
    return PaperExecutionResponse(
        execution_id=exec_id,
        proposal_id=proposal.id,
        symbol=proposal.symbol,
        action=proposal.action,
        filled_quantity=proposal.requested_quantity,
        execution_price=341.50,  # simulated live price
        executed_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Successful execution of RISK_APPROVED proposal
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_successful_execution(mock_ms, db):
    """A RISK_APPROVED proposal should execute successfully."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal)

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["proposal_status"] == "EXECUTED"
    assert data["symbol"] == "TSLA"
    assert data["action"] == "BUY"
    assert data["requested_quantity"] == 10
    assert data["filled_quantity"] == 10
    assert data["execution_price"] == 341.50
    assert data["execution_id"].startswith("EXE-") or data["execution_id"] == "EXE-TEST1234"
    assert data["stop_loss"] == 330.0
    assert data["take_profit"] == 358.02
    assert data["primary_strategy"] == "MomentumBreakout"
    assert "executed_at" in data


# ─────────────────────────────────────────────────────────────────────────────
# 2. PENDING_RISK rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_pending_risk_rejected(db):
    """A proposal still in PENDING_RISK must be rejected."""
    proposal = _create_proposal(db, status_val="PENDING_RISK")
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 400
    assert "PENDING_RISK" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. RISK_REJECTED rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_risk_rejected_proposal(db):
    """A RISK_REJECTED proposal must be rejected."""
    proposal = _create_proposal(db, status_val="RISK_REJECTED")
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 400
    assert "RISK_REJECTED" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. NEEDS_REVIEW rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_needs_review_rejected(db):
    """A NEEDS_REVIEW proposal must be rejected."""
    proposal = _create_proposal(db, status_val="NEEDS_REVIEW")
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 400
    assert "NEEDS_REVIEW" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Wrong user rejected (403)
# ─────────────────────────────────────────────────────────────────────────────
def test_wrong_user_rejected(db):
    """A user who does not own the proposal must get 403."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    other_user = uuid4()
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={other_user}"
    )
    assert resp.status_code == 403
    assert "own" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Missing portfolio rejected (400)
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_portfolio_rejected(db):
    """A proposal with no portfolio_id must be rejected."""
    uid = uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=uid,
        portfolio_id=None,  # <-- no portfolio
        signal_id="SIG-NOPORT",
        symbol="AAPL",
        action="BUY",
        requested_quantity=5,
        entry_price=190.00,
        stop_loss=185.00,
        take_profit=200.00,
        confidence_score=0.80,
        primary_strategy="EMACrossover",
        status="RISK_APPROVED",
    )
    db.add(proposal)
    db.commit()

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={uid}"
    )
    assert resp.status_code == 400
    assert "portfolio" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Duplicate execution / idempotency (already EXECUTED)
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_idempotent_reexecution(mock_ms, db):
    """Re-executing an already-EXECUTED proposal returns the existing result, not a duplicate."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal)

    # First execution
    resp1 = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp1.status_code == 200
    assert resp1.json()["proposal_status"] == "EXECUTED"

    # Second execution (idempotent) — proposal is now EXECUTED
    resp2 = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    # Should return 200 with the same execution result (idempotent)
    assert resp2.status_code == 200
    assert resp2.json()["proposal_status"] == "EXECUTED"

    # market-service should only have been called once
    assert mock_ms.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Concurrent execution protection (IntegrityError path)
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_concurrent_execution_protection(mock_ms, db):
    """If a second execution races and gets IntegrityError, it must get 409."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")

    # Pre-insert an execution intent to simulate a race condition
    existing_intent = ExecutionIntent(
        proposal_id=proposal.id,
        status="PENDING",
    )
    db.add(existing_intent)
    db.commit()

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()
    mock_ms.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Successful status transition to EXECUTED
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_status_transition_to_executed(mock_ms, db):
    """After successful execution, proposal status must be EXECUTED and intent COMPLETED."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal)

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 200

    # Verify DB state
    db.expire_all()
    db_proposal = db.query(TradeProposal).filter(TradeProposal.id == proposal.id).first()
    assert db_proposal.status == "EXECUTED"

    db_intent = db.query(ExecutionIntent).filter(ExecutionIntent.proposal_id == proposal.id).first()
    assert db_intent is not None
    assert db_intent.status == "COMPLETED"
    assert db_intent.completed_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 10. market-service failure → EXECUTION_FAILED
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_market_service_failure(mock_ms, db):
    """On market-service error, proposal must transition to EXECUTION_FAILED."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.side_effect = RuntimeError("market-service returned HTTP 500: internal error")

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 502
    assert "market-service" in resp.json()["detail"].lower()

    # Verify DB state
    db.expire_all()
    db_proposal = db.query(TradeProposal).filter(TradeProposal.id == proposal.id).first()
    assert db_proposal.status == "EXECUTION_FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Execution intent failure handling
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_execution_intent_failure_status(mock_ms, db):
    """On market-service failure, execution intent status must be FAILED."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.side_effect = RuntimeError("Connection refused")

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 502

    db.expire_all()
    db_intent = db.query(ExecutionIntent).filter(ExecutionIntent.proposal_id == proposal.id).first()
    assert db_intent is not None
    assert db_intent.status == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Immutable proposal values are forwarded correctly
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_immutable_values_forwarded(mock_ms, db):
    """The payload sent to market-service must contain the immutable proposal values."""
    proposal = _create_proposal(
        db,
        status_val="RISK_APPROVED",
        symbol="GOOGL",
        action="SELL",
        entry_price=180.00,
        stop_loss=185.00,
        take_profit=170.00,
    )

    fill = _make_fill_response(proposal)
    mock_ms.return_value = fill

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 200

    # Verify what was sent to market-service
    call_args = mock_ms.call_args[0][0]  # First positional arg = PaperExecutionRequest
    assert str(call_args.proposal_id) == str(proposal.id)
    assert str(call_args.portfolio_id) == str(proposal.portfolio_id)
    assert str(call_args.user_id) == str(proposal.user_id)
    assert call_args.symbol == "GOOGL"
    assert call_args.action == "SELL"
    assert call_args.requested_quantity == 10
    assert call_args.stop_loss == 185.0
    assert call_args.take_profit == 170.0
    assert call_args.primary_strategy == "MomentumBreakout"
    assert call_args.execution_id.startswith("EXE-")


# ─────────────────────────────────────────────────────────────────────────────
# 13. Live execution price is NOT supplied by the client
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_no_client_execution_price(mock_ms, db):
    """The payload sent to market-service must NOT contain an execution_price field."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal)

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 200

    # PaperExecutionRequest should have no execution_price attribute
    call_args = mock_ms.call_args[0][0]
    assert not hasattr(call_args, "execution_price"),         "Client must not supply execution_price — market-service determines live fill price."


# ─────────────────────────────────────────────────────────────────────────────
# 14. Proposal not found → 404
# ─────────────────────────────────────────────────────────────────────────────
def test_proposal_not_found(db):
    """Executing a non-existent proposal must return 404."""
    fake_id = uuid4()
    fake_user = uuid4()
    resp = client.post(
        f"/trade-proposals/{fake_id}/execute?user_id={fake_user}"
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 15. Missing user_id → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_user_id(db):
    """Calling execute without user_id or X-User-Id must return 400."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    resp = client.post(f"/trade-proposals/{proposal.id}/execute")
    assert resp.status_code == 400
    assert "user_id" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 16. X-User-Id header works
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_x_user_id_header(mock_ms, db):
    """The X-User-Id header should work as an alternative to the query parameter."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal)

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute",
        headers={"X-User-Id": str(proposal.user_id)},
    )
    assert resp.status_code == 200
    assert resp.json()["proposal_status"] == "EXECUTED"


# ─────────────────────────────────────────────────────────────────────────────
# 17. EXECUTION_PENDING status rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_execution_pending_rejected(db):
    """A proposal already in EXECUTION_PENDING must be rejected."""
    proposal = _create_proposal(db, status_val="EXECUTION_PENDING")
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 400
    assert "EXECUTION_PENDING" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 18. EXECUTION_FAILED status rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_execution_failed_status_rejected(db):
    """A proposal in EXECUTION_FAILED must be rejected."""
    proposal = _create_proposal(db, status_val="EXECUTION_FAILED")
    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 400
    assert "EXECUTION_FAILED" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 19. Execution ID format
# ─────────────────────────────────────────────────────────────────────────────
@patch("src.execution_service._call_market_service")
def test_execution_id_format(mock_ms, db):
    """The returned execution_id must start with EXE-."""
    proposal = _create_proposal(db, status_val="RISK_APPROVED")
    mock_ms.return_value = _make_fill_response(proposal, exec_id="EXE-ABCD1234")

    resp = client.post(
        f"/trade-proposals/{proposal.id}/execute?user_id={proposal.user_id}"
    )
    assert resp.status_code == 200
    # The execution_id comes from mock_ms return value
    assert resp.json()["execution_id"] == "EXE-ABCD1234"
