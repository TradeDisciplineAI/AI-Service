import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import routers
from src.routers.routes import router as agent2_router
from src.routers.agent3_router import router as agent3_router
from src.routers.trade_proposal_router import router as trade_proposal_router
from src.routers.agent6_router import router as agent6_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI Trading Service API (Agents 1, 2, 3 & 6)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Attach routers
app.include_router(agent2_router)
app.include_router(agent3_router)
app.include_router(trade_proposal_router)
app.include_router(agent6_router)

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "AI-Service", "agents": ["Agent 1", "Agent 2", "Agent 3", "Agent 6"]}

@app.get("/health")
def health():
    return {"status": "healthy"}

