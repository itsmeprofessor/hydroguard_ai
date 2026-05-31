# HydroGuard-AI v3.3

**Production-grade flood and cloudburst intelligence platform for Pakistan — powered by per-city hybrid deep learning, live weather data, and a full Flutter mobile/web app.**

[![CI](https://github.com/itsmeprofessor/hydroguard_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/itsmeprofessor/hydroguard_ai/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![Flutter](https://img.shields.io/badge/Flutter-3.41-02569B.svg)](https://flutter.dev/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.15-FF6F00.svg)](https://tensorflow.org/)
[![License](https://img.shields.io/badge/license-Academic-lightgrey.svg)](#license)

---

## What is HydroGuard-AI?

HydroGuard-AI is a full-stack, production-grade platform for **real-time flood risk detection and early warning** across Pakistani cities. It trains per-city hybrid ML models, fetches live weather from WeatherAPI, monitors feature drift, and delivers risk intelligence through a secure FastAPI backend and a Flutter mobile/web app.

**6 cities trained and live:** Islamabad · Karachi · Lahore · Peshawar · Quetta · Gilgit

**Core design principles:**
- Per-city models capture each city's unique seasonal patterns, monsoon profiles, and topographic vulnerability
- Every prediction returns a calibrated flood probability — not a binary alarm
- Role-based access: Citizens get risk alerts, Admins get operational control

> **Platform framing:** HydroGuard-AI produces **calibrated probabilistic risk estimates** from live weather data. `ALERT` tier means elevated probability of hazardous conditions — not a guaranteed flood or an evacuation order.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [ML Pipeline](#ml-pipeline)
- [Flutter App](#flutter-app)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Live Weather](#live-weather)
- [Deployment](#deployment)
- [Testing](#testing)
- [Security](#security)
- [Credits](#credits)

---

## Architecture

```
Browser / Mobile
      │
      ▼
nginx (port 80/443)
  ├── /           → Flutter web app  (frontend/citizen_flutter_app/build/web/)
  ├── /auth/*     → FastAPI backend  (hydroguard-api:8000)
  ├── /api/*      → FastAPI backend
  ├── /health     → FastAPI backend
  └── /ws/*       → FastAPI WebSocket (hydroguard-api:8000)
            │
            ▼
      FastAPI (Python 3.11)
            │
  ┌─────────┴──────────┐
  │                    │
PostgreSQL 16      Redis 7
(users, anomalies) (rate-limit, WS state)
```

### Per-City ML Inference Flow

```
Live WeatherAPI data
        │
        ▼
WeatherDataPreprocessorV2 (fitted per city, no leakage)
        │
        ├──► Autoencoder branch  →  ECDFScaler  →  ae_percentile [0,1]
        │
        ├──► TCN branch (CausalTCN, seq_len=30)  →  ECDFScaler  →  tcn_percentile [0,1]
        │     (activates after 30-observation warm-up buffer fills)
        │
        └──► FusionModel (LightGBM)  →  IsotonicCalibrator
                    │
                    ▼
         event_probability [0,1]  +  hri_score [0-100]
         alert_tier_label (NORMAL / ADVISORY / ALERT)
         risk_band (Low / Moderate / High / Severe)
         SHAP drivers  +  MC Dropout uncertainty
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, FastAPI 0.111, Uvicorn, Pydantic v2, SQLAlchemy 2, Alembic |
| **ML** | TensorFlow 2.15, Keras 3, LightGBM, scikit-learn, joblib, NumPy, pandas |
| **ML Models** | Autoencoder + CausalTCN + LightGBM FusionModel + IsotonicCalibrator (per city) |
| **Uncertainty** | Monte Carlo Dropout, Mahalanobis OOD detection |
| **Auth** | JWT HS256 (python-jose), bcrypt, refresh-token rotation with reuse detection |
| **Live Weather** | WeatherAPI.com (primary) · OpenWeatherMap (fallback) · Open-Meteo (free fallback) |
| **Realtime** | FastAPI WebSocket + LocalBroadcaster → RedisBroadcaster (auto-scales) |
| **Database** | PostgreSQL 16 (production), SQLite (local dev) |
| **Cache** | Redis 7 (rate-limit, WS state, weather cache) |
| **Frontend** | Flutter 3.41 / Dart 3.11 — compiled to web + Android/iOS |
| **State Management** | Riverpod 2.6 |
| **Navigation** | GoRouter 14.6 with role-based redirect guard |
| **HTTP Client** | Dio 5.7 with auth interceptor + automatic 401 refresh |
| **Maps** | flutter_map 7.0 + OpenStreetMap tiles |
| **Charts** | fl_chart 0.70 |
| **Proxy** | Nginx (TLS, security headers, rate limiting, gzip) |
| **Container** | Docker Compose (5 services), multi-stage Dockerfile |
| **CI** | GitHub Actions (ruff, mypy, pytest, Docker build) |

---

## ML Pipeline

### Architecture (per city, fixed — do not change)

| Component | Details |
|---|---|
| **Autoencoder** | Dense [64→32→16→latent 8→16→32→64→output]. Dropout 0.20. Physics-weighted MSE loss (prcp×3, pressure×2.5, humidity×2). Trained on fair-weather rows only. |
| **CausalTCN** | filters=128, kernel=3, dilations=[1,2,4,8,16,32], seq_len=30. Receptive field = 127 obs (~4 months). Next-step reconstructor. |
| **FusionModel** | LightGBM binary classifier on [ae_percentile, tcn_percentile, derived features]. |
| **IsotonicCalibrator** | Calibrates raw LightGBM output → calibrated `event_probability ∈ [0,1]`. |
| **ECDFScaler** | Maps reconstruction errors to uniform [0,1] percentile via empirical CDF. |
| **OOD Detector** | Mahalanobis distance on training features. Non-blocking — sets elevated uncertainty flag. |
| **MC Dropout** | N stochastic forward passes → `epistemic_uncertainty`, `model_entropy`, `prediction_stability`. |

> **Karachi-specific:** 9 additional coastal features (sea surface temp, sea-level pressure anomaly, salinity proxy, etc.) are computed and included in training.

### Saved Model Layout

```
backend/saved_models/city_models/<slug>/
  autoencoder.keras        Autoencoder branch (Keras 3)
  tcn_reconstructor.keras  TCN branch (Keras 3)
  ae_ecdf.pkl              ECDFScaler for AE errors
  tcn_ecdf.pkl             ECDFScaler for TCN errors
  lgbm_model.pkl           LightGBM FusionModel
  calibrator.pkl           IsotonicCalibrator
  preprocessor_v2.joblib   WeatherDataPreprocessorV2
  ood_detector.pkl         OOD Detector
  cal_data.npz             Calibration arrays (held-out split)
  training_metrics.json    Training provenance + evaluation metrics
  calibration_audit.json   ECE, reliability curve
  operational_metrics.json Runtime snapshot
```

### Training

```powershell
# Train all cities (recommended: set CPU threads first)
$env:OMP_NUM_THREADS="12"; $env:TF_NUM_INTRAOP_THREADS="12"
python scripts/train_city.py --all --data backend/data/pakistan_weather_2000_2024.csv --epochs 150

# Train one city
python scripts/train_city.py --city Islamabad --epochs 200

# AE-only (no TCN, for small datasets)
python scripts/train_city.py --city Gilgit --no-tcn --epochs 150
```

### Model Evaluation Metrics (v3.5.1 pipeline)

Each city's `training_metrics.json` records:
- AUC-ROC, Precision, Recall, F1, Brier Score
- ECE (Expected Calibration Error) from `calibration_audit.json`
- AE/TCN validation loss, training provenance, dataset date range

---

## Flutter App

The primary frontend is `frontend/citizen_flutter_app/` — a unified Flutter app serving both Citizens and Admins from a single binary.

### Role-Based Routing

| Role | Shell | Screens |
|---|---|---|
| `USER` | Citizen shell | Home · Forecast · Map · Learn · Settings · Profile |
| `ADMIN` | Admin shell | Dashboard · City HRI · Alerts · Map · More · Manual Prediction |

### Citizen Screens

| Screen | Live Data Source | Description |
|---|---|---|
| **Home** | `GET /api/v2/cities/{slug}/risk` | HRI score, severity ladder, live weather (38°C, humidity, pressure), risk trajectory chart, SHAP drivers, advice cards, family safety actions |
| **Forecast** | `GET /api/v2/cities/{slug}/forecast` | 7-bar precipitation chart, 7-day outlook rows from WeatherAPI |
| **Map** | OSM tiles + city coordinates | Real OpenStreetMap tiles, city marker, 3 shelter POIs |
| **Alerts** | `GET /api/v2/cities/{slug}/alerts` + WebSocket | Alert level ladder, live feed, WebSocket real-time prepend |
| **Learn** | Local (SharedPreferences) | Prep score ring, 7-item readiness checklist |
| **Settings** | `/api/v2/cities` + SharedPreferences | Theme picker (Light/Dark/Auto), city selector, notifications |
| **Profile** | `/auth/me` + SharedPreferences | Server fields (username, email, role) + locally-stored emergency info |

### Admin Screens

| Screen | Live Data Source | Description |
|---|---|---|
| **Dashboard** | `/health` + `/anomalies` + overview | KPIs (Elevated Cities, Models live, WS clients), system health bars, per-city model state, event feed |
| **City HRI** | `/api/v2/cities/overview` | All 6 cities sorted by HRI, band distribution bar |
| **Alerts** | `/api/v2/cities/{slug}/alerts` + WebSocket | Same as citizen with admin badge |
| **Map** | OSM + city coordinates | City pins labeled (ISL/KAR/LAH/PES/QUE/GIL) + risk legend |
| **More** | `/auth/me` + `/health` | Profile, system status, Refresh city registry (`POST /api/v2/cities/refresh`), Sign out |
| **Manual Prediction** | `POST /api/v2/cities/{slug}/predict` | Enter 8 weather parameters → get live ML prediction with HRI score, risk band, flood probability, SHAP drivers |

### Key Flutter Technical Features

- **Dio + auth interceptor** — auto-refresh on 401, concurrent refresh race-condition safe (uses `Completer<void>`)
- **SharedPreferences on web** — avoids `flutter_secure_storage` IndexedDB hang in browser
- **GoRouter redirect guard** — USER → citizen shell, ADMIN → admin shell, blocks cross-role access
- **FutureProvider (non-autoDispose)** — survives navigation transitions, prevents XHR abort on route animation
- **30s Dio connectTimeout** — accommodates WeatherAPI backend calls (8–12s latency)
- **Dark/Light/Auto theme** — `HGTheme` BuildContext extension (`context.hgText`, `context.hgCard`, etc.)
- **Admin "View as Citizen"** — violet preview banner with one-tap return to admin shell

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker Desktop | Latest | All backend services |
| Flutter SDK | 3.41+ | Build Flutter web app |
| OpenSSL | Any | Generate self-signed SSL cert |

### 1 — Clone the repository

```powershell
git clone https://github.com/itsmeprofessor/hydroguard_ai.git
cd hydroguard_ai
```

### 2 — Create `.env`

```env
JWT_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
POSTGRES_PASSWORD=your-db-password
REDIS_PASSWORD=your-redis-password
ADMIN_TOKEN=your-admin-token
WEATHERAPI_KEY=your-key-from-weatherapi.com
CORS_ORIGINS=http://localhost,http://localhost:80
```

### 3 — Generate SSL certs (one-time)

```powershell
mkdir nginx\certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout nginx\certs\privkey.pem `
  -out nginx\certs\fullchain.pem `
  -subj "/CN=localhost"
```

### 4 — Build the Flutter web app

```powershell
cd frontend\citizen_flutter_app
flutter pub get
flutter build web --dart-define=API_BASE='' --release
cd ..\..
```

### 5 — Start the full stack

```powershell
docker compose up --build
```

First run: ~3–4 minutes (Python image build). Subsequent runs: ~20 seconds.

### 6 — Open the app

| URL | What |
|---|---|
| `http://localhost` | Flutter web app |
| `http://localhost:8000/docs` | FastAPI Swagger UI |
| `http://localhost:8000/health` | Backend health JSON |

> **Important:** Always use `http://localhost` (not `https://`). Chrome's HSTS may redirect to HTTPS after a prior Docker HTTPS visit — clear it at `chrome://net-internals/#hsts` if stuck, or use an incognito window.

### Test Accounts

| Email | Password | Role |
|---|---|---|
| `test@hydroguard.pk` | `hydroguard123` | USER → Citizen shell |
| Create admin via: `docker exec -it hydroguard-db psql -U hydroguard -c "UPDATE users SET role='ADMIN' WHERE email='your@email.com';"` | | ADMIN → Admin shell |

---

## Configuration

### Required

| Variable | Description |
|---|---|
| `JWT_SECRET_KEY` | HS256 signing key, min 32 chars |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `REDIS_PASSWORD` | Redis auth password |
| `ADMIN_TOKEN` | Legacy `X-Admin-Token` header value |

### Weather API (Optional — has free fallback)

| Variable | Description |
|---|---|
| `WEATHERAPI_KEY` | WeatherAPI.com key (recommended — richest Pakistan data, 1M calls/month free) |
| `OPENWEATHER_API_KEY` | OpenWeatherMap alternative |
| `WEATHER_API_PROVIDER` | `auto` (default) · `weatherapi` · `openweathermap` · `open-meteo` |
| `WEATHER_CACHE_TTL_SECONDS` | `600` (10 min default) |

> `auto` mode picks the first available key. If no key is set, falls back to **Open-Meteo** (free, no key needed).

### Other Optional

| Variable | Default | Description |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `HYBRID_WARMUP` | `true` | Seed TCN buffers at startup from CSV |
| `HYBRID_WARMUP_ROWS` | `14` | Rows per city for warmup |
| `DATABASE_URL` | PostgreSQL | Override for local SQLite dev |
| `DEBUG` | `false` | Loosens secret checks (never use in prod) |

---

## API Reference

Interactive docs: `http://localhost:8000/docs`

### v2 City Endpoints (primary)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v2/cities` | none | List all cities + model availability |
| `GET` | `/api/v2/cities/overview` | none | Live risk snapshot — all cities |
| `GET` | `/api/v2/cities/{slug}/risk` | none | Full predict_v2 result for city |
| `GET` | `/api/v2/cities/{slug}/forecast` | none | 7-day WeatherAPI forecast |
| `GET` | `/api/v2/cities/{slug}/alerts` | none | Recent alert history (last 20) |
| `GET` | `/api/v2/cities/{slug}/status` | none | Model status + metrics |
| `POST` | `/api/v2/cities/{slug}/predict` | JWT | Manual prediction from weather params |
| `POST` | `/api/v2/cities/{slug}/train` | ADMIN | Trigger background model training |
| `POST` | `/api/v2/cities/refresh` | ADMIN | Rescan CSV + disk for new cities |

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create account (always role=USER) |
| `POST` | `/auth/login` | Returns access + refresh tokens |
| `POST` | `/auth/refresh` | Rotate refresh token (reuse detection) |
| `GET` | `/auth/me` | Current user profile |
| `POST` | `/auth/logout` | Invalidate refresh token |

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Model status, drift state, WS connections |
| `GET` | `/anomalies` | Anomaly records (filterable) |
| `GET` | `/admin/analytics` | Admin analytics |

### WebSockets

| Path | Auth | Description |
|---|---|---|
| `WS /ws/anomalies?token=<jwt>` | JWT | Push on every alert event |
| `WS /ws/risk-map?token=<jwt>` | JWT | Risk-map updates |
| `WS /ws/health` | Public | Health stream (no auth) |

### Prediction Response (v2)

```json
{
  "inference_id":         "uuid",
  "city":                 "Islamabad",
  "city_slug":            "islamabad",
  "inferred_at":          "2026-06-01T12:00:00Z",
  "event_probability":    0.042,
  "confidence_interval":  [0.021, 0.063],
  "uncertainty":          0.05,
  "risk_band":            "Low",
  "hri_score":            2,
  "is_alert":             false,
  "alert_tier":           {"level": 0, "label": "All Clear", "tier": "clear"},
  "alert_tier_label":     "NORMAL",
  "push_notification":    false,
  "component_scores":     {"ae_percentile": 0.12, "tcn_percentile": 0.09},
  "drivers":              [{"feature": "prcp", "shap": -1.26, "value": 0.0}],
  "weather_inputs":       {"prcp": 0.0, "humidity": 17, "pressure": 1005, "tavg": 38},
  "sequence_context":     {"buffer_size": 30, "required_size": 30, "tcn_active": true},
  "inference_mode":       "mc_dropout",
  "prediction_stability": "stable",
  "source":               "city_model"
}
```

---

## Live Weather

The backend uses **WeatherAPI.com** as the primary provider.

**Current key (in `.env`):** `WEATHERAPI_KEY=0166b218e6d54116893112936262805`
**Plan:** Free tier — 1 million API calls/month, 3-day forecast

Every city risk and forecast endpoint calls WeatherAPI live. Responses are cached for 10 minutes. The Flutter forecast screen may take 8–15 seconds on first load (WeatherAPI round-trip from the backend).

### Provider Auto-Selection

```
WEATHER_API_PROVIDER=auto
  ├── WEATHERAPI_KEY set?  → weatherapi.com  (recommended)
  ├── OPENWEATHER_API_KEY set? → openweathermap.org
  └── neither set → open-meteo.com (free, no key)
```

---

## Deployment

### Docker Compose (recommended)

```powershell
# Build Flutter first
cd frontend\citizen_flutter_app
flutter build web --dart-define=API_BASE='' --release
cd ..\..

# Start full stack
docker compose up --build -d

# Check health
docker compose ps
docker compose logs hydroguard-api --tail 50
```

### Day-to-Day Operations

```powershell
# Stop everything
docker compose down

# Stop + wipe all data
docker compose down -v

# Restart only API (after Python code change)
docker compose restart hydroguard-api

# Rebuild Flutter + redeploy (no Docker restart needed)
cd frontend\citizen_flutter_app
flutter build web --dart-define=API_BASE='' --release
# Then Ctrl+Shift+R in browser
```

### Resource Limits

| Container | Memory | CPU |
|---|---|---|
| `hydroguard-api` | 2 GB | 2 cores |
| `hydroguard-db` | 512 MB | 1 core |
| `hydroguard-redis` | 192 MB | 0.5 cores |
| `hydroguard-nginx` | 128 MB | 0.5 cores |

---

## Testing

```powershell
# Full backend test suite (135 tests)
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short

# Flutter static analysis
cd frontend\citizen_flutter_app
flutter analyze --no-fatal-infos

# Lint + type-check
ruff check backend/ --select E,W,F,I --ignore E501
mypy backend/app/core/config.py backend/app/schemas/__init__.py --ignore-missing-imports
```

### Test Suite Status

| Suite | Tests | Status |
|---|---|---|
| Backend API | 135 total | ✅ 135 passed, 0 failed |
| Flutter analysis | — | ✅ 0 errors, 0 warnings |

### CI Pipeline (`.github/workflows/ci.yml`)

1. **Lint** — ruff + mypy
2. **Test** — pytest with PostgreSQL service container
3. **Docker build** — multi-stage build + `curl /health` smoke test

---

## Security

| Control | Implementation |
|---|---|
| **JWT HS256** | 30-min access + 7-day refresh with rotation and reuse detection |
| **Reuse detection** | Presenting a recycled refresh token invalidates ALL sessions |
| **Mandatory secrets** | App refuses to start in production without `JWT_SECRET_KEY` |
| **Rate limiting** | Nginx: 5/min auth, 60/min predict. SlowAPI app-level shared limiter |
| **HTTPS** | TLS 1.2/1.3, HSTS max-age=1yr, self-signed for dev |
| **Security headers** | X-Frame-Options DENY, nosniff, XSS-Protection, CSP, Referrer-Policy |
| **WebSocket auth** | JWT via `?token=` query param (browsers can't send custom headers on WS handshake) |
| **CORS** | Wildcard only in dev; credential-bearing requests require explicit origins |
| **Roles** | USER · ADMIN. Public registration always creates USER. |

---

## Project Structure

```
hydroguard_ai/
├── backend/
│   ├── app/
│   │   ├── api/          FastAPI routes
│   │   ├── auth/         JWT + user model
│   │   ├── core/         Config, security, deps
│   │   ├── db/           SQLAlchemy models + repositories
│   │   ├── ml/           Autoencoder, TCN, FusionModel, preprocessing
│   │   ├── realtime/     WebSocket connection manager + broadcaster
│   │   ├── runtime/      System runtime, health collector, bootstrap
│   │   └── services/     CityModelService, AlertTierClassifier, polling
│   ├── data/             pakistan_weather_2000_2024.csv
│   └── saved_models/     city_models/<slug>/ (trained artifacts)
├── frontend/
│   └── citizen_flutter_app/   Primary Flutter app
│       └── lib/
│           ├── core/          Theme, router, network, storage
│           ├── features/      admin/ + citizen/ screens
│           ├── models/        Data models
│           ├── repositories/  API repositories
│           └── shared/        Providers, widgets
├── nginx/                nginx.conf + SSL certs
├── scripts/              train_city.py, evaluate.py
├── tests/                pytest test suite (135 tests)
├── docker-compose.yml
├── Dockerfile
├── SETUP.md              Full deployment guide
└── .env                  Secrets (never commit)
```

---

## Credits

**Author:** Zain Mohyuddin — FYP · System Architect & ML Developer
📧 `zain.mohyuddin09@gmail.com`

**Dataset:** Pakistan weather 2000–2024, daily observations, 6 cities

**ML Stack:** TensorFlow/Keras · LightGBM · scikit-learn

**Frontend:** Flutter 3.41 · Riverpod · GoRouter · Dio · flutter_map

**Infrastructure:** FastAPI · PostgreSQL · Redis · Nginx · Docker

**Live Weather:** WeatherAPI.com

---

*HydroGuard-AI — Early warning saves lives.*
