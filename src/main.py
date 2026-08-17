import logging
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import routers
from src.routers.routes import router as agent2_router
from src.routers.agent3_router import router as agent3_router
from src.routers.agent6_router import router as agent6_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI Trading Service API (Agents 1, 2, 3 & 6)")

# Attach routers
app.include_router(agent2_router)
app.include_router(agent3_router)
app.include_router(agent6_router)

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "AI-Service", "agents": ["Agent 1", "Agent 2", "Agent 3", "Agent 6"]}