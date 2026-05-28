# ============================================================
#  HydroGuard-AI — Production Dockerfile v3.1
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

# libgomp1 is required by LightGBM (OpenMP threading).
# python:3.11-slim omits it; without it all lgbm_model.pkl files fail to load.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source (no __pycache__, no .env)
COPY backend/ ./backend/
COPY frontend/ ./frontend/
# Training scripts — invoked by the admin /cities/{city}/train endpoint
# (see app/api/v2/cities.py::_run_training_background).
COPY scripts/ ./scripts/

# Runtime dirs (will be overlaid by volume mounts)
RUN mkdir -p backend/data backend/saved_models backend/logs

# Non-root user for security
RUN addgroup --system hydroguard \
    && adduser  --system --ingroup hydroguard hydroguard \
    && chown -R hydroguard:hydroguard /app
USER hydroguard

# Environment defaults (always override in production via .env or docker-compose)
# PYTHONPATH includes /app so `from scripts.train_city import ...` resolves
# regardless of the working directory.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DEBUG=false \
    CORS_ORIGINS=*

EXPOSE 8000

# Healthcheck using Python (no curl dependency)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request, sys; \
        r = urllib.request.urlopen('http://localhost:8000/health', timeout=8); \
        sys.exit(0 if r.status == 200 else 1)" || exit 1

WORKDIR /app/backend
CMD ["python", "run_server.py", "--host", "0.0.0.0", "--port", "8000"]
