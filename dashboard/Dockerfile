# ==========
# Multi-stage Dockerfile for Reflex Dashboard
#
# Usage: Check Justfile for commands
#
# Ports (from rxconfig.py):
#   - 3000: Frontend (Next.js)
#   - 8002: Backend (FastAPI)
# ==========

# Stage 1: Base ----
FROM python:3.12-slim-bookworm AS base
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Node.js once in base as all stages need it
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Development ----
FROM base AS development

# Use cache mounts for faster dependency installs
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache, target=/root/.cache/uv \
    uv sync --frozen

EXPOSE 3000 8002

HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/ping || exit 1

CMD ["uv", "run", "reflex", "run", "--loglevel", "debug"]

# Stage 3: Builder----
FROM base AS builder

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache, target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY rxconfig.py ./
COPY dashboard/ ./dashboard/
COPY assets/ ./assets/

RUN uv run reflex init

# Stage 4: Production ----
FROM base as production

RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy only what's needed from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/.web /app/.web
COPY --from=builder --chown=appuser:appuser /app/rxconfig.py /app/
COPY --from=builder --chown=appuser:appuser /app/dashboard /app/dashboard
COPY --from=builder --chown=appuser:appuser /app/assets /app/assets

USER appuser

EXPOSE 3000 8002

ENV REFLEX_ENV=prod
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/ping || exit 1

CMD ["uv", "run", "reflex", "run", "--env", "prod"]