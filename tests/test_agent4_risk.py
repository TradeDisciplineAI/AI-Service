from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.database import (
    MarketPaperPosition,
    MarketPortfolio,
    SessionLocal,
    TradeProposal,
)
from src.main import app

client = TestClient(app)


@pytest.fixture
def db():
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


def test_risk_evaluation_missing_proposal(db):
    user_id = str(uuid4())
    fake_proposal_id = str(uuid4())
    response = client.post(
        f"/trade-proposals/{fake_proposal_id}/risk-evaluation",
        params={"user_id": user_id},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_risk_evaluation_unauthorized_user(db):
    user_id = uuid4()
    other_user_id = uuid4()

    proposal = TradeProposal(
        id=uuid4(),
        user_id=other_user_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_risk_evaluation_hold_proposal(db):
    user_id = uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="HOLD",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "HOLD" in response.json()["detail"]


def test_risk_evaluation_invalid_status_transition(db):
    user_id = uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-123",
        status="RISK_APPROVED",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_valid_buy_risk_approved(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=100,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Momentum",
        signal_id="SIG-BUY-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision"] == "RISK_APPROVED"
    assert data["risk_score"] == 100
    assert data["max_risk"] == 1000.0
    assert data["estimated_reward"] == 2000.0
    assert data["risk_reward_ratio"] == 2.0
    assert len(data["checks"]) == 7

    db.refresh(proposal)
    assert proposal.status == "RISK_APPROVED"


def test_valid_sell_risk_approved(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="SELL",
        requested_quantity=100,
        entry_price=150.0,
        stop_loss=160.0,
        take_profit=130.0,
        confidence_score=0.8,
        primary_strategy="MeanReversion",
        signal_id="SIG-SELL-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision"] == "RISK_APPROVED"
    assert data["max_risk"] == 1000.0
    assert data["estimated_reward"] == 2000.0
    assert data["risk_reward_ratio"] == 2.0


def test_invalid_buy_pricing_order(db):
    user_id = uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=160.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision"] == "RISK_REJECTED"
    assert data["risk_score"] == 0
    assert any("Invalid BUY price structure" in r for r in data["reasons"])


def test_invalid_sell_pricing_order(db):
    user_id = uuid4()
    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="SELL",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=160.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-123",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision"] == "RISK_REJECTED"
    assert any("Invalid SELL price structure" in r for r in data["reasons"])


def test_zero_and_negative_inputs(db):
    user_id = uuid4()

    p1 = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=0,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-1",
        status="PENDING_RISK",
    )
    p2 = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=-150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-2",
        status="PENDING_RISK",
    )
    db.add_all([p1, p2])
    db.commit()

    for p in [p1, p2]:
        response = client.post(
            f"/trade-proposals/{p.id}/risk-evaluation", params={"user_id": str(user_id)}
        )
        assert response.json()["decision"] == "RISK_REJECTED"


def test_excessive_limits(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    p_pv = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=1000,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-PV",
        status="PENDING_RISK",
    )
    p_risk = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=100,
        entry_price=150.0,
        stop_loss=120.0,
        take_profit=200.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-RISK",
        status="PENDING_RISK",
    )
    p_dist = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=130.0,
        take_profit=200.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-DIST",
        status="PENDING_RISK",
    )
    p_rr = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=160.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-RR",
        status="PENDING_RISK",
    )
    db.add_all([p_pv, p_risk, p_dist, p_rr])
    db.commit()

    r_pv = client.post(
        f"/trade-proposals/{p_pv.id}/risk-evaluation", params={"user_id": str(user_id)}
    ).json()
    assert r_pv["decision"] == "RISK_REJECTED"

    r_risk = client.post(
        f"/trade-proposals/{p_risk.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    ).json()
    assert r_risk["decision"] == "RISK_REJECTED"

    r_dist = client.post(
        f"/trade-proposals/{p_dist.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    ).json()
    assert r_dist["decision"] == "NEEDS_REVIEW"

    r_rr = client.post(
        f"/trade-proposals/{p_rr.id}/risk-evaluation", params={"user_id": str(user_id)}
    ).json()
    assert r_rr["decision"] == "NEEDS_REVIEW"


def test_portfolio_exposure_limits(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    position = MarketPaperPosition(
        id=uuid4(),
        portfolio_id=portfolio_id,
        symbol="MSFT",
        quantity=300,
        average_entry_price=400.0,
    )
    db.add(position)
    db.commit()

    p_port = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=200,
        entry_price=200.0,
        stop_loss=190.0,
        take_profit=230.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-PORT",
        status="PENDING_RISK",
    )
    p_asset = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="MSFT",
        action="BUY",
        requested_quantity=10,
        entry_price=400.0,
        stop_loss=390.0,
        take_profit=430.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-ASSET",
        status="PENDING_RISK",
    )
    db.add_all([p_port, p_asset])
    db.commit()

    r_port = client.post(
        f"/trade-proposals/{p_port.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    ).json()
    assert r_port["decision"] == "RISK_REJECTED"

    r_asset = client.post(
        f"/trade-proposals/{p_asset.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    ).json()
    assert r_asset["decision"] == "RISK_REJECTED"


def test_re_evaluation_persistence_and_retrieval(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=10,
        entry_price=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-TEST",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    resp1 = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert resp1.status_code == status.HTTP_200_OK
    eval1_id = resp1.json()["id"]

    get_resp = client.get(
        f"/trade-proposals/{proposal.id}/risk", params={"user_id": str(user_id)}
    )
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json()["id"] == eval1_id

    db.refresh(proposal)
    proposal.status = "PENDING_RISK"
    db.commit()

    resp2 = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert resp2.status_code == status.HTTP_200_OK
    eval2_id = resp2.json()["id"]
    assert eval2_id != eval1_id

    get_resp2 = client.get(
        f"/trade-proposals/{proposal.id}/risk", params={"user_id": str(user_id)}
    )
    assert get_resp2.json()["id"] == eval2_id


def test_boundaries_exactly_at_configured_limits(db):
    user_id = uuid4()
    portfolio_id = uuid4()

    portfolio = MarketPortfolio(
        id=portfolio_id, user_id=user_id, name="Test Portfolio", type="PAPER"
    )
    db.add(portfolio)
    db.commit()

    proposal = TradeProposal(
        id=uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        symbol="AAPL",
        action="BUY",
        requested_quantity=80,
        entry_price=625.0,
        stop_loss=600.0,
        take_profit=662.5,
        confidence_score=0.8,
        primary_strategy="Test",
        signal_id="SIG-BOUND",
        status="PENDING_RISK",
    )
    db.add(proposal)
    db.commit()

    response = client.post(
        f"/trade-proposals/{proposal.id}/risk-evaluation",
        params={"user_id": str(user_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["decision"] == "RISK_APPROVED"
