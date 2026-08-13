import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

# Connect to PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Define the AI Analysis Table structure
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    analysis_data = Column(JSON) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Define the Stock News Table structure
class StockNews(Base):
    __tablename__ = "stock_news"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    headlines = Column(JSON) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# CRITICAL: This MUST be at the very bottom so it creates ALL the tables defined above!
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()