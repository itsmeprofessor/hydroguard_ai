# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HydroGuard-AI is a flood/weather anomaly detection system consisting of:
- A **FastAPI backend** with a hybrid ML model (Autoencoder + LSTM) for anomaly scoring
- A **Flutter mobile app** for real-time anomaly monitoring
- An **HTML/JS web dashboard** for admin use

## Commands

### Backend

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run API server (from repo root)
python backend/run_server.py
python backend/run_server.py --reload --port 8080

# Run tests
pytest tests/ -v --tb=short

# Run a single test
pytest tests/test_api.py::test_health -v

# Lint + type-check (matches CI)
ruff check backend/ --select E,W,F,I --ignore E501
mypy backend/app/core/config.py backend/app/schemas/__init__.py --ignore-missing-imports

# Smoke test against running server
./backend/smoke_test.sh http://127.0.0.1:8000

# Offline model training
python scripts/train.py --data backend/data/pakistan_weather_2000_2024.csv --use-lstm --epochs 200

# Docker
docker compose up --build
```

### Flutter App

```bash
cd frontend/weather_anomaly_app
flutter pub get
flutter analyze
flutter run                    # default device
flutter run -d chrome          # web
```

## Architecture

### Backend (`backend/app/`)

**Entry point:** `backend/run_server.py` → uvicorn → `app/main.py` (FastAPI app factory)

**Request flow:** Router → `app/services/anomaly_service.py` → ML inference → DB write via `app/db/database.py`

**Routers** (`app/api/routes/`):
- `system.py` — `/health`, `/model/info`
- `prediction.py` — `POST /predict`, `POST /predict/batch`
- `anomalies.py` — `GET /anomalies`, `/anomalies/statistics`, `/anomalies/{id}`
- `risk_analytics.py` — `/risk-map`, `/analytics`, `/database/statistics`
- `training.py` — `POST /train`
- `analytics_aliases.py` — dashboard aliases for `/analytics` and `/database/statistics`

**Anomaly detection** (`app/services/anomaly_service.py`):
- Singleton holding the loaded ML model
- **Hybrid scoring**: Autoencoder reconstruction loss + LSTM sequence context
- **HRI (Human Risk Index)**: `anomaly_score×0.4 + rainfall_intensity×0.35 + regional_vulnerability×0.25`
- **Cloudburst rule engine**: independent physics-based thresholds (precipitation, pressure, humidity, cloud cover) with monsoon-season boost
- **Per-city LSTM buffers** seeded from historical CSV on startup (default: 14 rows, controlled by `HYBRID_WARMUP_ROWS`)
- **Flood-focused feature weights**: `prcp=3.0`, `humidity=2.0`, `pressure=2.0`

**Config** (`app/core/config.py`): Single source of truth for `APIConfig`, `ModelConfig`, and `CloudburstConfig`. All thresholds and weights live here.

**Database** (`app/db/database.py`): SQLAlchemy ORM with repository pattern. `AnomalyRecord` is the only table. SQLite for dev, PostgreSQL for prod (set via `DATABASE_URL`).

**Schemas** (`app/schemas/__init__.py`): All Pydantic v2 request/response models.

**ML models** (`backend/ml/`): `WeatherAutoencoder`, `LSTMAutoencoder`, `HybridAnomalyDetector`. Weights stored in `backend/saved_models/`.

**Preprocessing** (`backend/utils/preprocessing.py`): Feature engineering (season, temporal fields), standard scaling, one-hot encoding.

### Flutter App (`frontend/weather_anomaly_app/lib/`)

State management via `provider` (no Riverpod/Bloc).

**Three providers:** `SettingsProvider` (API URL, notifications, refresh interval) → `LocationProvider` (GPS, city/region) → `WeatherProvider` (fetch + predict, caches results).

**Navigation:** `SplashScreen` → `AppShell` (bottom nav: Home, History, Analytics, Settings)

**API client** (`services/anomaly_api_service.dart`): All HTTP calls to the FastAPI backend.

**Design system** (`core/theme/design_system.dart`): Dark-mode tokens (`DS.bg1`, `DS.text1`, etc.), Poppins font.

**Constants** (`utils/constants.dart`): API base URL, endpoint paths, default values.

### Web Dashboard (`frontend/web_dashboard/admin_dashboard/index.html`)

Static HTML/JS admin panel. Served by FastAPI at `/dashboard`.

## Environment

Copy `.env.example` to `.env`. Key variables:

```
DATABASE_URL=sqlite:///backend/weather_anomalies.db
ADMIN_TOKEN=changeme-set-in-env
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
HYBRID_WARMUP=true
HYBRID_WARMUP_ROWS=14
HYBRID_WARMUP_CSV=backend/data/pakistan_weather_2000_2024.csv
```

## CI

`.github/workflows/ci.yml` runs: ruff lint → mypy type-check → pytest → Docker build + smoke test.

## Key Constraints

- **ML architecture is fixed**: Autoencoder + LSTM hybrid. Do not alter model schema.
- **State management stays `provider`**: No migration to Riverpod or Bloc.
- **SQLite ↔ PostgreSQL**: Dev uses SQLite; multi-worker prod deployments require PostgreSQL (`DATABASE_URL` switch).
- **`asyncio_mode = "auto"`** (pyproject.toml) — all pytest-asyncio tests use auto mode.
