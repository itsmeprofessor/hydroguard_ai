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
- **Public Citizen Web App** (`frontend/citizen_app/`) — minimal, friendly. Five screens (Home / Forecast / Alerts / Learn / Settings), live polling every 5 minutes, light/dark mode, English + Urdu/Punjabi/Pashto/Sindhi/Balochi locale chooser. Connects to the backend via `/api/v2/*` endpoints with `/cities/*` fallback.
- **Admin Web Dashboard** (`frontend/web_dashboard/admin_dashboard/`) — JSX served via Babel-Standalone (no build step), JWT login, Pakistan SVG risk map, real-time WebSocket feed, **per-city model status / training trigger**.

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

### Public Citizen Web App

No build step. Served from FastAPI `/citizen` (mounted in `app/main.py`) or directly from `frontend/citizen_app/` via any static server. Boots React 18 + Babel from CDN; load order: `api.js` → `citizen-icons.jsx` → `citizen-screens.jsx` → `citizen-settings.jsx` → `citizen-app.jsx`.

```bash
# Local dev
cd frontend/citizen_app
python -m http.server 5500   # then open http://localhost:5500/index.html

# Override API base URL for the citizen app
# (set window.__HYDROGUARD_API__ before loading api.js, or fall back to same origin)
```

### Admin Web Dashboard

No build step. Serve `frontend/web_dashboard/admin_dashboard/` statically (nginx in compose, or `python -m http.server` for local). The page boots React 18 + Babel from CDN and sequentially loads JSX files in the order set by `index.html`.

---

## Architecture

### Backend (`backend/app/`)

**Entry point:** `backend/run_server.py` (CLI: `--host`, `--port/-p`, `--reload/-r`, `--workers/-w`) → uvicorn → `app/main.py::create_app()`.

**App lifespan** (`app/main.py`):
1. `init_db()` — creates tables; **must import `User` from `app.auth.models`** before `Base.metadata.create_all()`.
2. Verifies `anomaly_service.get_model_info()` and logs model type/version.
3. Mounts routers in this order: `auth_router` → `api_router` (system/training/prediction/anomalies/risk_analytics) → `analytics_aliases.router` → `realtime_router` (`/ws/*`).
4. CORS: if `CORS_ORIGINS` contains `*`, no credentials; otherwise specific origins **with** credentials.
5. Static mount at `/static/*` from `frontend/web_dashboard/admin_dashboard/`; `/frontend` and `/dashboard` GET routes serve `index.html` as a SPA fallback.
6. Global exception handler returns `{"error": detail, "status_code": code}`.

**Request flow:** Router → `Depends(get_current_user|require_role|require_admin)` → service layer (`anomaly_service`) → Repository (DB) → `broadcast_service.emit_*` → ConnectionManager → all sockets in channel.

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

#### Authentication (`app/core/security.py`, `app/auth/`, `app/api/deps.py`)

- **JWT (HS256)**: access token (`type="access"`, default 30 min, claims: `sub` user_id, `role`, `username`); refresh token (`type="refresh"`, default 7 days, sub only).
- **Password hashing**: bcrypt; passwords are truncated to 72 bytes before hashing.
- **Refresh-token storage**: only the SHA-256 hash is persisted in `User.refresh_token_hash`. Reuse detection: if a presented refresh token's hash does not match the stored one, all sessions are invalidated.
- **Roles enum**: `ADMIN` (full), `ANALYST` (analytics endpoints), `USER` (predict only).
- **`require_admin`**: accepts EITHER a JWT bearer with `role=="ADMIN"` OR a legacy `X-Admin-Token` header matching `ADMIN_TOKEN`. Keep both — legacy clients still rely on the header.
- **`require_role(*roles)`**: factory returning a `Depends()` that 403s on mismatch.

#### City-specific hybrid models (v3.1) (`app/ml/models/`, `app/services/city_model_service.py`)

**Goal**: per-city models capture each city's unique seasonal patterns, monsoon profiles, and topographic vulnerabilities. The global `anomaly_service` remains as a fallback for cities without trained models.

