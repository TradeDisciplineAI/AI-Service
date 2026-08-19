"""create risk evaluations table

Revision ID: create_risk_evaluations_table
Revises: add_portfolio_id_col
Create Date: 2026-08-18 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'create_risk_evaluations_table'
down_revision: Union[str, None] = 'add_portfolio_id_col'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create the risk_evaluations table inside schema 'ai'
    op.create_table(
        'risk_evaluations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('proposal_id', sa.UUID(), nullable=False),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('risk_score', sa.Integer(), nullable=False),
        sa.Column('max_risk', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('estimated_reward', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('risk_reward_ratio', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('portfolio_exposure', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('checks', sa.JSON(), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['proposal_id'], ['ai.trade_proposals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='ai'
    )
    op.create_index(op.f('ix_ai_risk_evaluations_proposal_id'), 'risk_evaluations', ['proposal_id'], unique=False, schema='ai')

def downgrade() -> None:
    op.drop_index(op.f('ix_ai_risk_evaluations_proposal_id'), table_name='risk_evaluations', schema='ai')
    op.drop_table('risk_evaluations', schema='ai')
