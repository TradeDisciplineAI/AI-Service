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

# Copy project definition and files
COPY pyproject.toml ./
COPY src /app/src
COPY tests /app/tests
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

# Install all project dependencies using uv
RUN uv pip install --system -e .

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_CACHE_DIR=/tmp
ENV HOME=/tmp
ENV UV_CACHE_DIR=/tmp

USER appuser

EXPOSE 8000

# Run Alembic migrations then start FastAPI from the src folder
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
