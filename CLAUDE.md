# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Architecture version:** v3.2.0 (`app/main.py`). The sections below describe the
> **current codebase** — not v3.1. Key changes since v3.1: BahdanauAttention → TCN;
> simple score blending → LightGBM FusionModel + IsotonicCalibrator; fixed 10 cities →
> dynamic city discovery; new v2 API at `/api/v2/*`; WeatherAPI live provider added.

## Project Overview

HydroGuard-AI v3.2 is a production-grade flood / weather-anomaly detection system for Pakistan. Cities are **dynamically discovered** from the dataset CSV and the saved-models directory (no fixed list). At least 6 cities have curated metadata: Islamabad, Rawalpindi, Lahore, Karachi, Peshawar, Quetta.

System surface area:

- **FastAPI backend** (`backend/`) — **city-specific hybrid ML** (Autoencoder + **TCN** + **LightGBM FusionModel** + **IsotonicCalibrator**, one model-set per city), JWT auth with refresh-token rotation, WebSocket real-time push, SQLAlchemy persistence, slowapi rate limits (applied on auth and city predict). Falls back to a rule-based heuristic when a city's model has not been trained yet.
- **Flutter App** (`frontend/citizen_flutter_app/`) — unified app for both Citizens and Admins. Role-based routing via GoRouter: `USER` role → Citizen shell (6 screens: Home / Forecast / Map / Alerts / Learn / Settings); `ADMIN` role → Admin shell (5 screens: Dashboard / Monitoring / Analytics / Cities / Settings). Stack: Riverpod + Dio + GoRouter. Builds to web (`flutter build web`) served by nginx; also runs as native mobile/desktop.

Backed in production by `docker-compose` (Postgres 16 + Redis 7 + API + nginx **with HTTPS**).

## Commands

### Backend

```bash
# Install + activate venv
pip install -r backend/requirements.txt
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # *nix

# Run API server (from repo root)
python backend/run_server.py
python backend/run_server.py --reload --port 8080
python backend/run_server.py --workers 4   # warns if >1 with SQLite

# Tests
pytest tests/ -v --tb=short
pytest tests/test_api.py::TestSystem::test_health -v

# Lint + type-check (matches CI)
ruff check backend/ --select E,W,F,I --ignore E501
mypy backend/app/core/config.py backend/app/core/security.py backend/app/schemas/__init__.py backend/app/db/database.py --ignore-missing-imports

# Smoke test against running server
./backend/smoke_test.sh http://127.0.0.1:8000

# Legacy global model training (kept for backward compat; not used in v3.2 inference)
python scripts/train.py --data backend/data/pakistan_weather_2000_2024.csv --use-lstm --epochs 200 --visualize

# v3.2 — city-specific hybrid model training (Autoencoder + TCN + FusionModel)
# Weak labels generated automatically from 95th-percentile heuristics if not present in CSV.
# Requires AUC >= 0.70 on calibration set to save (use --force to override gate).
python scripts/train_city.py --all --data backend/data/pakistan_weather_2000_2024.csv --epochs 150
python scripts/train_city.py --city Islamabad --epochs 200
python scripts/train_city.py --city Karachi  --no-tcn   # AE-only fallback

# Docker (full stack: postgres + redis + api + nginx on :80)
docker compose up --build
```

### Flutter App (primary frontend)

```bash
# Dev — run in Chrome against local backend
cd frontend/citizen_flutter_app
flutter run -d chrome --dart-define=API_BASE=http://localhost:8000

# Dev — Android emulator
flutter run -d emulator-5554 --dart-define=API_BASE=http://10.0.2.2:8000

# Dev — physical device (replace with your LAN IP)
flutter run --dart-define=API_BASE=http://192.168.x.x:8000

# Build web (output → build/web/, served by nginx in Docker)
flutter build web --dart-define=API_BASE=''

# Run tests
flutter test
```

---

## Architecture

### Backend (`backend/app/`)

**Entry point:** `backend/run_server.py` (CLI: `--host`, `--port/-p`, `--reload/-r`, `--workers/-w`) → uvicorn → `app/main.py::create_app()`.

