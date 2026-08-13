import logging
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import the router we just created
from src.routers.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Agent 2: News & Sentiment API")

# Attach the routes from routes.py into our main app
app.include_router(router)