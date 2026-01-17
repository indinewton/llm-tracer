# Multi - stage build for smaller image

FROM python:3.12-slim-bookworm AS builder

# Copy UV from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# copy dependency files
COPY pyproject.toml uv.lock ./

# Use uv sync to create virtual environment
# --frozen: Don't update uv.lock, use exactly what's specified
# --no-dev: Don't install dev dependencies (pytest, etc.)
RUN uv sync --frozen --no-dev

# Production image
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install curl for health checks (optional but recommended)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Copy dependencies from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser src ./src/
COPY --chown=appuser:appuser scripts ./scripts/

# Environment variables
# PYTHONPATH="/app" (not /app/src) so that `src` is treated as a package,
# enabling relative imports like `from .models import ...` in src/server.py
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV="/app/.venv" \
    PYTHONPATH="/app"

USER appuser

EXPOSE 8001

# health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run as src.server (module path) to enable relative imports within the src package
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8001"]
