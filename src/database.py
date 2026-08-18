import os
import uuid
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, text, Numeric, UUID, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

# Connect to Database
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:////tmp/ai_service.db"

# Replace postgresql+asyncpg:// with postgresql:// for sync engine compatibility
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

# Engine configuration
IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Use schema only for PostgreSQL
schema_kwargs = {"schema": "ai"} if engine.dialect.name == "postgresql" else {}

# Define the Agent 1 Market Signals Table
class MarketSignals(Base):
    __tablename__ = "market_signals"
    if schema_kwargs:
        __table_args__ = schema_kwargs
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    scan_data = Column(JSON)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# Define the Agent 2 AI Analysis Table
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    if schema_kwargs:
        __table_args__ = schema_kwargs
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Define the Agent 2 Stock News Table
class StockNews(Base):
    __tablename__ = "stock_news"
    if schema_kwargs:
        __table_args__ = schema_kwargs
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    headlines = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Define the Trade Proposal Table
class TradeProposal(Base):
    __tablename__ = "trade_proposals"
    if schema_kwargs:
        __table_args__ = schema_kwargs

    # Use native UUID mapping (as_uuid=True handles both SQLite and PostgreSQL)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    portfolio_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    signal_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    requested_quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(18, 4), nullable=False)
    stop_loss = Column(Numeric(18, 4), nullable=False)
    take_profit = Column(Numeric(18, 4), nullable=False)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    primary_strategy = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING_RISK")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    risk_evaluations = relationship("RiskEvaluation", back_populates="proposal", cascade="all, delete-orphan")

# Define the Risk Evaluation Table (stores multiple evaluation history records)
class RiskEvaluation(Base):
    __tablename__ = "risk_evaluations"
    if schema_kwargs:
        __table_args__ = schema_kwargs

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey(TradeProposal.id, ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String, nullable=False)
    risk_score = Column(Integer, nullable=False)
    max_risk = Column(Numeric(18, 4), nullable=False)
    estimated_reward = Column(Numeric(18, 4), nullable=False)
    risk_reward_ratio = Column(Numeric(18, 4), nullable=False)
    portfolio_exposure = Column(Numeric(18, 4), nullable=False)
    checks = Column(JSON, nullable=False)
    reasons = Column(JSON, nullable=False)
    evaluated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    proposal = relationship("TradeProposal", back_populates="risk_evaluations")

# Read-only SQLAlchemy mappings for Market-Service schema
class MarketPortfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = {"schema": "market"} if engine.dialect.name == "postgresql" else {}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default="PAPER")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MarketPaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = {"schema": "market"} if engine.dialect.name == "postgresql" else {}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    average_entry_price = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Create schema and tables logic
if engine.dialect.name == "postgresql":
    with engine.connect() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai;"))
        connection.commit()
    # In production/postgresql we rely entirely on alembic migrations, DO NOT create tables here.
else:
    # For SQLite (unit tests), automatically create all tables
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

