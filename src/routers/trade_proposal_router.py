from fastapi import APIRouter, Depends, status, HTTPException, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List

from src.database import get_db
from src.schemas import TradeProposalCreate, TradeProposalResponse, RiskEvaluationResponse
from src.trade_proposal_service import TradeProposalService
from src.risk_service import RiskService

router = APIRouter(prefix="/trade-proposals", tags=["Trade Proposals"])
service = TradeProposalService()
risk_service = RiskService()

@router.get("", response_model=List[TradeProposalResponse])
def get_all_proposals(user_id: Optional[UUID] = None, db: Session = Depends(get_db)):
    return service.get_all_proposals(db, user_id)

@router.post("", response_model=TradeProposalResponse, status_code=status.HTTP_201_CREATED)
def create_proposal(proposal_in: TradeProposalCreate, db: Session = Depends(get_db)):
    return service.create_proposal(db, proposal_in)

@router.get("/{proposal_id}", response_model=TradeProposalResponse)
def get_proposal(proposal_id: UUID, db: Session = Depends(get_db)):
    return service.get_proposal(db, proposal_id)

@router.post("/{proposal_id}/risk-evaluation", response_model=RiskEvaluationResponse)
def evaluate_proposal_risk(
    proposal_id: UUID, 
    user_id: Optional[UUID] = None,
    x_user_id: Optional[UUID] = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db)
):
    effective_user_id = user_id or x_user_id
    if not effective_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id query parameter or X-User-Id header.")
    try:
        evaluation = risk_service.evaluate_proposal(db, proposal_id, effective_user_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Trade proposal not found.")
        return evaluation
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{proposal_id}/risk", response_model=RiskEvaluationResponse)
def get_proposal_risk(
    proposal_id: UUID,
    user_id: Optional[UUID] = None,
    x_user_id: Optional[UUID] = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db)
):
    effective_user_id = user_id or x_user_id
    if not effective_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id query parameter or X-User-Id header.")
    try:
        evaluation = risk_service.get_latest_evaluation(db, proposal_id, effective_user_id)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Risk evaluation not found for this proposal.")
        return evaluation
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