**App startup** — two functions run at boot: `lifespan()` (async context manager, startup/shutdown hooks) and `create_app()` (registers middleware, routes, and static mounts synchronously before the server accepts requests).

**`lifespan()` startup sequence** (`app/main.py`):
1. `validate_startup_secrets()` — exits in production if `JWT_SECRET_KEY` is missing/placeholder.
2. `init_db()` — creates tables; **must import `User` from `app.auth.models`** before `Base.metadata.create_all()`.
3. `init_redis()` — Redis connection pool; non-fatal if Redis is unavailable.
4. `init_weather_provider()` — WeatherAPI HTTP client; non-fatal.
5. `RollingWindowBuffer` (4.5), `EventBus` (4.6), `DriftMonitor` (4.7), `CalibrationService` (4.8) — supporting services initialised in sequence; each non-fatal.
6. `city_model_service.model_status()` — logs how many cities have trained models vs. untrained.
7. `warm_up_tcn_buffers()` — seeds each city's TCN rolling window (seq_len=30) from the most-recent rows of the master CSV; non-fatal.
8. `RuntimeHealthCollector.start()` — background health tick; non-fatal. Stopped on shutdown.

**`create_app()` wiring** (`app/main.py`):
- `_SecurityHeadersMiddleware` — injects `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, and HTTPS-only `Strict-Transport-Security` on every response.
- Rate limiter state + `RateLimitExceeded` handler attached to `app.state`.
- CORS: if `CORS_ORIGINS` contains `*`, no credentials; otherwise specific origins **with** credentials.
- Static mount at `/static/*` from `frontend/web_dashboard/admin_dashboard/` (legacy admin reference); `/frontend` and `/dashboard` GET routes serve its `index.html`.
- HTTP + general exception handlers return `{"error": detail, "status_code": code}`.
- Routers in order: `auth_router` → `api_router` → `analytics_aliases.router` → `realtime_router` (`/ws/*`) → `city_router`. Conditional: `v2_router` and `weather_router` appended after `city_router` if importable.
- Legacy React citizen app mounted at `/citizen` (static, `html=True`) if `frontend/citizen_app/` exists.
- Flutter built web mounted at `/flutter` (static, `html=True`) if `frontend/citizen_flutter_app/build/web/` exists. In Docker, nginx also serves the same build at the root (`/`).

**Request flow:** Router → `Depends(get_current_user|require_role|require_admin)` → service layer (`city_model_service.predict_v2()` for city predictions; `anomaly_service` was decommissioned in v3.2) → Repository (DB) → `broadcast_service.emit_*` → ConnectionManager → all sockets in channel.

#### Endpoints (full inventory)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/` | none | Banner + endpoint map |
| GET | `/health` | none | Includes `model_version`, `ws_connections` per channel |
| GET | `/model/info` | none | input_dim, threshold, features, training metadata |
| GET | `/model/versions` | none | `{current, archived[]}` from `manifest.json` |
| GET | `/frontend`, `/dashboard` | none | Serves `index.html` |
| POST | `/auth/register` | none | RegisterRequest → TokenResponse (201) |
| POST | `/auth/login` | none | LoginRequest → TokenResponse |
| POST | `/auth/refresh` | none | Refresh-token rotation; reuse → invalidates all sessions |
| GET | `/auth/me` | JWT | Current user profile |
| POST | `/auth/logout` | JWT | Clears `refresh_token_hash` (204) |
| POST | `/predict` | JWT | Rate limit **60/min**; saves record; broadcasts |
| POST | `/predict/batch` | JWT | Rate limit **20/min** |
| GET | `/anomalies` | none | Filters: skip, limit≤100, city, risk_level, start/end_date, anomalies_only |
| GET | `/anomalies/statistics` | none | DB stats; falls back to CSV if DB empty |
| GET | `/anomalies/{id}` | none | Single record |
| POST | `/train` | **Admin** | Accepts JWT(role=ADMIN) **or** legacy `X-Admin-Token` header |
| GET | `/risk-map` | none | Predicts HRI for all 10 cities |
| GET | `/admin/analytics` | **Admin** | Top cities, weekly anomaly count, etc. |
| GET | `/database/statistics` | none | Counts (alias used by dashboard) |
| GET | `/analytics` | none | `alerts_by_risk_level`, `top_cities_by_frequency`, week count |
| WS | `/ws/anomalies?token=` | JWT (query param) | Broadcasts after every prediction |
| WS | `/ws/risk-map?token=` | JWT (query param) | Risk-map updates |
| WS | `/ws/health` | **none** | Public health stream |
| GET | `/cities` | none | List all 10 cities + per-city model availability |
| GET | `/cities/overview` | none | Risk snapshot across all cities (one shot) |
| GET | `/cities/{city}/risk` | none | Current risk for *city* (uses live or default weather) |
| POST | `/cities/{city}/predict` | none | Submit weather data → standardised prediction |
| GET | `/cities/{city}/forecast` | none | 7-day outlook for *city* |
| GET | `/cities/{city}/alerts` | none | Recent anomaly alerts (last *n*, max 20) |
| GET | `/cities/{city}/status` | none | Model status, input_dim, ae_threshold |
| POST | `/cities/{city}/train` | **Admin** | Trigger city-specific training (background) |
| POST | `/cities/refresh` | **Admin** | Rescan CSV + disk for new cities; rebuilds `CITY_REGISTRY` |

#### Authentication (`app/core/security.py`, `app/auth/`, `app/api/deps.py`)

- **JWT (HS256)**: access token (`type="access"`, default 30 min, claims: `sub` user_id, `role`, `username`); refresh token (`type="refresh"`, default 7 days, sub only).
- **Password hashing**: bcrypt; passwords are truncated to 72 bytes before hashing.
- **Refresh-token storage**: only the SHA-256 hash is persisted in `User.refresh_token_hash`. Reuse detection: if a presented refresh token's hash does not match the stored one, all sessions are invalidated.
- **Roles enum**: `ADMIN` (full), `ANALYST` (analytics endpoints), `USER` (predict only).
- **`require_admin`**: accepts EITHER a JWT bearer with `role=="ADMIN"` OR a legacy `X-Admin-Token` header matching `ADMIN_TOKEN`. Keep both — legacy clients still rely on the header.
- **`require_role(*roles)`**: factory returning a `Depends()` that 403s on mismatch.

#### City-specific hybrid models (v3.2+) (`app/ml/models/`, `app/services/city_model_service.py`)

**Goal**: per-city models capture each city's unique seasonal patterns, monsoon profiles, and topographic vulnerabilities. `anomaly_service` was decommissioned in v3.2; the fallback for untrained cities is a rule-based heuristic in `city_model_service._build_degraded_response()`.

**Architecture (one model per city)** in `app/ml/models/city_hybrid.py`:
- **Autoencoder**: Dense `[64, 32, 16]` → latent **8** → mirrored decoder → `linear`. Dropout 0.20. Physics-weighted MSE loss (prcp 3×, pressure 2.5×, humidity 2×). Trained on fair-weather rows only. Score: `ECDFScaler(ae_error) → ae_percentile ∈ [0, 1]`.
- **TCN**: `CausalTCN(filters=128, kernel=3, dilations=[1,2,4,8,16,32], seq_len=30)`. Receptive field = 127 observations (~4 months). Trained as next-step reconstructor on full training set. Score: `ECDFScaler(tcn_error) → tcn_percentile ∈ [0, 1]`.
- **NO LSTM. NO BahdanauAttention. NO BiTCN.** Strictly causal.
- **Fusion**: `ae_percentile` + `tcn_percentile` + derived features → `FusionModel` (LightGBM) → raw `P(event)` → `IsotonicCalibrator` → `event_probability`.
- **Uncertainty**: Monte Carlo Dropout — N stochastic forward passes at inference. Outputs `epistemic_uncertainty` (weighted AE + TCN variance blend), `model_entropy`, `prediction_stability` (`stable|warming_up|degraded`).
- **OOD detection**: `OODDetector` (`ood_detector.pkl`) uses Mahalanobis distance. OOD is **non-blocking** — sets elevated uncertainty but does not stop inference.
- **Standardised output dict** (v3.2+):
  ```
  {
    inference_id, city, city_slug, inferred_at, model_version, source,
    event_probability,   # IsotonicCalibrator output ∈ [0,1]
    confidence_interval, # [lo, hi]
    uncertainty,         # epistemic uncertainty scalar
    model_entropy,       # None when MC disabled
    risk_band,           # "Low" | "Moderate" | "High" | "Severe"
    hri_score,           # 0–100 int
    is_alert,            # bool
    alert_tier,          # 1–5 (severity tier)
    alert_threshold,     # configured threshold used for this inference
    component_scores:    { ae_percentile, tcn_percentile, p_event_raw, ae_variance, tcn_variance },
    drivers,             # SHAP-derived top contributors
    weather_inputs,      # raw inputs echoed back
    climatology_context, # prcp_climo_pct, pressure_climo_z, etc.
    coastal_features,    # Karachi only; null for other cities
    sequence_context:    { buffer_size, required_size, tcn_active },
    inference_mode,      # "mc_dropout" | "fallback_deterministic"
    epistemic_uncertainty, model_uncertainty_score, prediction_stability,
    mc_samples_requested, mc_samples_completed, degraded_reason
  }
  ```

**`CityModelService` singleton** in `app/services/city_model_service.py`:
- `CITY_METADATA` / `CITY_REGISTRY` — canonical slug → name / province / population / lat-lon / vulnerability. Populated by `refresh_registry()` on startup; rescanned on `POST /cities/refresh`.
- Lazy-loads each city's model set on first access; per-city `RLock` keeps loading thread-safe.
- Per-city TCN rolling buffer (`_CityBuffer`, length=`TCN_SEQ_LEN`=30) — TCN branch activates only after the buffer fills; before that, AE branch only.
- `predict_v2(city_slug, raw_weather)` is the primary async entry point. Falls back to `_build_degraded_response()` (rule-based heuristic, `source="heuristic"`) when no model is loaded.
- In-memory **alert log** per city (last 20 alerts) via `get_recent_alerts()`.

**Saved-model layout**:
```
backend/saved_models/city_models/
└── <slug>/
    ├── autoencoder.keras        # Keras 3 format (AE branch)
    ├── tcn_reconstructor.keras  # Keras 3 format (TCN branch)
    ├── ae_ecdf.pkl              # ECDFScaler fitted on AE reconstruction errors
    ├── tcn_ecdf.pkl             # ECDFScaler fitted on TCN reconstruction errors
    ├── lgbm_model.pkl           # LightGBM FusionModel (binary P(event))
    ├── calibrator.pkl           # IsotonicCalibrator
    ├── preprocessor_v2.joblib   # WeatherDataPreprocessorV2 fitted on city's data
    ├── ood_detector.pkl         # OODDetector (Mahalanobis; non-blocking)
    ├── ae_calibration.npy       # Legacy v3.1 compat — AE [mean, std, p99] from training errors
    ├── cal_data.npz             # Held-out calibration arrays (for audit scripts)
    ├── calibration_audit.json   # Per-city calibration audit results (ECE, reliability)
    ├── leakage_audit.json       # Feature leakage audit results from training pipeline
    ├── operational_metrics.json # Runtime operational metrics snapshot
    └── training_metrics.json    # Training provenance + evaluation metrics
```

**Training** (`scripts/train_city.py`): args `--city <name>` or `--all`; `--data`, `--epochs`, `--batch-size`, `--no-tcn`, `--seed`, `--min-records`, `--force`. Per-city training pipeline:
1. Filter master CSV to one city (`city` column). For Karachi: compute 9 coastal features.
2. Fit `WeatherDataPreprocessorV2` on the training split (no leakage).
3. 4-way split (train / cal / test / implicit holdout). Train AE on fair-weather rows; fit `ECDFScaler` on AE errors.
4. If ≥30 sequences, train TCN reconstructor; fit `ECDFScaler` on TCN errors.
5. Train `FusionModel` (LightGBM) on cal split branch outputs. Fit `IsotonicCalibrator`.
6. Train `OODDetector` on training features (Mahalanobis covariance).
7. Save all artifacts → `city_model_service.register_model(slug, ...)` hot-swap (only if `input_dim` unchanged; dimension change requires container restart).

#### ML & preprocessing (`app/ml/`, `app/ml/preprocessing_v2.py`)

- **`WeatherDataPreprocessorV2`** (`app/ml/preprocessing_v2.py`): 28 base numerical features (`NUMERICAL_V2`) + 9 Karachi-specific coastal features (auto-excluded for other cities via `num_present` filter) + 4 temporal + 2 OHE categorical. Fit on training split only; `input_dim` property returns the actual fitted dimension. `utils/preprocessing.py` (v1, `WeatherDataPreprocessor`) is still used by legacy global-model scripts (`scripts/train.py`, `scripts/evaluate.py`) — NOT used by v3.2 inference.
- **Drift detection** (`app/ml/drift/detector.py`): PSI on `[prcp, humidity, pressure, cloud_cover]`. WARN at 0.10, CRIT at 0.20. Surfaced via `/health`.

#### Repositories (`app/db/repositories/`)

All DB access goes through these — never query in routers.

- **`AnomalyRepository`**: `create`, `get_by_id`, `get_all(skip, limit, city, risk_level, start_date, end_date, is_anomaly_only)`, `list`, `get_count`, `get_statistics`.
- **`TrainingRepository`**: `create(metadata)`, `get_latest`.
- **`UserRepository`**: `get_by_id`, `get_by_email`, `get_by_username`, `create`, `update_refresh_token`, `update_last_login`. **Not** re-exported from `app/db/__init__.py` to avoid circular import (`app.db` ← `user_repo` ← `app.auth.models`). Always import directly: `from app.db.repositories.user_repo import UserRepository`.

#### Database (`app/db/database.py`)

SQLAlchemy ORM, `declarative_base`. SQLite gets `check_same_thread=False`; PostgreSQL otherwise. Tables:

- **`AnomalyRecord`**: weather fields, `anomaly_score`, `threshold`, `is_anomaly`, `risk_level` (indexed), `hri_score`/`hri_label`, cloudburst trio, `feature_contributions` (JSON), `detailed_explanation` (JSON), timestamps.
- **`TrainingRecord`**: train/val sample counts, AE/LSTM losses + epoch counts, anomaly_percentage, status, error_message.
- **`User`** (in `app/auth/models.py`): email/username unique, `hashed_pw`, `role`, `is_active`, `refresh_token_hash`, `last_login`.

#### WebSockets (`app/realtime/`)

- **`ConnectionManager`** singleton: per-channel `set[WebSocket]` for `anomalies`, `risk-map`, `health`. Broadcasts JSON `{channel, data, ts}`; dead sockets are pruned.
- **JWT in query param**: `ws://host/ws/anomalies?token=<jwt>`. Browsers cannot send custom Authorization headers on WebSocket handshakes — query param is intentional. Token is validated as `type="access"` (same as REST).
- **`/ws/health` is public** (no token) — used for dashboard status indicators.
- **Broadcast trigger** (`broadcast_service.emit_anomaly`): fires on `is_anomaly == True` OR `hri_score ≥ 40` (so elevated risk shows up even without a hard anomaly).
- **Multi-worker note**: with multiple uvicorn workers, each worker holds its own ConnectionManager. Redis (already in compose) is the planned bridge if cross-worker fan-out becomes necessary; today's deployment is single-worker.

#### Schemas (`app/schemas/__init__.py`)

Enums: `RiskLevel` (LOW/MEDIUM/HIGH/CRITICAL), `HRILabel` (Low/Guarded/Elevated/Severe).

Key request models: `WeatherDataInput` (only `city` is required; everything else is optional and gets imputed), `BatchWeatherInput`, `TrainingRequest`. Response models include `PredictionResponse` (with `consensus_score`, `feature_contributions`, `detailed_explanation`), `AnomalyListResponse`, `RiskMapResponse`, `HealthResponse` (with `ws_connections`).

#### Config (`app/core/config.py`)

Selected env vars (full list in `.env.example`):

- **Server**: `API_HOST`, `API_PORT`, `DEBUG`, `CORS_ORIGINS` (comma-separated; `*` allowed but disables credentials).
- **JWT**: `JWT_SECRET_KEY` (warns + uses placeholder if unset — do not deploy without it), `JWT_ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.
- **Legacy**: `ADMIN_TOKEN` (still honored by `require_admin`).
- **DB**: `DATABASE_URL` (`sqlite:///backend/weather_anomalies.db` default; `postgresql://...` for prod).
- **Hybrid warm-up**: `HYBRID_WARMUP` (bool), `HYBRID_WARMUP_ROWS_PER_CITY` (default 14), `HYBRID_WARMUP_CSV`.
- **Hard-coded model knobs**: `THRESHOLD_K=2.5`, `SEASONAL_THRESHOLD_MULTIPLIER`, `HRI_WEIGHTS`, `REGIONAL_VULNERABILITY`, `CloudburstConfig` thresholds and `MONSOON_MONTHS=[6,7,8,9]`, `FLASH_FLOOD_PRONE_CITIES`.

Logging: rotating file at `logs/hydroguard.log` (10 MB × 5) + console.

#### Model artifacts

- `backend/saved_models/manifest.json` — `version`, `trained_at`, `ae_threshold`, `anomaly_rate`, `has_lstm`.
- `backend/saved_models/autoencoder_model/` — TF SavedModel.
- `backend/saved_models/lstm_model/` — TF SavedModel (optional).
- `backend/saved_models/preprocessor.joblib`.
- `backend/saved_models/archive/v{n}/` — previous versions (auto-rotated).
- `backend/saved_models/visualizations/` — training plots (PNG).

---

### Flutter App (`frontend/citizen_flutter_app/`)

Single unified Flutter app — both the public Citizen interface and the Admin Dashboard live here, separated by role-based routing.

**Stack:** Flutter 3.x · Riverpod (state) · Dio (HTTP) · GoRouter (navigation) · flutter_secure_storage (tokens) · fl_chart (charts) · flutter_map + OpenStreetMap (map screen)

**Auth flow (`lib/features/auth/`):**
- `SplashScreen` — on start calls `/auth/me`; routes to `/citizen/home` (USER) or `/admin/dashboard` (ADMIN), or `/login` if unauthenticated.
- `LoginScreen`, `SignupScreen`, `ForgotPasswordScreen` — call backend `/auth/*` endpoints.

**Role-based routing (`lib/core/router/app_router.dart`):**
- GoRouter `redirect` guard: redirects `/splash` → role-appropriate home; blocks `/admin/*` for non-admin users.
- Citizen shell (`/citizen/*`): Home, Forecast, Map, Alerts, Learn, Settings.
- Admin shell (`/admin/*`): Dashboard, Monitoring, Analytics, Cities, Settings.

**Data layer (`lib/repositories/`):**
- `AuthRepository` — login/register/logout/refresh; stores access + refresh tokens in flutter_secure_storage.
- `CityRepository` — city list/overview/alerts/status via v1 (`/cities/*`); forecast tries v2 (`/api/v2/cities/{slug}/forecast`) first then falls back to v1; risk has explicit `getCityRiskV2()` alongside the default v1 call.
- `AdminRepository` — anomalies, training trigger, analytics via v2 + admin endpoints.

**State management (`lib/shared/providers/app_provider.dart`):** Riverpod providers for auth state, selected city, theme prefs (dark mode, big text).

**API base URL:** configured via `--dart-define=API_BASE=...`. Web builds use empty string (same-origin via nginx proxy); mobile/desktop dev use `http://localhost:8000` (or LAN IP for physical device; `http://10.0.2.2:8000` for Android emulator).

**Deployment:** `flutter build web` → `build/web/` mounted into nginx container at `/usr/share/nginx/html`. All non-API paths fall through to Flutter SPA (`try_files $uri $uri/ /index.html`).

**Legacy frontends** (still in repo, not primary): `frontend/citizen_app/` (React, served by FastAPI at `/citizen`) and `frontend/web_dashboard/admin_dashboard/` (JSX/Babel, legacy admin reference).

---

## Infrastructure

### `docker-compose.yml`

- **`postgres:16-alpine`** (`hydroguard-db`) — db `hydroguard`, user `hydroguard`, vol `postgres_data`, healthcheck `pg_isready`.
- **`redis:7-alpine`** (`hydroguard-redis`) — password from env, vol `redis_data`, healthcheck `redis-cli ping`.
- **`hydroguard-api`** — built from root `Dockerfile` (multi-stage `python:3.11-slim`); env: `DATABASE_URL=postgresql://...`, `REDIS_URL`, JWT vars, `HYBRID_WARMUP=true`. Mounts `./backend/data`, `./backend/saved_models`, `./backend/logs`. Healthcheck `curl -sf /health`. Depends on db + redis.
- **`nginx:alpine`** — mounts `./nginx/nginx.conf` (ro), `./nginx/certs` (ro), and `./frontend/citizen_flutter_app/build/web` → `/usr/share/nginx/html` (compiled Flutter web app). Ports `80:80`, `443:443`.

### `nginx/nginx.conf`

Upstream `hydroguard_api` → `hydroguard-api:8000`. WebSocket upgrade at `/ws/*` (`Upgrade`/`Connection` headers, `proxy_read_timeout`/`proxy_send_timeout` 86400 s). Regex match for API paths (`/anomalies`, `/analytics`, `/risk-map`, `/train`, `/health`, `/auth`, `/model`, `/docs`, `/redoc`, `/openapi.json`, `/cities`, `/weather`, `/drift`, `/database`, `/api`). All other paths → Flutter SPA with `try_files $uri $uri/ /index.html`.

**Rate limits (per source IP):**
- `auth/(login|register)`: 5 req/min, burst=3 — brute-force protection
- `api/v2/cities/*/predict` + `/predict`: 60 req/min, burst=10
- All other API routes: 200 req/min, burst=50

**Frontend served:** `citizen_flutter_app/build/web` (compiled Flutter). The React `citizen_app` is served by FastAPI at `/citizen`, not by nginx.

**HTTPS:** Self-signed certs for local dev — `openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem -subj "/CN=localhost"`. Production: use Certbot. Certs mounted `:ro`; to renew, update host files and `docker compose restart nginx`.

### `Dockerfile` (root)

Stage 1 builder installs `gcc`/`libffi-dev`, runs `pip install --prefix=/install -r backend/requirements.txt`. Stage 2 runtime is `python:3.11-slim` + `curl` (HEALTHCHECK), copies installed packages, drops to non-root `hydroguard` user, `EXPOSE 8000`, `CMD ["python", "backend/run_server.py", "--host", "0.0.0.0", "--port", "8000"]`.

### `.env.example`

Mandatory: `JWT_SECRET_KEY` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`). Sensitive: `ADMIN_TOKEN`, `REDIS_PASSWORD`. Tunable: `ACCESS_TOKEN_EXPIRE_MINUTES=30`, `REFRESH_TOKEN_EXPIRE_DAYS=7`, `CORS_ORIGINS`, `DATABASE_URL`, `HYBRID_WARMUP*`.

