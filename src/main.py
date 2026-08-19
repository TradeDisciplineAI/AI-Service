import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import the router we just created
from src.routers.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Agent 2: News & Sentiment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach the routes from routes.py into our main app
app.include_router(router)