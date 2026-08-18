"""add portfolio_id to trade_proposals table

Revision ID: add_portfolio_id_col
Revises: cce2857ca2b8
Create Date: 2026-08-17 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_portfolio_id_col'
down_revision: Union[str, None] = 'cce2857ca2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add portfolio_id column to the trade_proposals table inside schema 'ai'
    op.add_column('trade_proposals', sa.Column('portfolio_id', sa.UUID(), nullable=True), schema='ai')
    op.create_index(op.f('ix_ai_trade_proposals_portfolio_id'), 'trade_proposals', ['portfolio_id'], unique=False, schema='ai')

def downgrade() -> None:
    op.drop_index(op.f('ix_ai_trade_proposals_portfolio_id'), table_name='trade_proposals', schema='ai')
    op.drop_column('trade_proposals', 'portfolio_id', schema='ai')
