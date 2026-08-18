import pytest
from uuid import uuid4, UUID
from fastapi.testclient import TestClient
from fastapi import status

from src.main import app
from src.database import SessionLocal, TradeProposal
from src.schemas import SignalAction

client = TestClient(app)

@pytest.fixture
def db():
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()

def test_create_valid_trade_proposal(db):
    """
    Test that a valid trade proposal can be created and persisted,
    and returns 201 Created.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "NVDA",
        "action": "BUY",
        "requested_quantity": 100,
        "signal_id": "SIG-A1B2C3D4",
        "entry_price": 180.50,
        "stop_loss": 175.00,
        "take_profit": 195.00,
        "confidence_score": 0.82,
        "primary_strategy": "MomentumBreakout"
    }

    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    
    data = response.json()
    assert "id" in data
    assert data["user_id"] == user_id
    assert data["symbol"] == "NVDA"
    assert data["action"] == "BUY"
    assert data["requested_quantity"] == 100
    assert data["signal_id"] == "SIG-A1B2C3D4"
    assert data["entry_price"] == 180.50
    assert data["stop_loss"] == 175.00
    assert data["take_profit"] == 195.00
    assert data["confidence_score"] == 0.82
    assert data["primary_strategy"] == "MomentumBreakout"
    assert data["status"] == "PENDING_RISK"
    assert "created_at" in data
    assert "updated_at" in data

    # Verify database persistence
    db_proposal = db.query(TradeProposal).filter(TradeProposal.id == UUID(data["id"])).first()
    assert db_proposal is not None
    assert str(db_proposal.user_id) == user_id
    assert db_proposal.symbol == "NVDA"
    assert db_proposal.action == "BUY"
    assert db_proposal.requested_quantity == 100
    assert db_proposal.signal_id == "SIG-A1B2C3D4"
    assert float(db_proposal.entry_price) == 180.50
    assert float(db_proposal.stop_loss) == 175.00
    assert float(db_proposal.take_profit) == 195.00
    assert float(db_proposal.confidence_score) == 0.82
    assert db_proposal.primary_strategy == "MomentumBreakout"
    assert db_proposal.status == "PENDING_RISK"

def test_get_trade_proposal_by_id(db):
    """
    Test retrieving an existing trade proposal by its ID.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "AAPL",
        "action": "SELL",
        "requested_quantity": 50,
        "signal_id": "SIG-F5E6D7C8",
        "entry_price": 172.30,
        "stop_loss": 175.00,
        "take_profit": 165.00,
        "confidence_score": 0.75,
        "primary_strategy": "MeanReversion"
    }

    create_resp = client.post("/trade-proposals", json=payload)
    assert create_resp.status_code == status.HTTP_201_CREATED
    proposal_id = create_resp.json()["id"]

    # Retrieve proposal
    get_resp = client.get(f"/trade-proposals/{proposal_id}")
    assert get_resp.status_code == status.HTTP_200_OK
    
    data = get_resp.json()
    assert data["id"] == proposal_id
    assert data["symbol"] == "AAPL"
    assert data["action"] == "SELL"
    assert data["requested_quantity"] == 50
    assert data["signal_id"] == "SIG-F5E6D7C8"
    assert data["status"] == "PENDING_RISK"

def test_get_nonexistent_proposal_returns_404():
    """
    Test that retrieving a nonexistent proposal ID returns 404 Not Found.
    """
    random_id = str(uuid4())
    response = client.get(f"/trade-proposals/{random_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()

def test_reject_zero_or_negative_quantity():
    """
    Test that quantity <= 0 is rejected with 422.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "AAPL",
        "action": "BUY",
        "requested_quantity": 0,  # Zero
        "signal_id": "SIG-12345678",
        "entry_price": 150.00,
        "stop_loss": 145.00,
        "take_profit": 160.00,
        "confidence_score": 0.80,
        "primary_strategy": "MomentumBreakout"
    }
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "quantity" in response.json()["detail"].lower()

    payload["requested_quantity"] = -10  # Negative
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "quantity" in response.json()["detail"].lower()

def test_reject_invalid_prices():
    """
    Test that negative or zero prices are rejected.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "AAPL",
        "action": "BUY",
        "requested_quantity": 10,
        "signal_id": "SIG-12345678",
        "entry_price": 0.0,  # Zero
        "stop_loss": 145.00,
        "take_profit": 160.00,
        "confidence_score": 0.80,
        "primary_strategy": "MomentumBreakout"
    }
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "price" in response.json()["detail"].lower()

    payload["entry_price"] = 150.00
    payload["stop_loss"] = -5.0  # Negative
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "price" in response.json()["detail"].lower()

