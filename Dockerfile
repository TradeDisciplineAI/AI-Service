# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.13-slim-bookworm

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# Create a non-root user for security and set /app ownership
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    chown -R appuser:appgroup /app

# Copy project definition and files as appuser
COPY --chown=appuser:appgroup pyproject.toml README.md ./
COPY --chown=appuser:appgroup src /app/src
COPY --chown=appuser:appgroup tests /app/tests
COPY --chown=appuser:appgroup alembic.ini /app/alembic.ini
COPY --chown=appuser:appgroup alembic /app/alembic

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_CACHE_DIR=/tmp
ENV HOME=/tmp
ENV UV_CACHE_DIR=/tmp

USER appuser

# Install all project dependencies using uv into .venv as appuser
RUN uv sync

EXPOSE 8000

# Run Alembic migrations then start FastAPI from the src folder
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