**Architecture (one model per city)** in `app/ml/models/city_hybrid.py`:
- **Autoencoder**: Dense `[64, 32, 16]` → latent **8** → mirrored decoder → `linear` reconstruction. Dropout 0.20.
- **LSTM + Attention**: `LSTM(64, return_sequences=True)` → **`BahdanauAttention(units=32)`** (additive, causal — `app/ml/models/attention.py`) → `LSTM(32)` → `Dense(16)` → `Dense(1, sigmoid)`. Sequence length = 7.
- **NO BiLSTM** — strictly causal forward LSTM, suitable for real-time forecasting.
- **Hybrid score**: `0.55 × ae_score + 0.45 × lstm_score`, both normalised to `[0, 1]`.
- **Standardised output dict** (always returned): `{ risk_level: "Low"|"Medium"|"High", anomaly_score, confidence, is_anomaly, ae_score, lstm_score, hri_score (0–100) }`.

**`CityModelService` singleton** in `app/services/city_model_service.py`:
- `CITY_REGISTRY` — canonical slug → name / province / population / lat-lon / regional vulnerability for all 10 cities.
- Lazy-loads each city's saved model on first access; per-city `RLock` makes loading thread-safe.
- Per-city LSTM rolling buffer (`_CityBuffer`, length 7) — model emits AE-only score until the buffer fills.
- `predict(city, features, preprocessor)` is the single entry point. Falls back to a **rule-based heuristic** (`prcp/humidity/pressure` weighted score × city vulnerability) when no model exists, returning the same standardised dict with `source="heuristic"`.
- In-memory **alert log** per city (last 20 anomalies) accessed via `get_recent_alerts()`.

**Saved-model layout**:
```
backend/saved_models/city_models/
└── <slug>/
    ├── autoencoder/         # Keras SavedModel
    ├── lstm_attention/      # Keras SavedModel (optional — skipped if <100 sequences)
    ├── ae_calibration.npy   # [mean, std, p99] from training reconstruction errors
    └── preprocessor.joblib  # WeatherDataPreprocessor fitted on this city's data
```

**Training** (`scripts/train_city.py`): args `--city <name>` or `--all`; `--data`, `--epochs`, `--batch-size`, `--no-lstm`, `--seed`, `--min-records`. Per-city training pipeline:
1. Filter master CSV to one city (`city` column).
2. Fit `WeatherDataPreprocessor` on that city's data.
3. Split (no leakage), train AE first, calibrate `[mean, std, p99]` on AE errors.
4. If ≥100 sequences, train LSTM+Attention on overlapping length-7 windows.
5. Save → registry hot-swap via `city_model_service.register_model(slug, model)`.

**Bahdanau Attention layer** (`app/ml/models/attention.py`):
- Score: `e_t = V · tanh(W·h_t + U·s)`, weights `softmax(e_t)`, context `Σ aₜ · hₜ`.
- Optional `mask` argument for padding handling.
- `get_config` / `from_config` implemented — Keras-loadable via `custom_objects={"BahdanauAttention": BahdanauAttention}`.

#### Anomaly detection (`app/services/anomaly_service.py`)

Singleton `anomaly_service` (module-level instance).

- **Architecture**: `WeatherAutoencoder` (Dense [32,16,8] → latent 6) + `LSTMAutoencoder` (32 units, sequence length 7) → `HybridAnomalyDetector` (weighted-average of normalized AE + LSTM scores).
- **Per-city sequence buffer** (`_CitySequenceBuffer`): rolling deque of length 7 per city. `predict()` pushes the current point; LSTM scoring only fires once the buffer is full. Thread-safe.
- **Warm-up on startup** (`_warm_hybrid_buffer_after_load`): if `HYBRID_WARMUP_ENABLED`, loads `HYBRID_WARMUP_CSV` (or first CSV in `data/`), transforms via the saved preprocessor, and seeds each city's buffer with the most recent `HYBRID_WARMUP_ROWS_PER_CITY` rows. This is what makes the LSTM produce useful scores from the very first request.
- **Seasonal threshold multiplier** (`SEASONAL_THRESHOLD_MULTIPLIER`): monsoon months 6–9 get 1.4–1.5×; suppresses false alarms during expected monsoon precipitation.
- **HRI** (`compute_hri`): `0.40 * anomaly_norm + 0.35 * rainfall_norm + 0.25 * regional_vulnerability` → scaled to int 0–100. Labels: <25 Low, <50 Guarded, <75 Elevated, ≥75 Severe. Vulnerabilities are per-city (Gilgit 0.90 highest, Multan 0.60 lowest) in `ModelConfig.REGIONAL_VULNERABILITY`.
- **Cloudburst rule engine** (`_assess_cloudburst_risk`): weighted score from `prcp (0.45) + pressure (0.25) + humidity (0.20) + cloud_cover (0.10)`; ×1.2 in monsoon, ×1.1 in flash-flood-prone cities (Islamabad, Rawalpindi, Peshawar, Lahore, Karachi). `is_cloudburst_likely` requires score ≥ 0.5 **AND** heavy precip **AND** (high humidity OR low pressure).
- **Consensus score** (`compute_consensus_score`): `0.45 × hybrid + 0.35 × cloudburst + 0.20 × (HRI/100)`. Prevents the rule engine from dominating when ML disagrees.
- **Training** (`train`): split-before-fit (no leakage); preprocessor fitted on train only; trains AE → optionally LSTM (skipped if <100 sequences) → builds `HybridAnomalyDetector` → seeds buffers → saves models + preprocessor + manifest. Previous version archived to `saved_models/archive/v{n}/`.

