# ============================================================
#  HydroGuard-AI — Production Dockerfile
#  Multi-stage build: deps layer cached separately from code.
# ============================================================

# ── Stage 1: dependency builder ──────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ───────────────────────────────────
FROM python:3.11-slim AS runtime

# curl for HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source (no __pycache__, no .env)
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Runtime dirs (will be overlaid by volume mounts)
RUN mkdir -p backend/data backend/saved_models backend/logs

# Non-root user for security
RUN addgroup --system hydroguard \
    && adduser  --system --ingroup hydroguard hydroguard \
    && chown -R hydroguard:hydroguard /app
USER hydroguard

# Environment defaults (override via docker-compose / -e flags)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DEBUG=false \
    CORS_ORIGINS=* \
    ADMIN_TOKEN=changeme-set-in-env

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

WORKDIR /app/backend
CMD ["python", "run_server.py", "--host", "0.0.0.0", "--port", "8000"]
