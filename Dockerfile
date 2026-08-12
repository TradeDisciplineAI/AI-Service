# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.13-slim-bookworm

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# Create a non-root user for security
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser

# Copy our project files
COPY pyproject.toml ./
COPY src /app/src
COPY .env /app/.env

# Install dependencies directly into the system using uv
RUN uv pip install --system fastapi "uvicorn[standard]" langchain langgraph langchain-google-genai pydantic python-dotenv newsapi-python tweepy praw duckduckgo-search

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# Start FastAPI from the src folder
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]