#### ML & preprocessing (`app/ml/`, `utils/preprocessing.py`)

- **Feature groups** (`ModelConfig`): primary (`prcp`, `humidity`, `pressure`, `cloud_cover` — heavily weighted), secondary (`dew_point`, `wspd`), context (`tmin`, `tmax`, `tavg`, `temp_range` — barely weighted to suppress diurnal noise). Numerical → median imputation → weight × StandardScaler. Temporal → MinMax. Categorical → one-hot, **unseen categories produce all-zero rows** rather than failing.
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

### Public Citizen Web App (`frontend/citizen_app/`)

**Visual design** mirrors the provided `frontend design for fyp/NewWebAPP.zip` exactly — the design is the spec. The Zip's "3 iPhones side-by-side showcase" was adapted to a **single full-page web app** with responsive layout (top bar + content on desktop; bottom tab bar on mobile <900 px).

**Files** (load order in `index.html`):
1. `api.js` — plain JS HydroAPI client. Public methods: `getCities`, `getOverview`, `getCityRisk(city)`, `predict(city, weather)`, `getForecast(city)`, `getAlerts(city, n)`, `health()`, `clearCache()`. 5-minute TTL local cache + retry-with-backoff.
2. `citizen-icons.jsx` — `<CIcon name=…/>` SVG icon set (≈40 icons). Identical to the zip's design.
3. `citizen-screens.jsx` — five screens: `HomeScreen`, `ForecastScreen`, `AlertsScreen`, `LearnScreen`. **Adapted to consume real backend data** instead of the hardcoded `SCENARIO_DATA` from the zip mock-up. Includes `RiskMeter` (HRI gauge), `ForecastChart` (SVG area chart), and `Skeleton` placeholders for loading states.
4. `citizen-settings.jsx` — `SettingsScreen` (city picker as a bottom-sheet modal, language picker for English/Urdu/Punjabi/Pashto/Sindhi/Balochi, dark-mode toggle, notification prefs). **Verbatim from the zip**.
5. `citizen-app.jsx` — root `App`. Manages tab/city/theme/prefs in `localStorage`, fetches data on city change, polls every 5 min, shows toast notifications. Top-bar nav on desktop; bottom-tab nav on mobile.

**Data flow**: `App` calls `HydroAPI.getCityRisk()` + `getForecast()` + `getAlerts()` in parallel via `Promise.allSettled` on city change. Failures degrade gracefully — heuristic data is shown with a `Rule-based` badge in the risk strip, and a toast informs the user.

**Scenario mapping** (`riskToScenario` in `citizen-screens.jsx`): API `risk_level` → UI scenario.
- `Low`     → `safe` (blue-cyan tones, "All clear")
- `Medium`  → `warn` (amber, "Heads up")
- `High`    → `crit` (red, "High risk alert", animated pulse banner, alerts tab badge)

**Design tokens** (`citizen-styles.css`): `oklch`-free, hex-based `--c-*` palette directly from the zip; dark-mode triggered via `body.dark` class or `[data-theme="dark"]` attribute.

**Local persistence**: `localStorage` keys — `hg-tab`, `hg-city`, `hg-theme`, `hg-prefs` (JSON: `{city, lang, notifications, criticalOnly, quietHours, sms, shareData}`).

