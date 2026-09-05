"""create execution intents table

Revision ID: add_execution_intents_table
Revises: create_risk_evaluations_table
Create Date: 2026-08-18 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_execution_intents_table'
down_revision: Union[str, None] = 'create_risk_evaluations_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'execution_intents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('proposal_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['proposal_id'],
            ['ai.trade_proposals.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proposal_id', name='uq_execution_intents_proposal_id'),
        schema='ai',
    )
    op.create_index(
        op.f('ix_ai_execution_intents_proposal_id'),
        'execution_intents',
        ['proposal_id'],
        unique=True,
        schema='ai',
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_ai_execution_intents_proposal_id'),
        table_name='execution_intents',
        schema='ai',
    )
    op.drop_table('execution_intents', schema='ai')
