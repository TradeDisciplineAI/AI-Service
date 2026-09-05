# ------------------ AI Service Main Entrypoint Feature -----------------------
"""
FastAPI application entrypoint for the AI Service orchestrating autonomous Trading Agents 1-6.
Configures CORS middleware, mounts API routers, and exposes service health endpoints.
"""

import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from src.routers.agent3_router import router as agent3_router
from src.routers.agent6_router import router as agent6_router
from src.routers.routes import router as agent2_router
from src.routers.trade_proposal_router import router as trade_proposal_router

# Load environment variables
load_dotenv()
logging.basicConfig(level=logging.INFO)

# ------------------ FastAPI Application Instance -----------------------
app = FastAPI(title="AI Trading Service API (Agents 1-6)")

# Instrument FastAPI HTTP metrics and expose GET /metrics endpoint
Instrumentator().instrument(app).expose(app)

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5175",
    "https://tradingcopilot.vercel.app",
    "https://tradingcopilot.duckdns.org",
]

raw_origins = os.getenv("ALLOWED_ORIGINS")
if raw_origins:
    try:
        allowed_origins = json.loads(raw_origins)
    except Exception:
        allowed_origins = DEFAULT_ORIGINS
else:
    allowed_origins = DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# ------------------ Mount API Routers -----------------------
app.include_router(agent2_router)
app.include_router(agent3_router)
app.include_router(trade_proposal_router)
app.include_router(agent6_router)


# ------------------ Root Service Endpoint -----------------------
@app.get("/")
def health_check():
    """
    Root endpoint returning service identity and supported agent list.
    """
    return {
        "status": "healthy",
        "service": "AI-Service",
        "agents": ["Agent 1", "Agent 2", "Agent 3", "Agent 4", "Agent 5", "Agent 6"],
    }


# ------------------ Health Check Endpoint -----------------------
@app.get("/health")
def health():
    """
    Health check probe endpoint for Docker and Kubernetes liveness checks.
    """
    return {"status": "healthy"}