**Backend mount**: served from FastAPI at `/citizen` (mounted in `app/main.py` lifespan; `StaticFiles(html=True)`). The API auto-detects same-origin in production; localhost falls back to `http://127.0.0.1:8000`.

---

### Web Dashboard (`frontend/web_dashboard/admin_dashboard/`)

Static React 18 served by nginx; **no bundler**. JSX is transformed in-browser by Babel-Standalone.

#### Boot sequence (`index.html`)

1. Boot screen with spinner; `#err-box` on-page error display (no DevTools needed).
2. Loads CDN: React 18.3.1, ReactDOM 18.3.1, Babel-Standalone 7.26.10.
3. **Sequential JSX loader**: fetches → `Babel.transform(..., { presets: ['react'] })` → `eval()` in strict order: `api.js` → `components.jsx` → `viz.jsx` → `screens/*.jsx` → `app.jsx` (mounts root). Order matters because each file populates `window.*` globals consumed by later files.

#### `api.js` — plain JS (no JSX)

- **Token storage**: `sessionStorage` keys `hg_access_token`, `hg_refresh_token`, `hg_role`, `hg_username`.
- **`req(method, path, body, extraHeaders, _retried)`**: adds `Authorization: Bearer <token>`; on 401 calls `doRefresh()` (queues concurrent calls so refresh fires once) and retries one time. Refresh failure → clears tokens + dispatches `hg:unauthorized` event for `app.jsx` to react.
- **`window.API`**: `login`, `register`, `logout`, `isLoggedIn`, `getMe`, `getAnomalies`, `getAnomalyStats`, `getAnomalyById`, `getRiskMap`, `getAnalytics`, `train`, `getHealth`, `getModelInfo`, `getDatabaseStats`, `connectWs(onMessage, onClose)`, `BASE`.

#### `app.jsx` — root shell + router

Sidebar nav groups: **Operations** (Dashboard, Real-time monitoring, Cloudburst, Flash flood) · **Intelligence** (Analytics, City management, Run prediction) · **System** (Settings, User management, Database) · Logout. Holds `liveEvents` array fed by WS, `alertFiring` for critical events. `CITY_SVG_MAP` carries lat/lon/population per city.

#### `components.jsx`

Inline-SVG `Icon` set (50+ icons), animated `BrandMark`, `Sparkline`, button/card/dialog/tabs primitives — all styled against `styles.css` design tokens.

#### `viz.jsx`

`PakistanMap` (720×620 viewBox SVG with selectable city circles, heat gradient by risk in `oklch`, hover tooltips), `RiskMeterComponent` gauge, generic chart wrappers.

#### `screens/`

- `landing-auth.jsx` — pre-login: `/health` summary + login/register forms.
- `dashboard.jsx` — recent anomalies, time-series chart, latest prediction card, alert table.
- `cloudburst-flood.jsx` — event log, time-range filter, terminal-style WS feed.
- `others.jsx` — `MonitoringScreen`, `AnalyticsScreen`, `CityManagementScreen`, `PredictScreen`, `SettingsScreen`, `UserManagementScreen` (all in one file; intentional, since each is small).

#### `styles.css`

`oklch` palette as CSS custom properties, `.theme-light` override, 232 px sidebar + 1 fr main grid, mobile media queries.

---

## Infrastructure

### `docker-compose.yml`

- **`postgres:16-alpine`** (`hydroguard-db`) — db `hydroguard`, user `hydroguard`, vol `postgres_data`, healthcheck `pg_isready`.
- **`redis:7-alpine`** (`hydroguard-redis`) — password from env, vol `redis_data`, healthcheck `redis-cli ping`.
- **`hydroguard-api`** — built from root `Dockerfile` (multi-stage `python:3.11-slim`); env: `DATABASE_URL=postgresql://...`, `REDIS_URL`, JWT vars, `HYBRID_WARMUP=true`. Mounts `./backend/data`, `./backend/saved_models`, `./backend/logs`. Healthcheck `curl -sf /health`. Depends on db + redis.
- **`nginx:alpine`** — mounts `./nginx/nginx.conf` (ro), `./nginx/certs` (ro), and `./frontend/web_dashboard/admin_dashboard` → `/usr/share/nginx/html`. Ports `80:80`, `443:443`.

