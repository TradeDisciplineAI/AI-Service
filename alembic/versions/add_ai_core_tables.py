"""add ai_analyses market_signals and stock_news tables

Revision ID: add_ai_core_tables
Revises: add_execution_intents_table
Create Date: 2026-09-01 22:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_ai_core_tables'
down_revision: Union[str, None] = 'add_execution_intents_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely create missing model tables inside schema 'ai'
    bind = op.get_bind()
    schema_name = "ai" if bind.dialect.name == "postgresql" else None
    
    ctx = op.get_context()
    is_offline = ctx.opts.get("as_sql", False)
    existing_tables = []
    if not is_offline and bind:
        try:
            inspector = sa.inspect(bind)
            existing_tables = inspector.get_table_names(schema=schema_name)
        except Exception:
            existing_tables = []

    if is_offline or 'market_signals' not in existing_tables:
        op.create_table(
            'market_signals',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ticker', sa.String(), nullable=True),
            sa.Column('scan_data', sa.JSON(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            schema=schema_name
        )
        op.create_index(op.f('ix_ai_market_signals_id'), 'market_signals', ['id'], unique=False, schema=schema_name)
        op.create_index(op.f('ix_ai_market_signals_ticker'), 'market_signals', ['ticker'], unique=True, schema=schema_name)

    if is_offline or 'ai_analyses' not in existing_tables:
        op.create_table(
            'ai_analyses',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ticker', sa.String(), nullable=True),
            sa.Column('analysis_data', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            schema=schema_name
        )
        op.create_index(op.f('ix_ai_ai_analyses_id'), 'ai_analyses', ['id'], unique=False, schema=schema_name)
        op.create_index(op.f('ix_ai_ai_analyses_ticker'), 'ai_analyses', ['ticker'], unique=False, schema=schema_name)

    if is_offline or 'stock_news' not in existing_tables:
        op.create_table(
            'stock_news',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ticker', sa.String(), nullable=True),
            sa.Column('headlines', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            schema=schema_name
        )
        op.create_index(op.f('ix_ai_stock_news_id'), 'stock_news', ['id'], unique=False, schema=schema_name)
        op.create_index(op.f('ix_ai_stock_news_ticker'), 'stock_news', ['ticker'], unique=True, schema=schema_name)


def downgrade() -> None:
    bind = op.get_bind()
    schema_name = "ai" if bind.dialect.name == "postgresql" else None
    
    ctx = op.get_context()
    is_offline = ctx.opts.get("as_sql", False)
    existing_tables = []
    if not is_offline and bind:
        try:
            inspector = sa.inspect(bind)
            existing_tables = inspector.get_table_names(schema=schema_name)
        except Exception:
            existing_tables = []

    if is_offline or 'stock_news' in existing_tables:
        op.drop_index(op.f('ix_ai_stock_news_ticker'), table_name='stock_news', schema=schema_name)
        op.drop_index(op.f('ix_ai_stock_news_id'), table_name='stock_news', schema=schema_name)
        op.drop_table('stock_news', schema=schema_name)

    if is_offline or 'ai_analyses' in existing_tables:
        op.drop_index(op.f('ix_ai_ai_analyses_ticker'), table_name='ai_analyses', schema=schema_name)
        op.drop_index(op.f('ix_ai_ai_analyses_id'), table_name='ai_analyses', schema=schema_name)
        op.drop_table('ai_analyses', schema=schema_name)

    if is_offline or 'market_signals' in existing_tables:
        op.drop_index(op.f('ix_ai_market_signals_ticker'), table_name='market_signals', schema=schema_name)
        op.drop_index(op.f('ix_ai_market_signals_id'), table_name='market_signals', schema=schema_name)
        op.drop_table('market_signals', schema=schema_name)