def test_reject_invalid_action():
    """
    Test that HOLD action is rejected.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "AAPL",
        "action": "HOLD",  # Invalid for proposal
        "requested_quantity": 100,
        "signal_id": "SIG-12345678",
        "entry_price": 150.00,
        "stop_loss": 145.00,
        "take_profit": 160.00,
        "confidence_score": 0.80,
        "primary_strategy": "MomentumBreakout"
    }
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

def test_reject_invalid_signal_id():
    """
    Test that invalid or missing signal_id prefix is rejected.
    """
    user_id = str(uuid4())
    payload = {
        "user_id": user_id,
        "symbol": "AAPL",
        "action": "BUY",
        "requested_quantity": 10,
        "signal_id": "A1B2C3D4",  # Missing 'SIG-' prefix
        "entry_price": 150.00,
        "stop_loss": 145.00,
        "take_profit": 160.00,
        "confidence_score": 0.80,
        "primary_strategy": "MomentumBreakout"
    }
    response = client.post("/trade-proposals", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "signal_id" in response.json()["detail"].lower()


def test_get_all_trade_proposals(db):
    """
    Test retrieving all trade proposals.
    """
    # Create two proposals for the same user
    user_id = str(uuid4())
    portfolio_id = str(uuid4())
    
    payload1 = {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "symbol": "MSFT",
        "action": "BUY",
        "requested_quantity": 10,
        "signal_id": "SIG-M1",
        "entry_price": 420.00,
        "stop_loss": 410.00,
        "take_profit": 440.00,
        "confidence_score": 0.85,
        "primary_strategy": "EMACrossover"
    }
    
    payload2 = {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "symbol": "MSFT",
        "action": "SELL",
        "requested_quantity": 5,
        "signal_id": "SIG-M2",
        "entry_price": 425.00,
        "stop_loss": 435.00,
        "take_profit": 415.00,
        "confidence_score": 0.78,
        "primary_strategy": "MeanReversion"
    }

    resp1 = client.post("/trade-proposals", json=payload1)
    assert resp1.status_code == status.HTTP_201_CREATED
    
    resp2 = client.post("/trade-proposals", json=payload2)
    assert resp2.status_code == status.HTTP_201_CREATED

    # Fetch all proposals (without filter)
    all_resp = client.get("/trade-proposals")
    assert all_resp.status_code == status.HTTP_200_OK
    all_data = all_resp.json()
    assert len(all_data) >= 2
    
    # Verify portfolio_id persistence
    p1 = next(x for x in all_data if x["id"] == resp1.json()["id"])
    assert p1["portfolio_id"] == portfolio_id
    assert p1["action"] == "BUY"
    assert p1["status"] == "PENDING_RISK"

    # Fetch proposals filtered by user_id
    user_resp = client.get(f"/trade-proposals?user_id={user_id}")
    assert user_resp.status_code == status.HTTP_200_OK
    user_data = user_resp.json()
    assert len(user_data) == 2
    assert all(x["user_id"] == user_id for x in user_data)
    
    # Verify UUID serialization format (must be standard string UUID representation in JSON)
    for x in user_data:
        # Check that they parse as valid UUIDs
        assert UUID(x["id"])
        assert UUID(x["user_id"])
        assert UUID(x["portfolio_id"])