### `nginx/nginx.conf`

Upstream `hydroguard_api` → `hydroguard-api:8000`. WebSocket upgrade at `/ws/*` (`Upgrade`/`Connection` headers, 86400 s timeouts). Regex match for API paths (`/predict`, `/anomalies`, `/analytics`, `/risk-map`, `/train`, `/health`, `/auth`, `/model`, `/docs`, `/redoc`, `/openapi.json`). All other paths → static SPA with `try_files $uri $uri/ /index.html`. HTTPS server block present but cert paths commented.

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

- **ML architecture is fixed**: Autoencoder + LSTM + **Bahdanau Attention** per-city hybrid. **No BiLSTM**: the system must remain causal so the LSTM can be used for real-time forecasting. The global `anomaly_service` (legacy AE+LSTM hybrid, no attention) is kept only as a fallback.
- **City-specific models are required**: each of the 10 cities trains its own AE+LSTM+Attention model. `CityModelService` lazy-loads them; missing models route through a heuristic. Don't replace the per-city design with a single global model.
- **Standardised output dict**: every prediction returns `{ risk_level, anomaly_score, confidence, is_anomaly, ae_score, lstm_score, hri_score }`. Risk levels are `Low | Medium | High` (no `Critical` — that maps to `High` in v3.1). The backend translates this to scenario `safe | warn | crit` via `_risk_to_scenario` in `app/api/routes/city_predictions.py`.
- **Citizen web app must follow the zip design**: do not redesign hero cards, color tokens, or layout primitives without referencing `frontend design for fyp/NewWebAPP.zip`. The zip is the visual contract.
- **Mobile dependencies removed in v3.1**: the Flutter project (`frontend/weather_anomaly_app/`) is deprecated — do not extend it. All new client work goes into the web apps.
- **JWT secret must be set** in production; the placeholder logs a warning but the app still runs (tokens are guessable).
- **WebSocket auth uses `?token=` query param** intentionally — browsers cannot send custom headers on the WS handshake.
- **`AnomalyRepository` canonical location**: `app/db/repositories/anomaly_repo.py`. The old broken copy embedded in `anomaly_service.py` was deleted in v3.0 — do not resurrect it.
- **`UserRepository` is NOT re-exported** from `app/db/__init__.py` — circular import via `app.auth.models`. Always `from app.db.repositories.user_repo import UserRepository`.
- **`init_db()` must import `User`** before `Base.metadata.create_all()` or the `users` table will silently not be created.
- **`asyncio_mode = "auto"`** — do not add `@pytest.mark.asyncio` decorators; they are unnecessary and noisy.
- **SQLite ↔ PostgreSQL**: multi-worker prod requires PostgreSQL; SQLite has write races at `--workers > 1`. `run_server.py` warns when this combo is used.
- **`require_admin` accepts both** JWT `role=ADMIN` and legacy `X-Admin-Token` header — keep both paths working.
- **Web dashboard is JSX-via-CDN-Babel**, not a bundler build. Don't introduce JSX-only syntax that Babel-Standalone cannot transform, and respect the load order in `index.html` — every `window.*` global must exist by the time the next file evals. The new `screens/screens.jsx` is loaded **after** the legacy screens so it intentionally overrides them.
- **Citizen app uses fetch-based caching, not WebSockets**: HydroAPI has a 5-minute in-memory TTL cache. To force a refresh, call `HydroAPI.clearCache()` (the Refresh button does this). Don't add WebSocket clients to the citizen app — keep it polling-only for simpler offline behaviour.
- **WebSocket fan-out is per-worker**: today's deployment is single-worker. If you scale uvicorn, you'll need a Redis pub/sub bridge between `ConnectionManager` instances.
- **City model loading is thread-safe via per-slug RLock** — concurrent first-touch predictions race on the same lock and only one filesystem load happens per city.
- **CORS with `*`**: when `CORS_ORIGINS` contains `*`, FastAPI cannot allow credentials. The dashboard's auth flow requires specific origins (with credentials) in production.
- **Bahdanau Attention is custom** — when loading saved LSTM models, always pass `custom_objects={"BahdanauAttention": BahdanauAttention}` to `keras.models.load_model`. `CityHybridModel.load()` already does this.