### CI (`.github/workflows/ci.yml`)

Push/PR to `main` or `develop`. Sequential jobs: **lint** (ruff + mypy non-blocking) → **test** (pytest with PostgreSQL service) → **docker build** (BuildKit cache + `curl /health` smoke test) → **deploy** (placeholder, both Docker Hub push and SSH deploy commented).

### `pyproject.toml`

`testpaths=["tests"]`, `asyncio_mode = "auto"` (every pytest-asyncio test is auto-marked), `log_cli=true`.

### `scripts/`

- `train.py` — args: `--data`, `--epochs`, `--batch-size`, `--use-lstm`, `--visualize`, `--output-dir`, `--seed`. Saves to `backend/saved_models/`, updates manifest.
- `evaluate.py` — metrics + confusion matrix on a held-out set.
- `tune_threshold.py` — sweep `THRESHOLD_K`.

### Tests (`tests/test_api.py`)

Classes: `TestSystem` (root, health, model info, database statistics), `TestAnomalies` (list, filters, single 404), `TestPrediction` (422 on missing/invalid, 200/400 for predict, batch), `TestAdmin` (401 paths), `TestRiskMap`. Sample payloads: `SAMPLE_NORMAL` (Islamabad 2024-06-15 mild) and `SAMPLE_EXTREME` (Islamabad 2024-07-25 monsoon heavy).

