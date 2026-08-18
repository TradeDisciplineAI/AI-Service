from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List

from src.database import get_db
from src.schemas import TradeProposalCreate, TradeProposalResponse
from src.trade_proposal_service import TradeProposalService

router = APIRouter(prefix="/trade-proposals", tags=["Trade Proposals"])
service = TradeProposalService()

@router.get("", response_model=List[TradeProposalResponse])
def get_all_proposals(user_id: Optional[UUID] = None, db: Session = Depends(get_db)):
    return service.get_all_proposals(db, user_id)

@router.post("", response_model=TradeProposalResponse, status_code=status.HTTP_201_CREATED)
def create_proposal(proposal_in: TradeProposalCreate, db: Session = Depends(get_db)):
    return service.create_proposal(db, proposal_in)

@router.get("/{proposal_id}", response_model=TradeProposalResponse)
def get_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    return service.get_proposal(db, proposal_id)

