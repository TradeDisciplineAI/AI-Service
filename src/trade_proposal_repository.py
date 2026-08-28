from uuid import UUID

from sqlalchemy.orm import Session

from src.database import TradeProposal


class TradeProposalRepository:
    def create(self, db: Session, proposal: TradeProposal) -> TradeProposal:
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        return proposal

    def get_by_id(self, db: Session, proposal_id: UUID) -> TradeProposal | None:
        return db.query(TradeProposal).filter(TradeProposal.id == proposal_id).first()

    def get_all(self, db: Session, user_id: UUID | None = None) -> list[TradeProposal]:
        query = db.query(TradeProposal)
        if user_id:
            query = query.filter(TradeProposal.user_id == user_id)
        return query.order_by(TradeProposal.created_at.desc()).all()
