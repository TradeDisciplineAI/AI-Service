import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

# Connect to PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Define the Agent 1 Market Signals Table
class MarketSignals(Base):
    __tablename__ = "market_signals"
    __table_args__ = {"schema": "ai"} # <--- Added Schema
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    scan_data = Column(JSON) 
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

# Define the Agent 2 AI Analysis Table
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = {"schema": "ai"} # <--- Added Schema
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    analysis_data = Column(JSON) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Define the Agent 2 Stock News Table
class StockNews(Base):
    __tablename__ = "stock_news"
    __table_args__ = {"schema": "ai"} # <--- Added Schema
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    headlines = Column(JSON) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# CRITICAL: Create the 'ai' schema in PostgreSQL before creating tables!
with engine.connect() as connection:
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai;"))
    connection.commit()

# Create ALL the tables defined above inside the 'ai' schema
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()