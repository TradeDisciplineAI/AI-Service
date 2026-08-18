import re
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import HTTPException, status
from typing import Optional

from src.database import TradeProposal
from src.schemas import TradeProposalCreate, SignalAction
from src.trade_proposal_repository import TradeProposalRepository

class TradeProposalService:
    def __init__(self):
        self.repository = TradeProposalRepository()

    def create_proposal(self, db: Session, proposal_in: TradeProposalCreate) -> TradeProposal:
        # 1. Validation
        if proposal_in.requested_quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="requested_quantity must be greater than zero."
            )
            
        if proposal_in.entry_price <= 0 or proposal_in.stop_loss <= 0 or proposal_in.take_profit <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Price targets (entry_price, stop_loss, take_profit) must be positive values."
            )

        if proposal_in.action == SignalAction.HOLD:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="HOLD action is not allowed for executable trade proposals. Only BUY or SELL actions are allowed."
            )

        if not proposal_in.signal_id or not proposal_in.signal_id.startswith("SIG-"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="signal_id must be a valid non-empty string starting with 'SIG-'."
            )

        if not proposal_in.symbol.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="symbol must be a non-empty string."
            )
            
        if proposal_in.confidence_score < 0.0 or proposal_in.confidence_score > 1.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="confidence_score must be between 0.0 and 1.0."
            )

        # 2. Database model instantiation
        proposal = TradeProposal(
            user_id=proposal_in.user_id,
            portfolio_id=proposal_in.portfolio_id,
            signal_id=proposal_in.signal_id,
            symbol=proposal_in.symbol.strip().upper(),
            action=proposal_in.action.value,
            requested_quantity=proposal_in.requested_quantity,
            entry_price=proposal_in.entry_price,
            stop_loss=proposal_in.stop_loss,
            take_profit=proposal_in.take_profit,
            confidence_score=proposal_in.confidence_score,
            primary_strategy=proposal_in.primary_strategy.strip()
        )

        return self.repository.create(db, proposal)

    def get_all_proposals(self, db: Session, user_id: Optional[UUID] = None) -> list[TradeProposal]:
        return self.repository.get_all(db, user_id)

    def get_proposal(self, db: Session, proposal_id: UUID) -> TradeProposal:
        proposal = self.repository.get_by_id(db, proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"TradeProposal with ID {proposal_id} not found."
            )
        return proposal