---

## Key Constraints & Gotchas

- **ML architecture is fixed**: Autoencoder + **TCN** + **LightGBM FusionModel** + **IsotonicCalibrator** per-city. No BiTCN, no LSTM, no BahdanauAttention — strictly causal. MC Dropout provides epistemic uncertainty. `anomaly_service` is decommissioned; the fallback for untrained cities is the rule-based heuristic in `city_model_service`.
- **City-specific models are required**: each city trains its own AE+TCN+FusionModel set (`scripts/train_city.py`). `CityModelService` lazy-loads them; missing models route through the rule-based heuristic. Don't replace the per-city design with a single global model.
- **Standardised output dict**: v2 predictions return `{ inference_id, event_probability, confidence_interval, uncertainty, risk_band, hri_score, is_alert, alert_tier, component_scores, drivers, sequence_context, inference_mode, epistemic_uncertainty, prediction_stability, degraded_reason }`. The v1 `/cities/{city}/forecast` translates `risk_band` to scenario `safe | warn | crit` via `_risk_to_scenario`.
- **Flutter app is the primary frontend**: `frontend/citizen_flutter_app/` is the only actively maintained frontend. The original Flutter project (`frontend/weather_anomaly_app/`) and the legacy React apps (`citizen_app/`, `web_dashboard/`) are deprecated — do not extend them. All new client work goes into `citizen_flutter_app`.
- **JWT secret must be set** in production; the placeholder logs a warning but the app still runs (tokens are guessable).
- **WebSocket auth uses `?token=` query param** intentionally — browsers cannot send custom headers on the WS handshake.
- **`AnomalyRepository` canonical location**: `app/db/repositories/anomaly_repo.py`. The old broken copy embedded in `anomaly_service.py` was deleted in v3.0 — do not resurrect it.
- **`UserRepository` is NOT re-exported** from `app/db/__init__.py` — circular import via `app.auth.models`. Always `from app.db.repositories.user_repo import UserRepository`.
- **`init_db()` must import `User`** before `Base.metadata.create_all()` or the `users` table will silently not be created.
- **`asyncio_mode = "auto"`** — do not add `@pytest.mark.asyncio` decorators; they are unnecessary and noisy.
- **SQLite ↔ PostgreSQL**: multi-worker prod requires PostgreSQL; SQLite has write races at `--workers > 1`. `run_server.py` warns when this combo is used.
- **`require_admin` accepts both** JWT `role=ADMIN` and legacy `X-Admin-Token` header — keep both paths working.
- **Flutter app uses Dio for HTTP, not browser fetch**: `ApiClient` (Dio-based) in `lib/core/network/api_client.dart` handles auth header injection, token refresh on 401, and `--dart-define=API_BASE` resolution. Don't add raw `http` package calls — go through `ApiClient` or the repository layer.
- **WebSocket fan-out is per-worker**: today's deployment is single-worker. If you scale uvicorn, you'll need a Redis pub/sub bridge between `ConnectionManager` instances.
- **City model loading is thread-safe via per-slug RLock** — concurrent first-touch predictions race on the same lock and only one filesystem load happens per city.
- **CORS with `*`**: when `CORS_ORIGINS` contains `*`, FastAPI cannot allow credentials. The dashboard's auth flow requires specific origins (with credentials) in production.
- **TCN is custom** — `app/ml/models/tcn.py` implements `CausalTCN`. When loading TCN models, `CityHybridModel.load()` handles all custom object registration automatically.
