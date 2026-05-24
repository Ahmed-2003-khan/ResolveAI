# ── Base stage ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for asyncpg + sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# ── Dependencies stage ─────────────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install hatchling && \
    pip install -e ".[dev]"

# ── Development stage ──────────────────────────────────────────────────────────
FROM deps AS development

# Bind-mount the source in docker-compose; no COPY needed here
USER appuser

# ── Production stage ───────────────────────────────────────────────────────────
FROM deps AS production

COPY --chown=appuser:appgroup . .
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
