# HydroGuard-AI v3.2 — Complete Production-Grade System Audit

**Audit Date:** 2026-05-08
**Actual System Version:** v3.2.0 (`app/main.py:38`) — CLAUDE.md is outdated (documents v3.1)
**Auditor Scope:** 95 Python files, 7 JSX/JS files, 2 CSS files, all infrastructure files

---

## 1. System Overview

### Architecture Classification

**Monolithic FastAPI Backend + CDN-Babel React Frontends + Redis + PostgreSQL**
Not microservices. One uvicorn process hosts all APIs, WebSockets, static files, and ML inference.

### Major Subsystems

```
┌─────────────────────────────────────────────────────────────┐
│              HydroGuard-AI v3.2 Architecture                │
├──────────────┬──────────────────┬──────────────────────────┤
│ Citizen App  │  Admin Dashboard │      FastAPI Backend       │
│ React+Babel  │  React+Babel CDN │                           │
│ 6-file SPA   │  7-file SPA      │  /api/v2/*  (v2 router)  │
│ polling      │  WebSocket       │  /cities/*  (legacy)      │
│ 5-min cache  │  30s refresh     │  /auth/*    (JWT)         │
│              │                  │  /ws/*      (realtime)    │
│              │                  │  /anomalies (DB read)     │
├──────────────┴──────────────────┤  /health, /risk-map       │
│              nginx              ├───────────────────────────┤
│  HTTP proxy + WS upgrade +      │        ML Services         │
│  static files + SPA fallback    │  CityModelService         │
│  (HTTPS DISABLED in production) │  AnomalyService (legacy)  │
├─────────────────────────────────┤  FusionModel (LightGBM)  │
│       Docker Compose Stack      │  CalibrationService       │
│  postgres:16 + redis:7 +        │  OODDetector              │
│  hydroguard-api + nginx +       │  DriftMonitor (PSI)       │
│  postgres-backup sidecar        │  WeatherAPI provider      │
└─────────────────────────────────┴───────────────────────────┘
```

### Version Reality Gap

CLAUDE.md documents **v3.1** (LSTM + BahdanauAttention). The codebase is **v3.2** — a significant architectural shift:

| Component | v3.1 (CLAUDE.md) | v3.2 (Actual code) |
|---|---|---|
| Temporal model | LSTM + BahdanauAttention | **TCN (CausalTCN, dilations [1,2,4,8])** |
| Score fusion | Weighted avg: 0.55×AE + 0.45×LSTM | **LightGBM FusionModel (16 features)** |
| Calibration | p99 threshold | **IsotonicCalibrator → P(event) [0,1]** |
| Anomaly scoring | Hybrid score [0,1] | **event_probability [0,1] + confidence_interval** |
| OOD detection | None | **Mahalanobis distance OODDetector** |
| Explainability | None | **SHAP drivers** |
| Labeling | Manual training labels | **Weak label engine (heuristic rules)** |
| API | /cities/* only | **/api/v2/* (cities, events, labels, drift, training)** |
| Cities tracked | Fixed 10 | **Dynamic discovery from CSV + disk** |
| Weather data | Manual input only | **WeatherAPI/Open-Meteo live provider** |
| attention.py | Present | **DELETED — replaced by TCN** |
| CITY_METADATA | 10 cities | **6 cities (Islamabad, Rawalpindi, Lahore, Karachi, Peshawar, Quetta)** |

---

## 2. ML Pipeline Analysis

### A. Data Flow: Raw Input → Prediction Output

```
TRAINING PATH (scripts/train_city.py):
  CSV row (prcp, humidity, pressure, cloud_cover, tmin, tmax, tavg, dew_point, wspd, city, date)
    ↓ _ensure_derived() [train_city.py:81–91]
    → Injects zeros for: pressure_delta_3h, pressure_delta_6h, rain_rate_1h,
                         rain_accumulation_3h/6h, cloud_jump_3h
    → Injects 1.0  for:  prcp_climo_pct, humidity_climo_pct
    → Injects 0.0  for:  pressure_climo_z (INCONSISTENCY — not in NUMERICAL_V2 correctly)
    ↓ WeatherDataPreprocessorV2.fit/transform() [preprocessing_v2.py:78–164]
    → NUMERICAL_V2 (22):   StandardScaler + median impute (rolling → 0-impute)
    → TEMPORAL_V2 (5):     MinMaxScaler (month, day, dayofweek, is_weekend, is_monsoon_month)
    → CATEGORICAL_V2 (2):  OneHotEncoder (city_slug, season); unseen → all-zero
    → PASSTHROUGH_V2 (2):  vulnerability, is_flash_flood_prone
    ↓ Weak label generation [label_city(), train_city.py:342–357]
    → Binary label via 95th-percentile heuristics on prcp, humidity, pressure, cloud_cover
    → NOT ground truth — purely statistical
    ↓ Split: 80% train / 10% val / 10% calibration (chronological, no leakage)
    ↓ Phase 1: AE training on X_train[weak_label==0] (fair-weather rows)
    ↓ Phase 2: TCN training on full X_train → next-step reconstruction (seq_len=24)
    ↓ Phase 3: FusionModel (LightGBM) on calibration set
    ↓ Phase 4: IsotonicCalibrator on fusion outputs
    ↓ Phase 5: OODDetector.fit() on training feature subset
    ↓ Atomic save to: autoencoder.keras, tcn_reconstructor.keras, ae_ecdf.pkl,
                      tcn_ecdf.pkl, lgbm_model.pkl, calibrator.pkl, ood_detector.pkl,
                      preprocessor_v2.joblib, training_metrics.json

INFERENCE PATH (city_model_service.predict_v2()):
  Dict input (prcp, humidity, pressure, etc.)
    ↓ FeaturePipelineV2.build_features() OR _v2_feature_defaults() [lines 498–542]
    ↓ CRITICAL: rolling_delta features HARDCODED TO 0.0 [lines 531–542]
       (OOD trained on zeros, real values cause Mahalanobis explosion)
    ↓ OODDetector.is_ood(features) — skip if no detector
    ↓ If no model → heuristic fallback [_heuristic_predict()]
    ↓ WeatherDataPreprocessorV2.transform(features) → x_vec (input_dim,)
    ↓ _CityBuffer.push_and_get() → sequence (24, input_dim) or None
    ↓ CityHybridModel.predict(x_vec, sequence):
       AE:  rec = ae(x2d); ae_error = MSE(x2d, rec); ae_pct = ECDF(ae_error)
       TCN: pred = tcn(seq3d); tcn_error = MSE(pred, x2d); tcn_pct = ECDF(tcn_error)
       → {ae_percentile, tcn_percentile, ae_variance, tcn_variance}
    ↓ FusionModel.predict_scalar(16 features) → p_raw [0,1]
    ↓ IsotonicCalibrator.transform(p_raw) → event_probability + confidence_interval
    ↓ SHAP explainability → drivers dict (top 3 features)
    ↓ Risk band: Low[0,0.25) / Moderate[0.25,0.50) / High[0.50,0.75) / Severe[0.75,1.0]
    ↓ is_alert = event_probability >= 0.50
    ↓ Return: {inference_id, city, event_probability, risk_band, is_alert,
               component_scores, confidence_interval, uncertainty, drivers, ...}
```

### B. Model Architecture (Actual v3.2)

**Autoencoder Branch:**
```
Input (input_dim,)
  → Dense[64, ReLU, Dropout 0.20]
  → Dense[32, ReLU, Dropout 0.20]
  → Dense[16, ReLU, Dropout 0.20]
  → Dense[8,  ReLU]  ← latent
  → Dense[16, ReLU, Dropout 0.20]
  → Dense[32, ReLU, Dropout 0.20]
  → Dense[64, ReLU, Dropout 0.20]
  → Dense[input_dim, linear]

Trained on FAIR-WEATHER ROWS ONLY (weak_label == 0)
Score: ECDF percentile rank of reconstruction MSE
```

**TCN Branch (replaces LSTM+Attention):**
```
Input (24, input_dim,)
  → CausalConv1D, dilations=[1,2,4,8], filters=64, kernel=3
  Receptive field = 31 timesteps. Strictly causal (no future leakage).
  Trained on FULL training set for next-step MSE prediction.
  Score: ECDF percentile rank of forecasting error
  Cold-start: First 24 predictions return tcn_pct=0.0 (no sequence available)
```

**FusionModel (LightGBM):**
```
16 features:
  ae_percentile, tcn_percentile, ae_variance, tcn_variance,
  pressure_delta_3h, pressure_delta_6h, rain_rate_1h, rain_accumulation_3h,
  prcp_climo_pct, humidity_climo_pct, moisture_flux, tdew_spread, cloud_jump_3h,
  month, is_monsoon_month, vulnerability

Trained on last 10% of data (calibration set) with weak labels
Output: p_raw ∈ [0,1], then IsotonicCalibrator → event_probability
Metrics gate: AUC ≥ 0.70 required (else training fails), ECE ≤ 0.10 (warning only)
```

### C. Training vs Inference Consistency

| Feature | Training | Inference | Status |
|---|---|---|---|
| Rolling deltas (pressure_delta_*, rain_rate_*) | Filled with 0.0 | Hardcoded to 0.0 | Intentional workaround — masks real dynamics |
| Climo features (prcp_climo_pct, humidity_climo_pct) | Filled with 1.0 | Hardcoded to 1.0 | Same workaround |
| Preprocessor version | Always V2 | V2 preferred, V1 fallback | Risk if old models loaded |
| Weak labels | 95th-percentile heuristic | N/A (inference only) | Labels are statistical proxies, not ground truth |
| Data splits | Chronological 80/10/10 | N/A | Correct — no leakage |
| Sequence length | seq_len=24 (TCN_SEQ_LEN) | seq_len=24 | Consistent |

### D. Saved Model Artifacts (Per City)

```
backend/saved_models/city_models/{slug}/
  ├── autoencoder.keras         ← Required (AE weights)
  ├── tcn_reconstructor.keras   ← Required (TCN weights)
  ├── ae_ecdf.pkl               ← Required (AE ECDF threshold calibration)
  ├── tcn_ecdf.pkl              ← Required (TCN ECDF threshold calibration)
  ├── lgbm_model.pkl            ← Required (FusionModel LightGBM)
  ├── calibrator.pkl            ← Required (IsotonicCalibrator)
  ├── ood_detector.pkl          ← Required (Mahalanobis OOD detector)
  ├── preprocessor_v2.joblib    ← Required (V2 feature preprocessor)
  ├── training_metrics.json     ← Required (AUC, ECE, metadata)
  └── ae_calibration.npy        ← Legacy backward-compat (mu/std/p99)
```

**Failure modes if artifacts missing:**
- No `autoencoder.keras` → model load fails → falls back to heuristic
- No `preprocessor_v2.joblib` → tries `preprocessor.joblib` (v1) → may produce wrong feature order
- No `lgbm_model.pkl` / `calibrator.pkl` / `ood_detector.pkl` → optional features disabled, still runs

---

## 3. Backend Status

### A. Complete Route Inventory

| Method | Path | Auth | Status |
|---|---|---|---|
| GET | `/` | None | ✓ Functional |
| GET | `/health` | None | ✓ Functional (rich status) |
| GET | `/model/info` | None | ✓ Functional |
| GET | `/model/versions` | None | ✓ Functional |
| GET | `/model/registry` | None | ✓ Functional |
| GET | `/model/registry/{slug}` | None | ✓ Functional |
| GET | `/drift` | None | ⚡ Redirects to `/api/v2/drift` |
| GET | `/drift/{slug}` | None | ⚡ Redirects to `/api/v2/drift/{slug}` |
| GET | `/frontend`, `/dashboard` | None | ✓ Serves index.html |
| GET | `/anomalies` | None | ✓ Functional (paginated, filtered) |
| GET | `/anomalies/statistics` | None | ✓ Functional |
| GET | `/anomalies/{id}` | None | ✓ Functional |
| GET | `/risk-map` | None | ✓ Functional (public HRI for all cities) |
| GET | `/admin/analytics` | Admin | ✓ Functional |
| GET | `/database/statistics` | None | ⚠ DUPLICATE — registered twice (collision) |
| POST | `/predict` | None | ⚡ Tombstoned → 308 redirect to v2 |
| POST | `/predict/batch` | None | ⚡ Tombstoned → 308 redirect to v2 |
| POST | `/train` | None | ⚡ Tombstoned → 308 redirect to v2 |
| GET | `/cities` | None | ✓ Functional (legacy) |
| POST | `/cities/refresh` | Admin | ✓ Functional |
| GET | `/cities/overview` | None | ✓ Functional (legacy) |
| GET | `/cities/{city}/risk` | None | ✓ Functional (legacy) |
| POST | `/cities/{city}/predict` | None | ✓ Functional (legacy) |
| GET | `/cities/{city}/forecast` | None | ✓ Functional |
| GET | `/cities/{city}/alerts` | None | ✓ Functional |
| GET | `/cities/{city}/status` | None | ✓ Functional |
| POST | `/cities/{city}/train` | Admin | ✓ Functional (background task) |
| GET | `/analytics` | None | ✓ Functional (alias) |
| POST | `/auth/register` | None | ⚠ NO RATE LIMIT |
| POST | `/auth/login` | None | ⚠ NO RATE LIMIT |
| POST | `/auth/refresh` | None | ✓ Functional (rotation + reuse detection) |
| GET | `/auth/me` | JWT | ✓ Functional |
| POST | `/auth/logout` | JWT | ✓ Functional |
| WS | `/ws/anomalies?token=` | JWT | ✓ Functional |
| WS | `/ws/risk-map?token=` | JWT | ✓ Functional |
| WS | `/ws/health` | None | ✓ Functional (public) |
| GET | `/api/v2/cities` | None | ✓ Functional |
| GET | `/api/v2/cities/overview` | None | ✓ Functional (uses default weather, not live) |
| GET | `/api/v2/cities/{slug}/risk` | None | ✓ Functional |
| POST | `/api/v2/cities/{slug}/predict` | None | ✓ Functional (full v2 inference) |
| GET | `/api/v2/cities/{slug}/forecast` | None | ✓ Functional |
| GET | `/api/v2/cities/{slug}/alerts` | None | ✓ Functional |
| GET | `/api/v2/cities/{slug}/status` | None | ✓ Functional |
| POST | `/api/v2/training/{slug}` | Admin | ✓ Functional (background task) |
| GET | `/api/v2/training/{slug}/status` | None | ✓ Functional |
| GET | `/api/v2/events` | None | ✓ Functional |
| GET | `/api/v2/labels` | None | ✓ Functional |
| GET | `/api/v2/drift` | None | ✓ Functional |
| GET | `/api/v2/drift/{slug}` | None | ✓ Functional |
| GET | `/weather/{slug}/current` | None | ✓ Functional (live weather) |
| GET | `/weather/overview` | None | ✓ Functional |
| GET | `/weather/{slug}/forecast` | None | ✓ Functional |

**Total: 54 routes. 46 functional, 3 tombstoned (redirect), 1 duplicate collision, 2 auth endpoints without rate limiting.**

### B. Service Layer Status

| Service | File | Status | Notes |
|---|---|---|---|
| `CityModelService` | `services/city_model_service.py` | ✓ Core — fully functional | Dynamic city discovery, lazy loading, per-slug RLock |
| `WeatherAPIProvider` | `services/weather_api.py` | ✓ Functional | WeatherAPI / Open-Meteo; falls back to defaults if key missing |
| `BroadcastService` | `services/broadcast_service.py` | ✓ Functional | Emits on anomaly OR hri_score ≥ 40 |
| `CalibrationService` | `services/calibration_service.py` | ✓ Functional | Periodic isotonic recalibration |
| `EventBus` | `services/event_bus.py` | ✓ Functional | Redis pub/sub for cross-service event fan-out |
| `RollingWindowBuffer` | `services/rolling_window.py` | ✓ Functional | Sliding window sensor aggregation |
| `ModelRegistry` | `services/model_registry.py` | ✓ Functional | Model versioning and lineage tracker |
| `DatasetProfiler` | `services/dataset_profiler.py` | ✓ Functional (utility) | Statistics on training dataset |
| `ClimatologyStore` | `services/climatology_store.py` | ✓ Functional | Historical seasonal baselines |
| `ConnectionManager` | `realtime/manager.py` | ✓ Functional | WebSocket channel manager, async-safe with lock |

### C. Authentication Flow (End-to-End)

```
Registration:  POST /auth/register
  → hash_password(plain[:72]) with bcrypt
  → create User (role="USER", cannot be escalated via registration)
  → create_access_token(user_id, role, username)  [30 min, HS256]
  → create_refresh_token(user_id)  [7 days, HS256]
  → SHA-256 hash refresh token → store in User.refresh_token_hash
  → return {access_token, refresh_token}

Login:         POST /auth/login
  → lookup user by email → bcrypt.checkpw()
  → same token generation as registration
  → update last_login timestamp

Token Refresh: POST /auth/refresh
  → decode refresh token → verify type="refresh"
  → SHA-256 hash presented token → compare to stored hash
  → MISMATCH → replay attack detected → invalidate ALL sessions (set hash=NULL)
  → MATCH → issue new access_token, update stored hash

Protected API: GET /auth/me, POST /predict, WS /ws/anomalies
  → Authorization: Bearer {access_token}  (HTTP)
  → ?token={access_token}  (WebSocket — browsers cannot send custom headers on WS)
  → decode_token() → validate type="access", expiry, signature

Admin paths:   Accepts EITHER JWT(role=ADMIN) OR X-Admin-Token header (legacy)
```

### D. Key Backend Bugs

**Bug #1 — Rate Limiting Configured But Never Applied (severity: HIGH)**
`app/core/limiter.py` creates the singleton. `app/main.py:154–155` registers the exception handler.
Zero `@limiter.limit()` decorators exist anywhere in the codebase.
Brute-force attacks on `POST /auth/login` and registration enumeration are unrestricted.

**Bug #2 — DEBUG Mode Bypasses JWT Secret Validation (severity: CRITICAL)**
`app/core/config.py:123–135`: If `DEBUG=true`, startup continues even with an empty or placeholder
`JWT_SECRET_KEY`. An attacker knowing `DEBUG=true` can forge any JWT with `""` as the secret
and impersonate any user including administrators.

**Bug #3 — Route Collision on `/database/statistics` (severity: MEDIUM)**
Both `app/api/routes/risk_analytics.py:104` and `app/api/routes/analytics_aliases.py:49` register
`GET /database/statistics`. FastAPI silently uses the first-registered handler; the second is dead.

**Bug #4 — `run_server.py` SQLite Warning Never Fires (severity: LOW)**
`backend/run_server.py:41` uses `APIConfig.__dict__.get("DATABASE_URL", ...)`.
`APIConfig` is a class with no instance `__dict__` for runtime values — the check silently fails.
The multi-worker + SQLite danger warning is never shown.

**Bug #5 — Missing Explicit DB Rollback in `get_db()` (severity: MEDIUM)**
`app/db/database.py:154–160`: Context manager closes session in `finally` but never calls
`db.rollback()` on exception. SQLAlchemy handles rollback internally, but explicit rollback
prevents partial-commit state in edge cases where an exception is caught mid-transaction.

---

## 4. Frontend Status

### Citizen App — Screen by Screen

**Home Screen** (`citizen-screens.jsx:178–309`) — **PARTIALLY WORKING**
- ✓ Risk level, HRI, rainfall, temperature, humidity display wired to `getCityRisk()`
- ✓ Loading skeletons, graceful degradation on API failure
- ✓ v1 and v2 response structures both normalized via `normRisk()` (lines 53–68)
- ✗ Hourly forecast strip is **MOCKED**: hardcoded +2h/+4h/+6h offsets with synthetic
  calculations (lines 199–207). `forecast` prop is fetched but never consumed here.
- ✗ Advice cards are decorative (no click handlers)

**Forecast Screen** (`citizen-screens.jsx:312–400`) — **FULLY WORKING**
- ✓ 7-day forecast from `getForecast()`, correctly maps both v1 and v2 field names
- ✓ SVG area chart with correct min/max scaling and gradient fill
- ✓ Risk color-coding per day card

**Alerts Screen** (`citizen-screens.jsx:403–473`) — **PARTIALLY WORKING**
- ✓ Real backend alerts from `getAlerts()`, normalizes v1 + v2 response structures
- ✗ **Static hardcoded alerts always appended** (lines 427–437):
  "Elevated flood risk" and "Heavy rain advisory" always appear even with real backend data
- ✗ **Filter buttons (All / My area / National) have no `onClick` handlers** (lines 444–448)

**Learn Screen** (`citizen-screens.jsx:476–538`) — **STATIC / INFORMATIONAL**
- All content hardcoded. No API calls. Phone `tel:` links functional.
- Acceptable for current project scope.

**Settings Screen** (`citizen-settings.jsx:191–367`) — **PARTIALLY WORKING**
- ✓ Theme toggle, city picker, language selector, notification prefs persist to `localStorage`
- ✓ City list fetched from `getCities()` with static `PK_CITIES` fallback if API fails
- ✗ **Sign-out button has no `onClick` handler** (`citizen-settings.jsx:352`)
  Users cannot log out of the citizen app.

**Citizen API.js Audit**

| Function | Endpoint | Cache TTL | Status |
|---|---|---|---|
| `getCities()` | `GET /api/v2/cities` | 10 min | ✓ Correct |
| `getOverview()` | `GET /api/v2/cities/overview` | 1 min | ✓ Correct (aggressive polling) |
| `getCityRisk(city)` | `GET /api/v2/cities/{slug}/risk` | 5 min | ✓ Correct |
| `predict(city, weather)` | `POST /api/v2/cities/{slug}/predict` | — | ✓ Correct |
| `getForecast(city)` | `GET /api/v2/cities/{slug}/forecast` | 10 min | ✓ Correct |
| `getLiveWeather(city)` | `GET /weather/{slug}/current` | 5 min | ✓ Correct |
| `getAlerts(city, n)` | `GET /api/v2/cities/{slug}/alerts?n=` | — | ✓ Correct |
| `health()` | `GET /health` | — | Defined but never called in citizen app |

### Admin Dashboard — Screen by Screen

**Dashboard Screen** (`screens/screens.jsx:55–169`) — **CRASHES ON RENDER**
- ✓ KPI cards, risk table, live WebSocket event feed
- ✓ Export JSON and Refresh buttons wired
- ✗ **Line 75: `CITIES.length` — `CITIES` global is undefined.**
  Should be `cities` prop from `useCityList()`. Causes `TypeError: Cannot read properties
  of undefined (reading 'length')` on every render.

**Real-Time Monitoring Screen** (`screens.jsx:172–244`) — **FULLY WORKING**
- ✓ Health metrics polled every 30s, WS event terminal, pause/resume/clear buttons
- ✓ v2-compatible field parsing (risk_band, is_alert, event_probability)

**Cloudburst Detection Screen** (`screens.jsx:247–301`) — **MOSTLY WORKING**
- ✓ Live WS events filtered by risk level
- ✗ Filter count logic checks "High"/"Medium"/"Low" but v2 API may emit uppercase variants.
  `toLowerCase()` not applied consistently on all event fields.

**Flash Flood Risk Screen** (`screens.jsx:304–354`) — **FULLY WORKING**
- ✓ City cards with HRI score bars, 60-second auto-refresh

**Analytics Screen** (`screens.jsx:357–425`) — **FULLY WORKING**
- ✓ KPI cards, risk distribution chart, top-city ranking

**City Management Screen** (`screens.jsx:428–668`) — **FULLY WORKING**
- ✓ City list with model/data badges, training trigger, model status display
- ✓ Score breakdown bars, 7-day forecast per city, `refreshCityRegistry()` admin action

**Prediction Screen** (`screens.jsx:672–826`) — **MOSTLY WORKING**
- ✓ Form wired to `API.cityPredict()`, result rendering correct with SHAP drivers
- ✗ No input validation — empty form submission sends a request with no fields

**Settings Screen, Profile Screen** — Working (informational display only)

**Admin API.js Audit**

| Area | Status | Notes |
|---|---|---|
| Token refresh (single-flight) | ✓ Correct | Queues concurrent calls, fires once |
| Token storage | ⚠ `sessionStorage` | Lost on page close; not persisted across browser refresh |
| Max retry on refresh failure | ✗ Missing | If `/auth/refresh` permanently fails, spins forever |
| WebSocket reconnect | ✓ Correct | Exponential backoff 1s → 30s cap |
| WS auth query param | ⚠ Security note | `?token=` logged by proxies; necessary trade-off for browser WS |
| Unused API functions | ✗ Dead code | `getDriftState()`, `getEvents()`, `getCityRegistry()`, `profileDataset()` defined but never called from any screen |

---

## 5. Integration Map

### End-to-End Prediction Flow

```
USER ACTION: Citizen selects city "Lahore"
  ↓
citizen-app.jsx:269 → HydroAPI.cancelCity(prev) → abort previous request
  ↓
Promise.allSettled([getCityRisk('lahore'), getForecast('lahore'), getAlerts('lahore', 8)])
  ↓
api.js → fetch('/api/v2/cities/lahore/risk')
  ↓
app/api/v2/cities.py → city_risk()
  ↓
city_model_service.predict_v2('lahore', weather_dict)
  ↓  [if model loaded]
  WeatherDataPreprocessorV2.transform(feature_dict) → x_vec
  _CityBuffer.push_and_get() → sequence (24 steps) or None (cold start)
  CityHybridModel.predict(x_vec, sequence)
    AE:  reconstruct → ECDF → ae_percentile
    TCN: next-step error → ECDF → tcn_percentile
  FusionModel.predict_scalar(16 features) → p_raw
  IsotonicCalibrator.transform(p_raw) → event_probability
  SHAP → drivers (top 3 contributing features)
  risk_band = Low / Moderate / High / Severe
  ↓  [if is_alert OR hri_score ≥ 40]
  broadcast_service.emit_anomaly(city, result)
    → ConnectionManager.broadcast('anomalies', data)
    → ws.send() to all /ws/anomalies subscribers
  ↓
Return: {event_probability, risk_band, is_alert, component_scores, drivers, ...}
  ↓
citizen-screens.jsx:
  normRisk() maps risk_band → risk_label
  riskToScenario(risk_label) → 'safe' | 'warn' | 'crit'
  HomeScreen renders accordingly

PARALLEL (Admin Dashboard WebSocket):
  app.jsx → wss://host/ws/anomalies?token=<jwt>
  Each broadcast → onMessage() → liveEvents.push(event) → DashboardScreen re-renders
```

### Integration Issues

| Issue | Severity | Location |
|---|---|---|
| `/api/v2/cities/overview` uses default weather `{prcp:0.0, humidity:60.0, pressure:1013.0}`, not live weather | Medium | `v2/cities.py:49–51` |
| Legacy `/cities/overview` and `/api/v2/cities/overview` both exist with different response shapes | Medium | Duplication |
| Forecast endpoint generates synthetic deterministic data (MD5 hash seed, not ML output) | Medium | `city_predictions.py:308` |
| Admin `CITIES` variable undefined → dashboard crashes on load | High | `screens/screens.jsx:75` |
| Citizen hourly forecast hardcoded, not from backend | Medium | `citizen-screens.jsx:199–207` |
| Risk band naming inconsistency: v3.1 "Low/Medium/High" vs v3.2 "Low/Moderate/High/Severe" coexist | Medium | Legacy vs v2 endpoints |
| OOD detector trained on zero-variance features; inference hard-codes zeros to match | High | `city_model_service.py:531–542` |
| TCN cold-start: first 24 predictions have tcn_pct=0.0 → risk underestimated initially | Medium | `city_model_service.py:185–188` |

---

## 6. Critical Issues

### P0 — Security (Must Fix Before Any Public Deployment)

**C1: DEBUG mode bypasses JWT validation** (`config.py:123–135`)
If `DEBUG=true`, an empty or placeholder `JWT_SECRET_KEY` is accepted and the app starts normally.
An attacker aware of this can forge admin-role JWTs with `""` as the HMAC secret.
**Fix:** Generate an ephemeral random key in dev mode instead of using empty/placeholder string.

**C2: No rate limiting on authentication endpoints** (`auth/router.py`)
`POST /auth/login` and `POST /auth/register` have zero rate limiting.
The `limiter` singleton exists and the exception handler is registered in `main.py`,
but **no `@limiter.limit()` decorator is applied to any route in the entire codebase**.
**Fix:** Add `@limiter.limit("5/minute")` to `/auth/login`, `/auth/register`, and `/auth/refresh`.

**C3: HTTPS completely disabled in nginx** (`nginx/nginx.conf:139–202`)
The HTTPS server block and HTTP→HTTPS redirect are commented out.
All production traffic is plaintext — JWT tokens, passwords, and weather data are exposed.
**Fix:** Uncomment the HTTPS server block, obtain TLS certificates, enable redirect.

### P1 — Runtime Crashes

**C4: Admin dashboard `DashboardScreen` crashes on every render** (`screens/screens.jsx:75`)
`CITIES.length` references an undefined global. Throws `TypeError` on mount.
**Fix:** Replace `CITIES` with `cities` prop supplied by `useCityList()` hook.

**C5: Citizen app sign-out is non-functional** (`citizen-settings.jsx:352`)
The sign-out button renders correctly but has no `onClick` handler.
Users cannot log out.
**Fix:** Add `onClick={() => clearUserState()}` or equivalent handler.

**C6: Admin token refresh has no max-retry guard** (`admin_dashboard/api.js:43–49`)
If `/auth/refresh` permanently fails (key rotation, DB corruption), the refresh function
spins indefinitely until the tab is closed.
**Fix:** Add a `maxRetries` counter; throw after N failures and dispatch `hg:unauthorized`.

### P2 — Data Quality

**C7: OOD detector suppresses real weather dynamics** (`city_model_service.py:516–542`)
The OOD detector was trained on rolling delta features (pressure_delta_3h, rain_rate_1h, etc.)
that were all zero (filled constants). Real non-zero values cause Mahalanobis distance to
explode, triggering false OOD rejection. The workaround hard-codes all these features to 0.0
at inference time — effectively suppressing real pressure and rainfall dynamics from the model.
**Fix:** Retrain OOD detector using real FeaturePipelineV2 output with actual rolling values.

**C8: Citizen home screen hourly forecast is synthetic** (`citizen-screens.jsx:199–207`)
The "+2h", "+4h", "+6h" hourly tiles are computed from a formula using current rainfall,
not from any backend forecast API. The `forecast` prop is fetched from the API but never used
by this component.
**Fix:** Consume the actual forecast array for the hourly strip.

**C9: Hardcoded static alerts always displayed** (`citizen-screens.jsx:427–437`)
Two fabricated alert cards ("Elevated flood risk", "Heavy rain advisory") are unconditionally
prepended to real backend alerts, creating confusing duplicates.
**Fix:** Only inject fallback alerts when the backend returns an empty alert list.

---

## 7. Missing Features

| Feature | Current State | User Impact |
|---|---|---|
| Real hourly forecast in citizen Home screen | Mocked / synthetic data | Users see fake predictions |
| Alert filter functionality (All / My area / National) | Buttons render, no handlers | Filtering non-functional |
| HTTPS / TLS | Fully commented out in nginx | All traffic is plaintext |
| Rate limiting applied to routes | Limiter configured but zero decorators | Auth brute force unprotected |
| CD pipeline | Placeholder `echo` in `ci.yml:159` | No automated deployment exists |
| WebSocket tests | None written | Real-time features entirely untested |
| PostgreSQL in CI | Tests use SQLite | DB-specific bugs undetected |
| Drift monitor frontend screen | Endpoints exist, no dashboard screen | Drift data inaccessible to operators |
| Label management UI | `/api/v2/labels` endpoint exists, no admin screen | Cannot view or correct training labels |
| Citizen app logout | Sign-out button non-functional | Users cannot log out |
| Security headers middleware | Not configured | Missing X-Frame-Options, CSP, HSTS |
| Multi-worker WebSocket fan-out | Planned (Redis pub/sub), not implemented | Single-worker deployment only |
| TCN buffer pre-seeding | Cold-start gives tcn_pct=0.0 for 24 steps | Risk underestimated on startup |
| Ground-truth flood labels | Heuristic 95th-percentile quantile labels only | Model may not learn real flood patterns |
| 4 city metadata entries | Faisalabad, Multan, Hyderabad, Gilgit use DEFAULT_METADATA | Vulnerability/lat-lon unknown for these cities |

---

## 8. Non-Functional / Broken Code Report

### Dead Files

| File | Issue | Severity |
|---|---|---|
| `backend/analytics_aliases.py` (repo root) | Broken import: `from app.services.anomaly_service import AnomalyRepository` — this module path does not exist. File is never imported by `main.py`. Duplicate of `backend/app/api/routes/analytics_aliases.py`. | HIGH — crashes if imported |
| `backend/ml/models/autoencoder.py` | Legacy global autoencoder model. Only used by `scripts/train.py` (legacy global training). Not part of the v3.2 per-city pipeline. | LOW — harmless legacy |
| `backend/utils/preprocessing.py` | v1 preprocessor, fully superseded by `app/ml/preprocessing_v2.py`. Only referenced by `scripts/train.py`. | LOW — harmless |
| `backend/utils/visualization.py` | Training plot utility. Not called by any v3.2 service. Only invoked by legacy `scripts/train.py`. | LOW — harmless |
| `frontend/.../screens/dashboard.jsx` | Old dashboard screen. Overridden by `screens/screens.jsx` (loaded after, overwrites `window.DashboardScreen`). | LOW — silently replaced |
| `frontend/.../screens/others.jsx` | Old multi-screen bundle. Overridden by `screens/screens.jsx`. | LOW — silently replaced |
| `backend/app/ml/models/attention.py` | **DELETED** (listed as `D` in `git status`). v3.2 replaced BahdanauAttention with TCN. Legacy references (`"lstm_attention.keras"` path, `"ae_lstm_attention"` string) remain as safe conditional fallbacks — no import-time breakage. | LOW — gracefully handled |

### Dead Code Inside Active Files

| Location | Symbol | Issue | Severity |
|---|---|---|---|
| `app/core/limiter.py` + `main.py:154–155` | `limiter` singleton | Registered and exception handler added; zero `@limiter.limit()` decorators anywhere | HIGH (security) |
| `admin_dashboard/api.js` | `getDriftState()`, `getEvents()`, `getCityRegistry()`, `profileDataset()`, `getRegistry()` | Defined but never called from any screen | LOW |
| `app/db/repositories/training_repo.py` | `TrainingRepository` | `TrainingRecord` DB model exists. No v3.2 route writes to it (training now uses `ModelRegistry` + `training_run.py`). `create()` never called in v3.2 flow. | MEDIUM |
| `citizen-app.jsx` | `API.health()` | Defined in `api.js`, never called in citizen app code | LOW |
| `screens.jsx:963` | `window._setCities = function() {}` | Empty placeholder function set on global window. Never called. | LOW |
| `city_predictions.py:153–157` | `_default_weather()` | Returns hardcoded defaults. Only called by internal `_get_weather()` fallback. The `/api/v2/cities/overview` endpoint bypasses it and passes its own hardcoded defaults. | LOW |

### Broken Runtime Paths

| Issue | File:Line | Severity |
|---|---|---|
| `CITIES.length` — undefined global, crashes `DashboardScreen` | `screens/screens.jsx:75` | CRITICAL |
| Sign-out button has no `onClick` handler | `citizen-settings.jsx:352` | HIGH |
| Alert filter buttons have no `onClick` handlers | `citizen-screens.jsx:444–448` | MEDIUM |
| Hourly forecast strip uses synthetic computed data | `citizen-screens.jsx:199–207` | MEDIUM |
| Static alerts unconditionally prepended to real alerts | `citizen-screens.jsx:427–437` | MEDIUM |
| Token refresh has no max-retry counter | `admin_dashboard/api.js:43–49` | MEDIUM |
| `CITY_METADATA` only has 6 cities (Faisalabad, Multan, Hyderabad, Gilgit missing) | `city_model_service.py:49–56` | MEDIUM |
| Route collision: `/database/statistics` registered twice | `risk_analytics.py:104` + `analytics_aliases.py:49` | MEDIUM |
| CI test matrix uses SQLite — Postgres bugs not caught | `.github/workflows/ci.yml:62` | HIGH |
| HTTPS entirely disabled in nginx | `nginx/nginx.conf:139–202` | CRITICAL |
| CD deploy step is a placeholder `echo` | `.github/workflows/ci.yml:158–159` | CRITICAL |
| Multi-worker SQLite warning never fires in `run_server.py` | `run_server.py:41` | LOW |
| `DEBUG=true` allows empty JWT secret key → all tokens forgeable | `config.py:123–135` | CRITICAL |

---

## 9. Production Readiness Score

### Overall Score: **6.5 / 10**

| Dimension | Score | Justification |
|---|---|---|
| **Functional Correctness** | 7.5/10 | Core ML pipeline works end-to-end; 46/54 API routes functional; v2 inference chain complete. Penalty: mocked forecast, crashing admin screen, non-functional buttons |
| **Security** | 4.0/10 | Solid JWT design (rotation, reuse detection, bcrypt). Critical gaps: no rate limiting, DEBUG secret bypass, HTTP-only, session-storage tokens |
| **ML Quality** | 6.5/10 | Correct causal architecture (AE+TCN+Fusion+Calibration), ECDF scoring, LightGBM fusion. Gaps: heuristic weak labels (not ground truth), OOD workaround suppresses real dynamics, 24-step cold-start zeros |
| **Test Coverage** | 4.0/10 | 32 test methods but all shallow; SQLite only; zero WebSocket tests; no business logic validation; auth fixture fragile (session-scoped, accepts 400 silently) |
| **Infrastructure** | 6.0/10 | Docker compose complete with resource limits, healthchecks, backup sidecar. Gaps: HTTPS off, CD is placeholder, TensorFlow startup (30–60s) exceeds healthcheck window |
| **Code Quality** | 7.5/10 | Clean repository pattern, DI via `Depends()`, lifespan management, async-safe WS, dynamic city discovery. Gaps: dead files, route collision, severely outdated CLAUDE.md |
| **Observability** | 5.5/10 | Rotating file logs, drift PSI in `/health`, structured drift endpoint. Gaps: no JSON structured logs, no monitoring stack (Prometheus/Grafana), no alerting |
| **Frontend** | 6.5/10 | Good API client design with v1+v2 normalization, graceful degradation, retry/backoff. Gaps: mocked data, broken buttons, session-storage auth, crash on admin dashboard |

---

### What Must Be Fixed Before Public Deployment

| Priority | Fix | Estimated Effort |
|---|---|---|
| P0 | Enable HTTPS — uncomment nginx block, obtain TLS certificate | 2 hours |
| P0 | Add `@limiter.limit("5/minute")` to `POST /auth/login` and `POST /auth/register` | 30 min |
| P0 | Fix DEBUG mode JWT bypass in `config.py:134` — generate ephemeral random key, never empty | 1 hour |
| P1 | Fix `CITIES` → `cities` prop in `screens/screens.jsx:75` | 5 min |
| P1 | Add `onClick` handler to citizen sign-out button in `citizen-settings.jsx:352` | 10 min |
| P1 | Implement CD pipeline in `ci.yml` (Docker Hub push or SSH deploy) | 4 hours |
| P1 | Switch CI tests from SQLite to PostgreSQL service | 2 hours |
| P2 | Add max-retry counter to token refresh in `admin_dashboard/api.js` | 30 min |
| P2 | Replace mocked hourly forecast in `citizen-screens.jsx:199–207` with real data | 2 hours |
| P2 | Remove or conditionally show static alerts in `citizen-screens.jsx:427–437` | 30 min |
| P2 | Wire alert filter buttons in `citizen-screens.jsx:444–448` | 1 hour |
| P2 | Add `@limiter.limit()` to city prediction endpoints (DoS protection) | 30 min |
| P3 | Add security headers middleware (X-Frame-Options, X-Content-Type-Options, HSTS) | 1 hour |
| P3 | Retrain OOD detector with real FeaturePipelineV2 output (remove zero hard-code) | 1 day |
| P3 | Add ground-truth flood labels from domain experts / historical records | Long-term |

---

### What Is Already Production-Ready

- JWT authentication system (bcrypt, HS256, token reuse detection, rotation)
- Database session management (repository pattern, no connection leaks)
- WebSocket connection management (async-safe, per-channel, dead-socket pruning)
- City model dynamic discovery and thread-safe lazy loading (per-slug RLock)
- Docker compose stack (postgres + redis + api + nginx + backup sidecar, all with healthchecks)
- AE + TCN + Fusion inference pipeline (causal, no data leakage, ECDF calibration)
- Graceful degradation (heuristic fallback when model missing; `Promise.allSettled` in frontend)
- CORS configuration (correctly rejects credentials with wildcard origin)
- Global exception handling (no stack traces leaked to API clients)
- Atomic model saves (write to tmp directory, then atomic swap to final path)
- Rate-limiting infrastructure (limiter + exception handler configured, needs decorators added)
- Drift monitoring (PSI on 4 key features, surfaced in `/health` and `/api/v2/drift`)

---

*End of Audit Report — HydroGuard-AI v3.2 | Generated: 2026-05-08*
*All findings reference actual code inspected at `D:/Programming/FYP/hydroguard_ai/`*
*File:line references reflect code state as of git commit `16cf128`*
