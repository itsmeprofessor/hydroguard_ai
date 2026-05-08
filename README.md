# HydroGuard-AI v3.1

**Self-configuring, adaptive flood and cloudburst intelligence platform for Pakistan — powered by per-city hybrid deep learning and live weather data.**

[![CI](https://github.com/zainmohyuddin/hydroguard_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/zainmohyuddin/hydroguard_ai/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.15-FF6F00.svg)](https://tensorflow.org/)
[![License](https://img.shields.io/badge/license-Academic-lightgrey.svg)](#license)

---

## What is HydroGuard-AI?

HydroGuard-AI is a full-stack, production-grade platform for **real-time flood risk and cloudburst detection** across Pakistani cities. It automatically discovers cities from any CSV dataset, trains per-city hybrid ML models (Autoencoder + LSTM + Bahdanau Attention), fetches live weather observations, monitors for feature drift, and exposes everything through a secure FastAPI backend and two web frontends.

Key design principle: **schema-aware, city-scalable, feature-adaptive, self-configuring.**

- Add a new city to the CSV → the system detects it, trains a model, registers it, and exposes endpoints — zero code changes.
- Add new meteorological features (e.g. `cape`, `soil_moisture`) → the dataset profiler detects them, assigns weights, and incorporates them into training automatically.
- Connect OpenWeatherMap or Open-Meteo → every city's risk is computed against real-time observations, not historical defaults.

---

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [ML Pipeline](#ml-pipeline)
- [Live Weather](#live-weather)
- [Model Registry](#model-registry)
- [Drift Detection](#drift-detection)
- [Frontends](#frontends)
- [Deployment](#deployment)
- [Testing](#testing)
- [Security](#security)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Credits](#credits)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Citizen Web App  /  Admin Dashboard             │
│           (React 18 via CDN · no build step · polling/WS)           │
└────────────────────────┬────────────────────────────────────────────┘
                         │ HTTP / WSS
              ┌──────────▼──────────┐
              │   Nginx  :80/:443   │   TLS · HSTS · CSP
              │ rate-limit · gzip   │   auth-zone 5/min
              └──────────┬──────────┘   predict-zone 60/min
                         │
              ┌──────────▼──────────────────────────────┐
              │         FastAPI  :8000                   │
              │  ┌──────────────────────────────────┐   │
              │  │ Auth · JWT · Refresh rotation    │   │
              │  │ Rate limit (shared limiter)      │   │
              │  │ CORS (origin-specific in prod)   │   │
              │  ├──────────────────────────────────┤   │
              │  │  Service Layer                   │   │
              │  │  ├─ CityModelService (lazy-load) │   │
              │  │  ├─ WeatherService  (live data)  │   │
              │  │  ├─ DriftService    (PSI monitor) │  │
              │  │  ├─ ModelRegistry  (provenance)  │   │
              │  │  └─ DatasetProfiler (adaptive)   │   │
              │  ├──────────────────────────────────┤   │
              │  │  Per-City Hybrid ML               │   │
              │  │  AE  + LSTM-Reconstructor         │   │
              │  │       + BahdanauAttention         │   │
              │  └───────────┬──────────────────────┘   │
              └──────────────┼──────────────────────────┘
                             │
           ┌─────────────────┴──────────────────────┐
           ▼                                         ▼
  ┌──────────────────┐                    ┌────────────────────┐
  │  PostgreSQL 16   │                    │    Redis 7         │
  │  AnomalyRecord   │                    │  Rate-limit state  │
  │  TrainingRecord  │                    │  Weather cache     │
  │  User            │                    │  (WS bridge v3.2)  │
  └──────────────────┘                    └────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │  Backup sidecar (pg_dump daily · 7-day retention · auto-prune)   │
  └──────────────────────────────────────────────────────────────────┘
```

### Dynamic city discovery flow

```
CSV with city column  ──►  DatasetProfiler.profile()
                               └─► dataset_profile.json
                                     • cities discovered
                                     • feature types inferred
                                     • weights auto-assigned
                                     • sequence length suggested
                      ──►  CityModelService.refresh_registry()
                               └─► all cities exposed via /cities
                               └─► city-specific training triggered
                      ──►  ModelRegistry.register()
                               └─► full provenance saved
                      ──►  DriftService.record()
                               └─► PSI monitoring begins
```

---

## Features

### Adaptive Intelligence
| Feature | Description |
|---|---|
| **Dynamic city discovery** | New city in CSV → auto-detected, trained, registered, served. Zero code changes. |
| **Feature-adaptive pipeline** | New columns auto-classified, weighted, and incorporated into training. |
| **Dataset profiler** | Inspects any CSV: cities, feature types, temporal resolution, completeness, SHA256. |
| **Sequence length tuning** | Profiler suggests 7, 14, or 21-day windows based on dataset size and resolution. |
| **Model registry** | Every trained model recorded with architecture, dataset SHA256, git hash, metrics, calibration. |
| **PSI drift detection** | Population Stability Index monitored per city. WARN at 0.10, CRIT at 0.20 → retrain flagged. |
| **Continuous retraining** | POST `/cities/{city}/train` (admin) hot-swaps the in-memory model without restart. |

### ML Pipeline (per city)
| Component | Details |
|---|---|
| **Autoencoder** | Dense [64→32→16→8→16→32→64→output]. MSE reconstruction loss. Dropout 0.20. |
| **LSTM-Reconstructor** | LSTM(64, return_seq) → BahdanauAttention(32) → LSTM(32) → Dense(input_dim). Predicts next feature step (MSE), not zero-label BCE. |
| **Hybrid score** | 0.55 × AE + 0.45 × LSTM. Sigmoid-normalised z-scores from per-city calibration. |
| **Confidence** | 1 − normalised entropy of hybrid score (0 = totally uncertain, 1 = certain). |
| **HRI (0-100)** | 0.40 × anomaly + 0.35 × rainfall + 0.25 × regional vulnerability. |
| **Cloudburst engine** | Precipitation (0.45) + pressure (0.25) + humidity (0.20) + cloud cover (0.10). Monsoon × 1.2 multiplier. |
| **Fallback heuristic** | Rule-based scoring when city model not yet trained. Same output dict, `source="heuristic"`. |

### Live Weather
| Provider | Setup |
|---|---|
| **Open-Meteo** | Free, no API key. Set `WEATHER_API_PROVIDER=open-meteo` (default). |
| **OpenWeatherMap** | Set `WEATHER_API_PROVIDER=openweathermap` + `OPENWEATHER_API_KEY`. |
| **Cache** | In-memory TTL (configurable, default 10 min). Per-endpoint TTL in citizen app. |
| **Fallback** | If live weather fails, citizen app falls back to `/cities/{city}/risk` (historical defaults). |

### Security
| Control | Implementation |
|---|---|
| **Mandatory secrets** | JWT_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, ADMIN_TOKEN. App **refuses to start** if missing or placeholder in production. |
| **JWT HS256** | 30-min access + 7-day refresh with rotation and reuse detection (all sessions nuked on reuse). |
| **Registration** | `role` field removed from public endpoint. All registrations default to `USER`. |
| **Rate limiting** | Shared SlowAPI limiter on `/predict` (60/min), `/predict/batch` (20/min). Nginx auth zone: 5/min. |
| **HTTPS** | Nginx HTTPS redirect + HSTS + TLS 1.2/1.3 (enable by adding certs to `nginx/certs/`). |
| **Security headers** | X-Frame-Options DENY, X-Content-Type-Options nosniff, CSP, Referrer-Policy. |
| **WebSocket auth** | `/ws/anomalies` and `/ws/risk-map` require JWT `?token=`. `/ws/health` is public (intentional). |
| **CORS** | Wildcard only in dev; specific origins with credentials in production. |

---

## Tech Stack

| Layer | Stack |
|---|---|
| **Backend** | Python 3.11, FastAPI 0.111, Uvicorn, Pydantic v2, SQLAlchemy 2, SlowAPI |
| **ML** | TensorFlow 2.15+, Keras 3, NumPy, pandas, scikit-learn, joblib |
| **Auth** | python-jose (JWT HS256), bcrypt |
| **Live Weather** | Open-Meteo (free) / OpenWeatherMap (via httpx async) |
| **Realtime** | FastAPI WebSocket + ConnectionManager (Redis pub/sub planned for multi-worker) |
| **Database** | PostgreSQL 16 (prod), SQLite (dev) |
| **Cache** | Redis 7 (rate-limit + weather cache + WS bridge) |
| **Frontends** | React 18 via CDN + Babel-Standalone (no build step) |
| **Proxy** | Nginx (TLS, security headers, rate limiting, gzip) |
| **Container** | Docker Compose 3.9; multi-stage Dockerfile |
| **CI** | GitHub Actions (ruff, mypy, pytest, Docker build) |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker + Docker Compose (for full stack)
- Git

### 1. Clone and install

```bash
git clone https://github.com/zainmohyuddin/hydroguard_ai.git
cd hydroguard_ai
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r backend/requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
```

Edit `.env` — fill in at minimum:
```bash
# Generate a strong key:
python -c "import secrets; print(secrets.token_hex(32))"

JWT_SECRET_KEY=<generated-value>
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
ADMIN_TOKEN=<strong-admin-token>
```

### 3. Run (local dev — SQLite, no Docker needed)

```bash
# Start API
python backend/run_server.py --reload --port 8000

# Start citizen web app (separate terminal)
cd frontend/citizen_app && python -m http.server 5500
# Open: http://localhost:5500

# Admin dashboard: visit http://localhost:8000/frontend
```

### 4. Run (full stack with Docker)

Install Docker Desktop (Windows) — Step by Step
1. Check system requirements

Make sure:

Windows 10/11 (64-bit)
Virtualization enabled in BIOS (Intel VT-x / AMD-V)
2. Enable WSL 2 (required)

Open PowerShell as Admin and run:

wsl --install

If already installed, just ensure WSL2 is default:

wsl --set-default-version 2
3. Download Docker Desktop

Go to official site:

https://www.docker.com/products/docker-desktop/

Click Download for Windows

4. Install Docker Desktop

Run the downloaded .exe file

During installation:

Enable “Use WSL 2 instead of Hyper-V”
Keep default settings unless you know what you're changing
5. Restart your PC

This is required after installation.

6. Start Docker Desktop

Open:

Start Menu → Docker Desktop

Wait until it says “Docker is running”

7. Verify installation

Open PowerShell or WSL and run:

docker --version
docker compose version

If both show versions → success.

8. (Important) Enable WSL integration

Inside Docker Desktop:

Go to Settings → Resources → WSL Integration
Enable your distro (Ubuntu or others)
9. Test with a container

Run:

docker run hello-world

If you see a success message → everything is working.

After this

You can now safely run:

docker compose up --build

```bash
docker compose up --build
# API:       http://localhost:8000
# Dashboard: http://localhost:80
# Docs:      http://localhost:8000/docs
Access Database
psql -U hydroguard
\l
\c hydroguard
\dt
SELECT * FROM users;
SELECT * FROM anomalies;
SELECT * FROM anomalies LIMIT 10;
\d anomalies
\q 
```

### 5. Train city models

For CPU BOOST (in powershell)
$env:OMP_NUM_THREADS="12"
$env:TF_NUM_INTRAOP_THREADS="12"
$env:TF_NUM_INTEROP_THREADS="4"
$env:TF_CPP_MIN_LOG_LEVEL="2"

```bash
# Profile the dataset first
python scripts/train_city.py --profile

# List discovered cities
python scripts/train_city.py --list-cities

# Train all cities
python scripts/train_city.py --all --epochs 150
python scripts/train_city.py --all --data .\backend\data\pakistan_weather_2000_2024.csv --epochs 150

# Train one city
python scripts/train_city.py --city Islamabad --epochs 200

# AE-only mode (small dataset)
python scripts/train_city.py --city Gilgit --no-lstm
```

---

## Configuration

All configuration via environment variables. See `.env.example` for the full list.

### Required (app refuses to start in production if missing)

| Variable | Description |
|---|---|
| `JWT_SECRET_KEY` | HS256 signing key. Min 32 chars. Generate with `secrets.token_hex(32)`. |
| `POSTGRES_PASSWORD` | PostgreSQL password. |
| `REDIS_PASSWORD` | Redis auth password. |
| `ADMIN_TOKEN` | Legacy `X-Admin-Token` header value. |

> **DEBUG mode bypass**: In `DEBUG=true`, missing secrets log a warning but don't exit. Never use DEBUG in production.

### Optional (with defaults)

| Variable | Default | Description |
|---|---|---|
| `WEATHER_API_PROVIDER` | `open-meteo` | `open-meteo` or `openweathermap` |
| `OPENWEATHER_API_KEY` | — | Required only for OpenWeatherMap |
| `WEATHER_CACHE_TTL_SECONDS` | `600` | Live weather cache TTL |
| `HYBRID_WARMUP` | `true` | Seed LSTM buffers at startup |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `DATABASE_URL` | SQLite | PostgreSQL in prod |
| `DEBUG` | `false` | Dev mode (loosens secret checks) |

---

## API Reference

Interactive docs at `http://localhost:8000/docs` (Swagger) and `/redoc`.

### Key Endpoints

#### Cities & Risk
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/cities` | none | List all discovered cities + model availability |
| `GET` | `/cities/overview` | none | Risk snapshot for all cities |
| `GET` | `/cities/{city}/risk` | none | Current risk (historical defaults) |
| `POST` | `/cities/{city}/predict` | none | Risk from provided weather data |
| `GET` | `/cities/{city}/forecast` | none | 7-day outlook |
| `GET` | `/cities/{city}/alerts` | none | Recent anomaly alerts |
| `GET` | `/cities/{city}/status` | none | Model status + metrics |
| `POST` | `/cities/{city}/train` | admin | Trigger background training |
| `POST` | `/cities/refresh` | admin | Rescan CSV + disk for new cities |

#### Live Weather
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/weather/{city}/current` | none | Live weather + instant risk prediction |
| `GET` | `/weather/{city}/forecast` | none | N-day live forecast + per-day risk |
| `GET` | `/weather/overview` | none | All cities, live conditions + risk |

#### System & Monitoring
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | none | Full health: model status, drift state, registry summary, WS counts |
| `GET` | `/drift` | none | PSI drift state for all cities |
| `GET` | `/drift/{city}` | none | Drift check history for a city |
| `GET` | `/model/registry` | none | Full model registry |
| `GET` | `/model/registry/{city}` | none | Registry history for a city |

#### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | none | Create account (always `role=USER`) |
| `POST` | `/auth/login` | none | Issue access + refresh tokens |
| `POST` | `/auth/refresh` | none | Rotate refresh token (reuse detection) |
| `GET` | `/auth/me` | JWT | Current user profile |
| `POST` | `/auth/logout` | JWT | Invalidate refresh token |

#### Legacy (authenticated)
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/predict` | JWT | Global model prediction (60/min) |
| `POST` | `/predict/batch` | JWT | Batch prediction (20/min) |
| `POST` | `/train` | admin | Retrain global model |
| `GET` | `/risk-map` | none | HRI for all cities |

#### WebSockets
| Path | Auth | Description |
|---|---|---|
| `WS /ws/anomalies?token=` | JWT | Server-push anomaly events |
| `WS /ws/risk-map?token=` | JWT | Server-push risk-map updates |
| `WS /ws/health` | **none** | Public health stream |

### Standardised Prediction Response
```json
{
  "city":          "Islamabad",
  "city_slug":     "islamabad",
  "risk_level":    "Low | Medium | High",
  "anomaly_score": 0.34,
  "confidence":    0.82,
  "is_anomaly":    false,
  "ae_score":      0.29,
  "lstm_score":    0.38,
  "hri_score":     34,
  "source":        "city_model | heuristic | heuristic_fallback",
  "timestamp":     "2026-05-02T10:30:00+00:00",
  "is_live":       true,
  "prcp":          3.2,
  "humidity":      62,
  "pressure":      1008.4,
  "tmax":          31.5
}
```

---

## ML Pipeline

### Training Objectives (v3.1 — Fixed)

**Autoencoder** — reconstruction loss (MSE). Learns the normal feature distribution.
Anomaly score = how far a sample is from the learned normal space.

**LSTM-Reconstructor** — next-step prediction loss (MSE). Learns normal temporal dynamics.
Anomaly score = how unexpected the current sequence is relative to learned dynamics.

> **Bug fixed from v3.0**: The LSTM was previously trained with `y = zeros` + binary cross-entropy — a mathematically invalid objective that caused the model to always predict 0. v3.1 replaces this with proper next-step MSE reconstruction.

### Score Normalisation

Both AE and LSTM errors are normalised via **sigmoid of z-score**:
```
z = (error - mean_train) / std_train
score = sigmoid(z)  ∈ (0, 1)
```
This uses the full calibration triplet `[mean, std, p99]` (v3.0 only used p99).

### Confidence

```
H = -p·log₂(p) − (1−p)·log₂(1−p)   [binary entropy of hybrid score p]
confidence = 1 − H                    [0 = uncertain, 1 = certain]
```
v3.0 used `|hybrid − 0.5| × 2` which had no statistical meaning.

### Temporal Split (Leak-Free)

```
df.sort_values("date")  →  df[:80%] → TRAIN   df[80%:] → VAL
pre.fit(df_train)       # FIT on TRAIN only
pre.transform(df_val)   # transform-only on VAL
```
LSTM sequences are built within each split independently.

### Adding New Features

No code changes required. If your CSV gains new columns:

```bash
# Reprofile the dataset
python scripts/train_city.py --profile

# Retrain — new features are auto-discovered, classified, and weighted
python scripts/train_city.py --all
```

The `DatasetProfiler` classifies features by name against known meteorological vocabularies and assigns default importance weights. Unknown features default to `weight=1.0`. Override weights in `app/core/config.py` → `ModelConfig.FEATURE_WEIGHTS`.

---

## Live Weather

### Open-Meteo (default, free)

No API key needed. Set in `.env`:
```bash
WEATHER_API_PROVIDER=open-meteo
```

### OpenWeatherMap

<<<<<<< HEAD
```bash
WEATHER_API_PROVIDER=openweathermap
OPENWEATHER_API_KEY=your-free-key-from-openweathermap.org
```

### How it works

1. `GET /weather/{city}/current` fetches live observations from Open-Meteo or OWM.
2. The live observations are fed into the city's ML model (or heuristic fallback).
3. Response includes both the weather data and the risk prediction.
4. The citizen app tries `/weather/{city}/current` first, falls back to `/cities/{city}/risk`.
5. Live data responses include `"is_live": true` — the citizen app shows a green **LIVE** badge.

### Extending to More Providers

Implement `_normalise_<provider>(data, city) → Dict` in `app/services/weather_api.py` and add a branch in `WeatherService.get_current()`. No changes needed elsewhere.

---

## Model Registry

Every trained model is recorded in `backend/saved_models/registry.json` with full provenance:

```json
{
  "islamabad": {
    "city_slug":       "islamabad",
    "version":         3,
    "promoted_at":     "2026-05-02T10:00:00+00:00",
    "status":          "active",
    "git_commit":      "a3f91c2",
    "architecture":    "ae_lstm_attention",
    "input_dim":       18,
    "sequence_length": 7,
    "train_date_start": "2000-01-01",
    "train_date_end":   "2019-12-31",
    "val_date_start":   "2020-01-01",
    "val_date_end":     "2024-12-31",
    "dataset_sha256":  "e3b0c44298fc1c149...",
    "n_train":          7300,
    "n_val":            1826,
    "ae_val_loss":      0.00312,
    "lstm_val_loss":    0.00891,
    "ae_threshold_p99": 0.0412,
    "hyperparameters":  { ... },
    "calibration_params": {
      "ae_mean":  0.0031, "ae_std":  0.0008, "ae_p99": 0.0412,
      "lstm_mean": 0.0089, "lstm_std": 0.0021, "lstm_p99": 0.0312
    }
  }
}
```

Access via:
- `GET /model/registry` — all cities
- `GET /model/registry/{city}` — full history for one city

---

## Drift Detection

The PSI (Population Stability Index) drift monitor tracks feature distributions continuously.

| PSI | Status | Action |
|---|---|---|
| < 0.10 | OK | No action |
| 0.10 – 0.20 | WARN | Investigate |
| > 0.20 | **CRITICAL** | `needs_retrain = true` |

Monitored features: `prcp`, `humidity`, `pressure`, `cloud_cover`.

Check interval: every 100 predictions per city.
Reference window: last 500 predictions.

```bash
# Check drift state
curl http://localhost:8000/drift

# Specific city
curl http://localhost:8000/drift/islamabad
```

When `needs_retrain = true` for a city, trigger retraining:
```bash
curl -X POST http://localhost:8000/cities/islamabad/train \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"epochs": 150}'
```

After retraining, the drift flag is automatically acknowledged.

---

## Frontends

### Citizen Web App (`frontend/citizen_app/`)

Public-facing, mobile-first, no authentication required.

- **5 screens**: Home · Forecast · Alerts · Learn · Settings
- **Live weather**: Shows a green **LIVE** badge when data comes from Open-Meteo/OWM
- **Adaptive city list**: Fetched from `/cities` — reflects whatever is in the dataset
- **Light/dark mode**, language picker (EN/UR/PA/PS/SD/BL — UI only, translations pending)
- **5-minute polling** with per-endpoint TTL cache
- **Graceful degradation**: falls back gracefully when live weather or model is unavailable

Served at `/citizen` in production (FastAPI static mount). For local dev:
```bash
cd frontend/citizen_app && python -m http.server 5500
```

### Admin Dashboard (`frontend/web_dashboard/admin_dashboard/`)

JWT-authenticated. For system operators.

- Pakistan SVG risk map with city circles colored by HRI
- Real-time WebSocket feed (`/ws/anomalies`, `/ws/risk-map`)
- Per-city model status and training controls
- Analytics, database statistics, user management

Served at `/frontend` or `/dashboard` by the API, and at `/` by Nginx in Docker.

---

## Deployment

### Docker Compose (full stack)

```bash
# Copy and fill in required secrets
cp .env.example .env
# edit .env — set JWT_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, ADMIN_TOKEN

docker compose up --build -d

# Check status
docker compose ps
docker compose logs hydroguard-api --tail 50
```

Services started:
- `postgres:16-alpine` — database (port 5432, localhost-only)
- `redis:7-alpine` — cache + rate-limit state (port 6379, localhost-only)
- `hydroguard-api` — FastAPI (port 8000)
- `nginx:alpine` — reverse proxy (ports 80, 443)
- `hydroguard-backup` — daily pg_dump with 7-day retention

### HTTPS / TLS

1. Obtain a certificate (Let's Encrypt via certbot, or Caddy):
   ```bash
   certbot certonly --standalone -d yourdomain.com
   cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/
   cp /etc/letsencrypt/live/yourdomain.com/privkey.pem  nginx/certs/
   ```
2. Uncomment the HTTPS redirect in `nginx/nginx.conf` (line ~40: `return 301 https://...`).
3. Restart: `docker compose restart nginx`

### Resource Limits (already configured in docker-compose.yml)

| Service | Memory | CPU |
|---|---|---|
| `hydroguard-api` | 2 GB | 2 cores |
| `postgres` | 512 MB | 1 core |
| `redis` | 192 MB | 0.5 cores |
| `nginx` | 128 MB | 0.5 cores |

---

## Testing

```bash
# Run tests
pytest tests/ -v --tb=short

# Type checking
mypy backend/app/core/config.py backend/app/schemas/__init__.py --ignore-missing-imports

# Linting
ruff check backend/ --select E,W,F,I --ignore E501

# Smoke test against running server
./backend/smoke_test.sh http://127.0.0.1:8000
```

### CI Pipeline (`.github/workflows/ci.yml`)

1. **Lint** — ruff + mypy
2. **Test** — pytest with PostgreSQL service container
3. **Docker build** — multi-stage build + `curl /health` smoke test
4. **Deploy** — placeholder (uncomment to deploy)

> CI runs tests against PostgreSQL to catch Postgres-only behaviour. SQLite is only for local development.

---

## Security

### Authentication
- **JWT HS256** — 30-min access tokens, 7-day refresh with rotation
- **Reuse detection** — presenting a recycled refresh token invalidates ALL sessions for that user
- **Mandatory secrets** — `JWT_SECRET_KEY` cannot be empty or a placeholder in production
- **Roles** — `USER`, `ANALYST`, `ADMIN`. Role can only be set by an admin — public registration always creates `USER`

### Transport
- **TLS 1.2/1.3 only** — SSLv3, TLS 1.0, TLS 1.1 disabled
- **HSTS** — max-age 1 year, includeSubDomains
- **WebSocket auth** — JWT via `?token=` query param (browsers cannot send custom headers on WS handshake)

### Application
- **Rate limiting** — Nginx edge (5/min auth, 60/min predict) + SlowAPI app-level (shared limiter)
- **Security headers** — X-Frame-Options DENY, nosniff, XSS-Protection, CSP, Referrer-Policy
- **Input validation** — Pydantic v2 on all endpoints; training endpoint validates CSV columns before execution
- **CORS** — wildcard only in dev; credential-bearing requests require explicit origins

### Secrets Rotation
1. Generate new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `.env`
3. `docker compose restart hydroguard-api`
4. All existing tokens immediately invalid (users must re-login)

---

## Roadmap

### v3.2 (next)
- [ ] Pre-compile frontends with Vite (eliminate `eval`-based Babel in production)
- [ ] httpOnly Secure SameSite=Strict refresh-token cookie (eliminate sessionStorage risk)
- [ ] Redis pub/sub WebSocket bridge for multi-worker deployments
- [ ] Real i18n message bundles (English + Urdu)
- [ ] Prometheus metrics endpoint + Grafana board
- [ ] Alembic migration scripts (replace `create_all` at startup)
- [ ] `pytest-benchmark` for inference latency SLO (p99 < 200 ms)
- [ ] Conformal prediction confidence intervals

### v3.3
- [ ] Temporal Fusion Transformer for probabilistic 7-day rainfall forecasting (P10/P50/P90)
- [ ] XGBoost channel with engineered features (rolling means, lags, monsoon indicator)
- [ ] Learned fusion (stacking) to replace fixed 0.55/0.45 hybrid weights
- [ ] PMD / ECMWF historical flood event labels for supervised calibration
- [ ] Active learning loop (citizen-confirmed alerts feed back into training)

### v4.0
- [ ] Kubernetes Helm chart with HPA
- [ ] MLflow experiment tracking + model registry
- [ ] Physics-informed features (soil moisture, river discharge, terrain DEM)
- [ ] Mobile app (React Native, shared code with citizen web)
- [ ] Multi-region deployment with active-passive failover

---

## Contributing

PRs welcome. Please:
1. Run `ruff check` and `mypy` before opening a PR
2. Add tests for new endpoints or ML changes
3. For non-trivial changes, open an issue first to discuss the approach
4. Never commit `.env` or any file containing real secrets

---

## License

Released for academic and demonstration purposes. See `LICENSE`.

---

## Credits

**Author:** Zain Mohyuddin — system architect & ML developer (`zain.mohyuddin09@gmail.com`)

**Data:** Pakistan weather dataset 2000–2024, 10 cities, daily observations

**UI Design:** Citizen app design from `frontend design for fyp/NewWebAPP.zip`

**Built with:** FastAPI · TensorFlow/Keras · React 18 · Open-Meteo · Nginx · PostgreSQL · Redis

---

*HydroGuard-AI — Early warning saves lives.*
=======

>>>>>>> af86e3772d12dbe9d872a56e2ea7b503acef9d39
