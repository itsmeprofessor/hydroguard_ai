HydroGuard-AI v3.2 — Complete Production-Grade System Audit

  Audit Date: 2026-05-08
  Actual System Version: v3.2.0 (app/main.py:38) — CLAUDE.md is outdated (documents v3.1)
  Auditor Scope: 95 Python files, 7 JSX/JS files, 2 CSS files, all infrastructure files

  ---
  1. System Overview

  Architecture Classification

  Monolithic FastAPI Backend + CDN-Babel React Frontends + Redis + PostgreSQL
  Not microservices. One uvicorn process hosts all APIs, WebSockets, static files, and ML inference.

  Major Subsystems

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

  Version Reality Gap

  CLAUDE.md documents v3.1 (LSTM+BahdanauAttention). The codebase is v3.2 — a significant architectural shift:

  ┌────────────────┬────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │   Component    │        v3.1 (CLAUDE.md)        │                      v3.2 (Actual code)                      │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Temporal model │ LSTM + BahdanauAttention       │ TCN (CausalTCN, dilations [1,2,4,8])                         │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Score fusion   │ Weighted avg: 0.55×AE +        │ LightGBM FusionModel (16 features)                           │
  │                │ 0.45×LSTM                      │                                                              │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Calibration    │ p99 threshold                  │ IsotonicCalibrator → P(event) [0,1]                          │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Anomaly        │ Hybrid score [0,1]             │ event_probability [0,1] + confidence_interval                │
  │ scoring        │                                │                                                              │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ OOD detection  │ None                           │ Mahalanobis distance OODDetector                             │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Explainability │ None                           │ SHAP drivers                                                 │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Labeling       │ Manual training labels         │ Weak label engine (heuristic rules)                          │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ API            │ /cities/* only                 │ /api/v2/ (cities, events, labels, drift, training)*          │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Cities tracked │ Fixed 10                       │ Dynamic discovery from CSV + disk                            │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Weather data   │ Manual input only              │ WeatherAPI/Open-Meteo live provider                          │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ attention.py   │ Present                        │ DELETED — replaced by TCN                                    │
  ├────────────────┼────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CITY_METADATA  │ 10 cities                      │ 6 cities (Islamabad, Rawalpindi, Lahore, Karachi, Peshawar,  │
  │                │                                │ Quetta)                                                      │
  └────────────────┴────────────────────────────────┴──────────────────────────────────────────────────────────────┘

  ---
  2. ML Pipeline Analysis

  A. Data Flow: Raw Input → Prediction Output

  TRAINING PATH (scripts/train_city.py):
    CSV row (prcp, humidity, pressure, cloud_cover, tmin, tmax, tavg, dew_point, wspd, city, date)
      ↓ _ensure_derived() [train_city.py:81–91]
      → Injects zeros for: pressure_delta_3h, pressure_delta_6h, pressure_delta_6h,
                           rain_rate_1h, rain_accumulation_3h/6h, cloud_jump_3h
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

  B. Model Architecture (Actual v3.2)

  Autoencoder Branch:
  Input (input_dim,) → Dense[64,ReLU,Drop0.20] → Dense[32,ReLU,Drop0.20] → Dense[16,ReLU,Drop0.20]
  → Dense[8,ReLU] (latent) → Dense[16,ReLU,Drop0.20] → Dense[32,ReLU,Drop0.20]
  → Dense[64,ReLU,Drop0.20] → Dense[input_dim,linear]
  Trained on FAIR-WEATHER ROWS ONLY (weak_label==0)
  Score: ECDF percentile rank of reconstruction MSE

  TCN Branch (replaces LSTM+Attention):
  Input (24, input_dim,) → CausalConv1D dilations=[1,2,4,8], filters=64, kernel=3
  Receptive field = 31 timesteps. Strictly causal (no future leakage).
  Trained on FULL training set for next-step MSE prediction.
  Score: ECDF percentile rank of forecasting error
  Cold-start: First 24 predictions return tcn_pct=0.0 (no sequence available)

  FusionModel (LightGBM):
  16 features: [ae_pct, tcn_pct, ae_var, tcn_var, pressure_delta_3h/6h, rain_rate_1h,
                rain_accumulation_3h, prcp_climo_pct, humidity_climo_pct, moisture_flux,
                tdew_spread, cloud_jump_3h, month, is_monsoon_month, vulnerability]
  Trained on last 10% of data (calibration set) with weak labels
  Output: p_raw ∈ [0,1], then IsotonicCalibrator → event_probability
  Metrics gate: AUC ≥ 0.70 required (else training fails), ECE ≤ 0.10 (warning only)

  C. Training/Inference Consistency Issues

  ┌───────────────────────────────────────┬──────────────────────┬────────────────────┬───────────────────────────┐
  │                Feature                │       Training       │     Inference      │         Mismatch          │
  ├───────────────────────────────────────┼──────────────────────┼────────────────────┼───────────────────────────┤
  │ Rolling deltas (pressure_delta_*,     │ Filled with 0.0      │ Hardcoded to 0.0   │ Intentional but masks     │
  │ rain_rate_*)                          │                      │                    │ real dynamics             │
  ├───────────────────────────────────────┼──────────────────────┼────────────────────┼───────────────────────────┤
  │ Climo features (prcp_climo_pct,       │ Filled with 1.0      │ Hardcoded to 1.0   │ Same issue                │
  │ humidity_climo_pct)                   │                      │                    │                           │
  ├───────────────────────────────────────┼──────────────────────┼────────────────────┼───────────────────────────┤
  │ Preprocessor version                  │ Always V2            │ V2 preferred, V1   │ Risk if old models loaded │
  │                                       │                      │ fallback           │                           │
  ├───────────────────────────────────────┼──────────────────────┼────────────────────┼───────────────────────────┤
  │ Weak labels                           │ 95th-percentile      │ N/A (inference     │ Labels are statistical    │
  │                                       │ heuristic            │ only)              │ proxies                   │
  └───────────────────────────────────────┴──────────────────────┴────────────────────┴───────────────────────────┘

  ---
  3. Backend Status

  A. Complete Route Inventory (v3.2 Actual)

  ┌────────┬────────────────────────────────┬───────┬───────────────────────────────────────────────┐
  │ Method │              Path              │ Auth  │                    Status                     │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /                              │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /health                        │ None  │ ✓ Functional (rich status)                    │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /model/info                    │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /model/versions                │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /model/registry                │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /model/registry/{slug}         │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /drift                         │ None  │ ⚡ Redirects to /api/v2/drift                 │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /drift/{slug}                  │ None  │ ⚡ Redirects to /api/v2/drift/{slug}          │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /frontend , /dashboard         │ None  │ ✓ Serves index.html                           │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /anomalies                     │ None  │ ✓ Functional (paginated, filtered)            │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /anomalies/statistics          │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /anomalies/{id}                │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /risk-map                      │ None  │ ✓ Functional (no auth — public HRI)           │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /admin/analytics               │ Admin │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /database/statistics           │ None  │ ⚠ DUPLICATE (collision)                       │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /predict                       │ None  │ ⚡ Tombstoned → 308 to v2                     │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /predict/batch                 │ None  │ ⚡ Tombstoned → 308 to v2                     │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /train                         │ None  │ ⚡ Tombstoned → 308 to v2                     │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities                        │ None  │ ✓ Functional (legacy)                         │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /cities/refresh                │ Admin │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities/overview               │ None  │ ✓ Functional (legacy)                         │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities/{city}/risk            │ None  │ ✓ Functional (legacy)                         │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /cities/{city}/predict         │ None  │ ✓ Functional (legacy)                         │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities/{city}/forecast        │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities/{city}/alerts          │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /cities/{city}/status          │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /cities/{city}/train           │ Admin │ ✓ Functional (background)                     │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /analytics                     │ None  │ ✓ Functional (alias)                          │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /auth/register                 │ None  │ ⚠ NO RATE LIMIT                               │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /auth/login                    │ None  │ ⚠ NO RATE LIMIT                               │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /auth/refresh                  │ None  │ ✓ Functional (rotation + reuse detect)        │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /auth/me                       │ JWT   │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /auth/logout                   │ JWT   │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ WS     │ /ws/anomalies?token=           │ JWT   │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ WS     │ /ws/risk-map?token=            │ JWT   │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ WS     │ /ws/health                     │ None  │ ✓ Functional (public)                         │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities                 │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities/overview        │ None  │ ✓ Functional (uses default weather, not live) │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities/{slug}/risk     │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /api/v2/cities/{slug}/predict  │ None  │ ✓ Functional (v2 inference)                   │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities/{slug}/forecast │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities/{slug}/alerts   │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/cities/{slug}/status   │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ POST   │ /api/v2/training/{slug}        │ Admin │ ✓ Functional (background task)                │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/training/{slug}/status │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/events                 │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/labels                 │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/drift                  │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /api/v2/drift/{slug}           │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /weather/{slug}/current        │ None  │ ✓ Functional (live weather)                   │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /weather/overview              │ None  │ ✓ Functional                                  │
  ├────────┼────────────────────────────────┼───────┼───────────────────────────────────────────────┤
  │ GET    │ /weather/{slug}/forecast       │ None  │ ✓ Functional                                  │
  └────────┴────────────────────────────────┴───────┴───────────────────────────────────────────────┘

  Total: 54 routes. 46 functional, 3 tombstoned (redirect), 1 duplicate collision, 2 security gaps (no rate limit on
  auth)

  B. Service Layer Status

  ┌─────────────────────┬─────────────────────────────────┬─────────────────────┬───────────────────────────────────┐
  │       Service       │              File               │       Status        │               Notes               │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │                     │                                 │ ✓ Core — fully      │ Dynamic city discovery, lazy      │
  │ CityModelService    │ services/city_model_service.py  │ functional          │ model loading, thread-safe        │
  │                     │                                 │                     │ per-slug RLock                    │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │                     │                                 │                     │ WeatherAPI / Open-Meteo; fallback │
  │ WeatherAPIProvider  │ services/weather_api.py         │ ✓ Functional        │  to default weather if key        │
  │                     │                                 │                     │ missing                           │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ BroadcastService    │ services/broadcast_service.py   │ ✓ Functional        │ Emits on anomaly OR hri≥40        │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ AnomalyService      │ MISSING from services/          │ ⚠ Module not found  │ Legacy service; routes reference  │
  │                     │                                 │ at expected path    │ it but it may be relocated        │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ CalibrationService  │ services/calibration_service.py │ ✓ Functional (init  │ Periodic isotonic recalibration   │
  │                     │                                 │ only)               │                                   │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ EventBus            │ services/event_bus.py           │ ✓ Functional        │ Redis pub/sub for event fan-out   │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ RollingWindowBuffer │ services/rolling_window.py      │ ✓ Functional        │ Sliding window for sensor data    │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ ModelRegistry       │ services/model_registry.py      │ ✓ Functional        │ Model versioning tracker          │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ DatasetProfiler     │ services/dataset_profiler.py    │ ✓ Functional        │ Statistics on training data       │
  │                     │                                 │ (utility)           │                                   │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ ClimatologyStore    │ services/climatology_store.py   │ ✓ Functional        │ Historical baselines              │
  ├─────────────────────┼─────────────────────────────────┼─────────────────────┼───────────────────────────────────┤
  │ ConnectionManager   │ realtime/manager.py             │ ✓ Functional        │ WebSocket channel manager,        │
  │                     │                                 │                     │ async-safe                        │
  └─────────────────────┴─────────────────────────────────┴─────────────────────┴───────────────────────────────────┘

  C. Key Backend Bugs

  Bug #1 — No Rate Limiting Applied (severity: HIGH)
  app/core/limiter.py creates the limiter singleton. app/main.py:154–155 registers the exception handler. But zero route
   handlers use @limiter.limit(). Brute-force attacks on POST /auth/login and registration enumeration are unrestricted.

  Bug #2 — DEBUG Mode Bypasses JWT Secret Validation (severity: CRITICAL)
  app/core/config.py:123–135: If DEBUG=true, the system starts even with an empty or placeholder JWT_SECRET_KEY. An
  attacker who knows DEBUG=true is set can forge any JWT with "" as the secret and impersonate any user including
  admins.

  Bug #3 — Route Collision on /database/statistics (severity: MEDIUM)
  Both app/api/routes/risk_analytics.py:104 and app/api/routes/analytics_aliases.py:49 define GET /database/statistics.
  FastAPI silently uses the first-registered handler. The second is dead code.

  Bug #4 — run_server.py SQLite Check Uses Wrong Pattern (severity: LOW)
  backend/run_server.py:41 uses APIConfig.__dict__.get("DATABASE_URL", ...) — APIConfig is a class with no instance dict
   for config values. The multi-worker SQLite warning never fires.

  Bug #5 — Missing Explicit DB Rollback in get_db() (severity: MEDIUM)
  app/db/database.py:154–160: The get_db() context manager closes the session in finally but never calls db.rollback()
  on exception. SQLAlchemy handles this internally, but explicit rollback is safer and prevents partial-commit state
  inconsistencies.

  ---
  4. Frontend Status

  Citizen App — Screen by Screen

  Home Screen (citizen-screens.jsx:178–309) — PARTIALLY WORKING
  - ✓ Risk level, HRI, rainfall, temperature, humidity display wired to getCityRisk()
  - ✓ Loading skeletons, graceful degradation on API failure
  - ✗ Hourly forecast strip is MOCKED: hardcoded +2h/+4h offsets with synthetic calculations (lines 199–207). forecast
  prop is fetched but never used here
  - ✗ Advice cards are decorative (no interaction handlers)

  Forecast Screen (citizen-screens.jsx:312–400) — FULLY WORKING
  - ✓ 7-day forecast from getForecast(), correctly maps v1+v2 field names
  - ✓ SVG area chart with correct min/max scaling and gradient fill
  - ✓ Risk color-coding per day

  Alerts Screen (citizen-screens.jsx:403–473) — PARTIALLY WORKING
  - ✓ Real backend alerts from getAlerts(), normalizes v1+v2 response structures
  - ✗ Static hardcoded alerts always appended (lines 427–437): "Elevated flood risk" and "Heavy rain advisory" cards
  always appear even when real data is present
  - ✗ Filter buttons (All/My area/National) have no onClick handlers (lines 444–448): decorative only

  Learn Screen (citizen-screens.jsx:476–538) — STATIC/INFORMATIONAL
  - All content hardcoded; no API calls; phone tel: links work
  - Acceptable for current scope

  Settings Screen (citizen-settings.jsx:191–367) — PARTIALLY WORKING
  - ✓ Theme toggle, city picker, language selection, notifications prefs persist to localStorage
  - ✓ City list from getCities() with static fallback
  - ✗ Sign-out button has no onClick handler (citizen-settings.jsx:352): users cannot log out of the citizen app

  Citizen API.js — FUNCTIONAL with minor issues
  - All endpoints correctly mapped to backend
  - Retry/backoff logic correct (3 retries, exponential backoff)
  - Cache TTL logic correct (5-minute default)
  - /api/v2/cities/overview polled every 1 minute — aggressively high backend load

  Admin Dashboard — Screen by Screen

  Dashboard Screen (screens/screens.jsx:55–169) — MOSTLY WORKING
  - ✓ KPI cards, risk table, live WebSocket event feed
  - ✓ Export to JSON, Refresh button wired
  - ✗ Line 75 references CITIES.length — CITIES global is undefined; should be cities prop from useCityList() hook.
  Causes "Cannot read properties of undefined" crash on render

  Real-Time Monitoring Screen (screens.jsx:172–244) — FULLY WORKING
  - ✓ Health metrics polled every 30s, WS event terminal, pause/resume/clear
  - ✓ v2-compatible field parsing (risk_band, is_alert, event_probability)

  Cloudburst Detection Screen (screens.jsx:247–301) — MOSTLY WORKING
  - ✓ Live WS events, risk filtering
  - ✗ Filter counts check for "High"/"Medium"/"Low" (mixed case) but v2 API may send "HIGH"/"MEDIUM"/"LOW";
  toLowerCase() should be applied consistently

  Flash Flood Risk Screen (screens.jsx:304–354) — FULLY WORKING
  - ✓ City cards with HRI bars, 60s auto-refresh

  Analytics Screen (screens.jsx:357–425) — FULLY WORKING
  - ✓ KPI cards, risk distribution chart, top city ranking

  City Management Screen (screens.jsx:428–668) — FULLY WORKING (most complete screen)
  - ✓ City list with model/data badges, training trigger, status display
  - ✓ Score breakdown bars, 7-day forecast per city
  - ✓ refreshCityRegistry() admin action

  Prediction Screen (screens.jsx:672–826) — MOSTLY WORKING
  - ✓ Form wired to API.cityPredict(), result rendering correct
  - ✗ No input validation — submitting empty form sends request with no fields

  Settings, Profile — Working (informational)

  Admin API.js — FUNCTIONAL with issues
  - ✓ Token refresh with single-flight (no duplicate requests)
  - ✓ WebSocket with exponential backoff, proper protocol switch
  - ✗ No max-retry counter on token refresh — infinite loop if /auth/refresh permanently fails
  - ✗ Token stored in sessionStorage (lost on page close/refresh; browser back loses session)

  ---
  5. Integration Map

  End-to-End Flow

  USER ACTION: Citizen selects city "Lahore"
    ↓
  citizen-app.jsx:269 → HydroAPI.cancelCity(prev) → abort previous fetch
    ↓
  Promise.allSettled([getCityRisk('lahore'), getForecast('lahore'), getAlerts('lahore', 8)])
    ↓
  api.js:fetchWithRetry → fetch('/api/v2/cities/lahore/risk')
    ↓
  app/api/v2/cities.py:city_risk() (GET /api/v2/cities/{slug}/risk)
    ↓
  city_model_service.predict('lahore', weather_dict)
    ↓ [if model loaded]
    WeatherDataPreprocessorV2.transform(feature_dict) → x_vec
    _CityBuffer.push_and_get() → sequence or None
    CityHybridModel.predict(x_vec, sequence)
      → AE: reconstruct → ae_percentile
      → TCN: next-step error → tcn_percentile
    FusionModel.predict_scalar(16 features) → p_raw
    IsotonicCalibrator.transform(p_raw) → event_probability
    SHAP → drivers
    risk_band = Low/Moderate/High/Severe
    ↓ [if anomaly OR hri>=40]
    broadcast_service.emit_anomaly(city, result)
      → ConnectionManager.broadcast('anomalies', data)
      → all ws.send() to /ws/anomalies subscribers
    ↓
  Return: {event_probability, risk_band, is_alert, component_scores, drivers, ...}
    ↓
  citizen-screens.jsx: normRisk() maps risk_band → risk_label
    → riskToScenario(risk_label) → 'safe' | 'warn' | 'crit'
    → HomeScreen renders accordingly

  PARALLEL (Admin Dashboard WebSocket):
    app.jsx connects wss://host/ws/anomalies?token=<jwt>
    Each broadcast triggers onMessage → liveEvents.push(event) → DashboardScreen re-renders

  Integration Issues Found

  ┌───────────────────────────────────────────────────────────────────────┬──────────┬───────────────────────────────┐
  │                                 Issue                                 │ Severity │           Location            │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ /api/v2/cities/overview uses default weather {prcp:0.0,               │ Medium   │ v2/cities.py:49–51            │
  │ humidity:60.0, pressure:1013.0} not live weather                      │          │                               │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ Legacy /cities/overview and v2 /api/v2/cities/overview both exist     │ Medium   │ Duplication                   │
  │ with different response structures                                    │          │                               │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ Forecast endpoint generates synthetic deterministic forecast (MD5     │ Medium   │ city_predictions.py:308       │
  │ hash seed, not ML)                                                    │          │                               │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ Admin CITIES variable undefined → dashboard crashes on load           │ High     │ screens.jsx:75                │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ Citizen hourly forecast mocked, not from backend                      │ Medium   │ citizen-screens.jsx:199–207   │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ Risk band naming inconsistency: v3.1 "Low/Medium/High", v3.2          │ Medium   │ Legacy vs v2 endpoints        │
  │ "Low/Moderate/High/Severe" coexist                                    │          │                               │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ OOD detector trained on zero-variance features — real inference       │ High     │ city_model_service.py:531–542 │
  │ hard-codes zeros back                                                 │          │                               │
  ├───────────────────────────────────────────────────────────────────────┼──────────┼───────────────────────────────┤
  │ TCN cold-start: first 24 predictions have tcn_pct=0.0 → risk          │ Medium   │ city_model_service.py:185–188 │
  │ underestimated                                                        │          │                               │
  └───────────────────────────────────────────────────────────────────────┴──────────┴───────────────────────────────┘

  ---
  6. Critical Issues

  P0 — Security (Fix Before Any Public Deployment)

  C1: DEBUG mode bypasses JWT validation (config.py:123–135)
  If DEBUG=true, an empty or placeholder JWT_SECRET_KEY is accepted. An attacker can forge admin tokens with "" as the
  secret. Fix: generate a random ephemeral key in DEBUG mode rather than using empty string.

  C2: No rate limiting on authentication endpoints (auth/router.py)
  POST /auth/login and POST /auth/register have zero rate limiting. Brute-force credential attacks are unrestricted. The
   limiter singleton exists but no @limiter.limit() decorators are applied anywhere.

  C3: HTTPS completely disabled (nginx/nginx.conf:139–202)
  The entire HTTPS server block and HTTP→HTTPS redirect are commented out. Production traffic is in cleartext — JWT
  tokens, passwords, and sensitive weather data are exposed.

  P1 — Runtime Crashes

  C4: Admin dashboard crash on load (screens/screens.jsx:75)
  CITIES.length references an undefined global variable. The dashboard DashboardScreen component throws TypeError on
  first render. Fix: replace CITIES with cities prop from useCityList().

  C5: Citizen app sign-out non-functional (citizen-settings.jsx:352)
  The sign-out button renders but has no onClick handler. Users cannot log out of the citizen app. Fix: add onClick={()
  => clearUserState()} handler.

  C6: Token refresh infinite loop (admin_dashboard/api.js:43–49)
  If the /auth/refresh endpoint permanently fails (expired secret key rotation, DB corruption), the admin dashboard
  refresh function has no max-retry counter and will spin indefinitely until the browser tab closes.

  P2 — Data Quality

  C7: OOD detector trained on zero-variance features (city_model_service.py:516–542)
  The OODDetector was fitted on training data where rolling delta features (pressure_delta_3h, rain_rate_1h, etc.) were
  all zero (no real historical data for these). At inference, real non-zero values cause Mahalanobis distance to
  explode, triggering false OOD alerts. The code hard-codes these back to zero as a workaround — meaning dynamic weather
   signals are suppressed.

  C8: Citizen hourly forecast is synthetic (citizen-screens.jsx:199–207)
  The Home screen's hourly strip shows "+2h", "+4h" entries computed from a formula using current rainfall, not from
  real forecast data. The forecast API response is fetched but not used for this component.

  C9: Static alerts always appended to real alerts (citizen-screens.jsx:427–437)
  Two hardcoded alerts ("Elevated flood risk" and "Heavy rain advisory") are unconditionally prepended to the real
  backend alerts, creating confusing duplicates when the backend provides real anomaly data.

  ---
  7. Missing Features

  ┌───────────────────────────────┬─────────────────────────────────────┬───────────────────────────────────────────┐
  │            Feature            │               Status                │                  Impact                   │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Real hourly forecast          │ Mocked in citizen app               │ Users see synthetic +2h data              │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Alert filter functionality    │ Buttons render, no handlers         │ Alerts screen filters non-functional      │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ HTTPS / TLS                   │ Fully commented out in nginx        │ Production-blocking                       │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Rate limiting decorators      │ Limiter configured, never applied   │ Security gap                              │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ CD pipeline                   │ Placeholder echo only in ci.yml     │ No automated deployment                   │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ WebSocket tests               │ None written                        │ Real-time features untested               │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ PostgreSQL in CI tests        │ Tests use SQLite                    │ Postgres-specific bugs undetected         │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Drift monitor dashboard       │ /drift endpoints exist, no frontend │ Drift data inaccessible to operators      │
  │ integration                   │  screen                             │                                           │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Label management UI           │ /api/v2/labels endpoint exists, no  │ Admin cannot view/correct labels          │
  │                               │ screen                              │                                           │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Citizen app logout            │ Sign-out button non-functional      │ Users cannot log out                      │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Security headers middleware   │ Absent                              │ X-Frame-Options, CSP, HSTS missing        │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Multi-worker Redis pub/sub    │ Documented as planned, not          │ Single-worker only for WebSocket fan-out  │
  │                               │ implemented                         │                                           │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Real TCN buffer seeding       │ Cold-start gives tcn_pct=0.0 for 24 │ Risk underestimated at startup            │
  │                               │  steps                              │                                           │
  ├───────────────────────────────┼─────────────────────────────────────┼───────────────────────────────────────────┤
  │ Ground-truth training labels  │ Heuristic 95th-percentile quantile  │ Model learns statistical proxies, not     │
  │                               │ only                                │ real floods                               │
  └───────────────────────────────┴─────────────────────────────────────┴───────────────────────────────────────────┘

  ---
  8. Non-Functional / Broken Code Report

  Dead Files

  File: backend/analytics_aliases.py (root level)
  Issue: Broken import (from app.services.anomaly_service import AnomalyRepository — module doesn't exist at that path).

    Never imported by main.py. Duplicate of app/api/routes/analytics_aliases.py.
  Severity: HIGH — would crash if imported
  ────────────────────────────────────────
  File: backend/ml/models/autoencoder.py
  Issue: Legacy global autoencoder model. Only used by scripts/train.py (legacy global training). Not part of v3.2
    per-city pipeline.
  Severity: LOW — harmless
  ────────────────────────────────────────
  File: backend/utils/preprocessing.py
  Issue: v1 preprocessor, superseded by app/ml/preprocessing_v2.py. Used only by legacy scripts/train.py.
  Severity: LOW — harmless
  ────────────────────────────────────────
  File: backend/utils/visualization.py
  Issue: Training plots utility. Not called by any v3.2 service. Only invoked by scripts/train.py.
  Severity: LOW — harmless
  ────────────────────────────────────────
  File: frontend/web_dashboard/admin_dashboard/screens/dashboard.jsx
  Issue: Old dashboard screen. Overridden by screens/screens.jsx (loaded after it, overrides window.DashboardScreen).
  Severity: LOW — overridden
  ────────────────────────────────────────
  File: frontend/web_dashboard/admin_dashboard/screens/others.jsx
  Issue: Old screens bundle. Overridden by screens/screens.jsx. Functions still exist in window but are replaced.
  Severity: LOW — overridden

  Dead/Unused Code

  Location: admin_dashboard/api.js: getDriftState(), getEvents(), getCityRegistry(), profileDataset()
  Issue: Defined but never called from any screen.
  Severity: LOW
  ────────────────────────────────────────
  Location: app/core/limiter.py + app/main.py:154–155
  Issue: Limiter registered and exception handler added, but zero route decorators (@limiter.limit()) anywhere in
    codebase.
  Severity: HIGH (security)
  ────────────────────────────────────────
  Location: backend/app/db/repositories/training_repo.py
  Issue: TrainingRecord DB model and repo. No v3.2 route writes to it (training now uses ModelRegistry + training_run.py

    models). Repo exists but nothing calls TrainingRepository.create() in v3.2 flow.
  Severity: MEDIUM
  ────────────────────────────────────────
  Location: backend/app/ml/models/attention.py (DELETED)
  Issue: File deleted from disk (listed as D in git status). Previously CityHybridModel imported it. v3.2 replaced with
    TCN. Legacy references ("lstm_attention.keras" path, "ae_lstm_attention" string) remain as safe fallbacks.
  Severity: LOW — handled gracefully
  ────────────────────────────────────────
  Location: citizen-app.jsx: API.health()
  Issue: Defined in api.js but never called in citizen app code. Health check unused.
  Severity: LOW
  ────────────────────────────────────────
  Location: screens.jsx:963: window._setCities = function() {}
  Issue: Empty placeholder function exposed on global window. Never called.
  Severity: LOW

  Broken Runtime Paths

  ┌─────────────────────────────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
  │                Issue                │              File:Line              │              Severity               │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ CITIES.length undefined global      │ screens/screens.jsx:75              │ CRITICAL — crashes component        │
  │ reference                           │                                     │                                     │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Sign-out button has no handler      │ citizen-settings.jsx:352            │ HIGH                                │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Alert filter buttons have no        │ citizen-screens.jsx:444–448         │ MEDIUM                              │
  │ handlers                            │                                     │                                     │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Hourly forecast uses synthetic data │ citizen-screens.jsx:199–207         │ MEDIUM                              │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Static alerts unconditionally       │ citizen-screens.jsx:427–437         │ MEDIUM                              │
  │ prepended                           │                                     │                                     │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Token refresh no max-retry counter  │ admin_dashboard/api.js:43–49        │ MEDIUM                              │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ CITY_METADATA only has 6 cities (vs │                                     │ MEDIUM — 4 cities (Faisalabad,      │
  │  10 documented in CLAUDE.md)        │ city_model_service.py:49–56         │ Multan, Hyderabad, Gilgit) have no  │
  │                                     │                                     │ metadata                            │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Route collision                     │ risk_analytics.py:104 +             │ MEDIUM                              │
  │ /database/statistics                │ analytics_aliases.py:49             │                                     │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ CI test uses SQLite → misses        │ ci.yml:62                           │ HIGH                                │
  │ PostgreSQL bugs                     │                                     │                                     │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ HTTPS entirely disabled             │ nginx/nginx.conf:139–202            │ CRITICAL (production)               │
  ├─────────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Deploy step is placeholder echo     │ ci.yml:158–159                      │ CRITICAL (production)               │
  └─────────────────────────────────────┴─────────────────────────────────────┴─────────────────────────────────────┘

  ---
  9. Production Readiness Score

  Overall Score: 6.5 / 10

  ┌───────────────────┬────────┬────────────────────────────────────────────────────────────────────────────────────┐
  │     Dimension     │ Score  │                                   Justification                                    │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Functional        │ 7.5/10 │ Core ML pipeline works end-to-end; most API routes functional; v2 inference chain  │
  │ Correctness       │        │ complete. Minus: mocked forecast, broken admin screen, non-functional buttons      │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Security          │ 4/10   │ Solid JWT design, bcrypt, token reuse detection. Critical gaps: no rate limiting,  │
  │                   │        │ DEBUG bypass, HTTP-only (no HTTPS), session storage tokens                         │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │                   │        │ Correct architecture (AE+TCN+Fusion), causal design, ECDF calibration. Gaps:       │
  │ ML Quality        │ 6.5/10 │ heuristic labels not ground truth, OOD detector workaround suppresses real         │
  │                   │        │ signals, cold-start TCN zeros                                                      │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Test Coverage     │ 4/10   │ 32 test methods but all shallow; SQLite only; no WS tests; no business logic       │
  │                   │        │ validation; auth fixture fragile                                                   │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Infrastructure    │ 6/10   │ Docker compose correct; resource limits set; healthchecks configured. Gaps: HTTPS  │
  │                   │        │ off, CD placeholder, TensorFlow startup > healthcheck window                       │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Code Quality      │ 7.5/10 │ Clean repository pattern, DI, lifespan management, async-safe WS, dynamic city     │
  │                   │        │ discovery. Gaps: dead files, route collision, outdated CLAUDE.md                   │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Observability     │ 5.5/10 │ Rotating file logs configured, drift PSI exposed in /health. Gaps: no structured   │
  │                   │        │ JSON logs, no monitoring stack, no alerting                                        │
  ├───────────────────┼────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Frontend          │ 6.5/10 │ Dual SPA with good API client design, v1+v2 response normalization, graceful       │
  │                   │        │ degradation. Gaps: mocked data, broken buttons, session storage auth               │
  └───────────────────┴────────┴────────────────────────────────────────────────────────────────────────────────────┘

  What Must Be Fixed Before Public/Production Deployment

    | Priority |                      Fix                      | Estimated Effort |
    |----|--------------------------------------------------------------|---------|
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
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Functional            │ 7.5/10 │ Core ML pipeline works end-to-end; most API routes functional; v2 inference chain complete. Minus: mocked forecast, broken admin screen, non-functional buttons         │
  │ Correctness           │        │                                                                                                                                                                         │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Security              │ 4/10   │ Solid JWT design, bcrypt, token reuse detection. Critical gaps: no rate limiting, DEBUG bypass, HTTP-only (no HTTPS), session storage tokens                            │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ML Quality            │ 6.5/10 │ Correct architecture (AE+TCN+Fusion), causal design, ECDF calibration. Gaps: heuristic labels not ground truth, OOD detector workaround suppresses real signals,        │
  │                       │        │ cold-start TCN zeros                                                                                                                                                    │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Test Coverage         │ 4/10   │ 32 test methods but all shallow; SQLite only; no WS tests; no business logic validation; auth fixture fragile                                                           │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Infrastructure        │ 6/10   │ Docker compose correct; resource limits set; healthchecks configured. Gaps: HTTPS off, CD placeholder, TensorFlow startup > healthcheck window                          │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Code Quality          │ 7.5/10 │ Clean repository pattern, DI, lifespan management, async-safe WS, dynamic city discovery. Gaps: dead files, route collision, outdated CLAUDE.md                         │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Observability         │ 5.5/10 │ Rotating file logs configured, drift PSI exposed in /health. Gaps: no structured JSON logs, no monitoring stack, no alerting                                            │
  ├───────────────────────┼────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Frontend              │ 6.5/10 │ Dual SPA with good API client design, v1+v2 response normalization, graceful degradation. Gaps: mocked data, broken buttons, session storage auth                       │
  └───────────────────────┴────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  What Must Be Fixed Before Public/Production Deployment

  1. Enable HTTPS (uncomment nginx block, add Let's Encrypt or self-signed cert) — 2 hours
  2. Add @limiter.limit("5/minute") to POST /auth/login and POST /auth/register — 30 minutes
  3. Fix DEBUG mode JWT bypass in config.py:134 — generate ephemeral random key in dev, never empty — 1 hour
  4. Fix CITIES → cities in screens/screens.jsx:75 — 5 minutes
  5. Add onClick handler to citizen sign-out button — 10 minutes
  6. Implement CD in ci.yml (Docker Hub push or SSH deploy) — 4 hours
  7. Switch CI tests to PostgreSQL (add service block in ci.yml) — 2 hours
  8. Add max-retry to token refresh in api.js — 30 minutes

  What Is Solid and Deployment-Ready

  - JWT auth system (rotation, reuse detection, bcrypt, HS256)
  - Database session management (no leaks, proper repository pattern)
  - WebSocket connection management (async-safe, per-channel, prune-on-disconnect)
  - City model dynamic discovery and thread-safe lazy loading
  - Docker compose stack (postgres + redis + api + nginx + backup sidecar)
  - AE+TCN+Fusion inference pipeline architecture (causal, no leakage, ECDF calibration)
  - Graceful degradation (heuristic fallback when model missing, Promise.allSettled in frontend)
  - CORS configuration (correctly rejects credentials with wildcard origin)
  - Global exception handling (no stack traces leaked to clients)
  - Atomic model saves (tmp → swap)

  ---
  This report was generated from direct code inspection of all 95 Python source files, 7 JSX/JS files, all infrastructure YAML/configuration files, and the test suite. All findings reference actual line
  numbers and function signatures observed in the codebase.

Next Response
  Final Deliverable: Production Readiness Report

  ---
  A. What Was Changed (All 5 Phases)

  PHASE 1 — Security (P0) ✓

  ┌────────────────────────┬──────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │          Fix           │                   File                   │                           Change                                                                │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ JWT DEBUG bypass       │ app/core/config.py:120–135               │ Removed the if not debug_mode branch. System now exits on missing/placeholder JWT_SECRET_KEY regardless of DEBUG=true. Provides a    │
  │ eliminated             │                                          │ one-liner quick-fix command in the exit message.                                                                                     │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ JWT read-at-call-time  │ app/core/security.py                     │ Changed from from app.core.config import JWT_SECRET_KEY (value at import) to from app.core import config as _cfg (module reference). │
  │                        │                                          │  All create_*_token() and decode_token() now read _cfg.JWT_SECRET_KEY at call time — future runtime patches propagate correctly.     │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Rate limiting on auth  │ app/auth/router.py                       │ Added @limiter.limit() to all three endpoints: register 5/min, login 10/min, refresh 20/min. Added request: Request parameter as     │
  │                        │                                          │ required by slowapi.                                                                                                                 │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Rate limiting on city  │ app/api/routes/city_predictions.py       │ Added @limiter.limit("30/minute") to POST /cities/{city}/predict and POST /api/v2/cities/{slug}/predict.                             │
  │ predict                │                                          │                                                                                                                                      │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ HTTPS enabled in nginx │ nginx/nginx.conf                         │ HTTP→HTTPS redirect uncommented. Full HTTPS server block with TLSv1.2/1.3, HSTS, CSP, X-Frame-Options activated. ACME challenge path │
  │                        │                                          │  added for Let's Encrypt renewals.                                                                                                   │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ TLS cert               │ nginx/certs/.gitkeep,                    │ Created cert directory for volume mount. Added self-signed cert generation script for local dev.                                     │
  │ infrastructure         │ nginx/generate_dev_cert.sh               │                                                                                                                                      │
  ├────────────────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ SPA routing fixed      │ nginx/nginx.conf                         │ Changed ^/(frontend|dashboard)$ to ^/(frontend|dashboard)(/.*)?$ — sub-paths now route correctly.                                    │
  └────────────────────────┴──────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

  PHASE 2 — Runtime Stability (P1) ✓

  ┌───────────────────────┬──────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │          Fix          │                 File                 │                                                                  Change                                                                   │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Route collision       │ app/api/routes/risk_analytics.py:104 │ Removed duplicate GET /database/statistics handler. Added comment pointing to authoritative implementation in analytics_aliases.py.       │
  │ resolved              │                                      │                                                                                                                                           │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ DB session rollback   │ app/db/database.py:154–160           │ Added except Exception: db.rollback(); raise block to get_db(). Prevents partial-commit state corruption on exception.                    │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Security headers      │ app/main.py                          │ Added _SecurityHeadersMiddleware (BaseHTTPMiddleware) that injects X-Content-Type-Options, X-Frame-Options, X-XSS-Protection,             │
  │ middleware            │                                      │ Referrer-Policy, and Strict-Transport-Security (HTTPS only) on every response.                                                            │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Admin dashboard crash │ screens/screens.jsx:75               │ Replaced CITIES.length (undefined global) with CITIES_FALLBACK.length (defined at line 15 of same file).                                  │
  │  fixed                │                                      │                                                                                                                                           │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Citizen sign-out      │ citizen-settings.jsx:352             │ Added onClick handler that clears all four hg-* localStorage keys and reloads the page.                                                   │
  │ functional            │                                      │                                                                                                                                           │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Token refresh loop    │ admin_dashboard/api.js:33            │ Added _refreshFailCount counter and REFRESH_MAX_FAILURES = 3 guard. After 3 consecutive refresh failures: clears tokens, dispatches       │
  │ fixed                 │                                      │ hg:unauthorized, throws error. Resets to 0 on success.                                                                                    │
  ├───────────────────────┼──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Model description     │ screens/screens.jsx:84               │ Fixed subtitle from "Autoencoder + LSTM + Attention" to "Autoencoder + TCN + LightGBM Fusion" — matches actual v3.2 architecture.         │
  │ corrected             │                                      │                                                                                                                                           │
  └───────────────────────┴──────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  PHASE 3 — Data & Logic Consistency (P2) ✓

  ┌───────────────────────┬─────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │          Fix          │            File             │                                                                       Change                                                                       │
  ├───────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ v3.2 risk band        │ citizen-screens.jsx:39–46   │ riskToScenario() now handles "severe" → "crit" and "moderate"/"elevated" → "warn". Previously "Moderate" from v3.2 fell through to "safe" — risk   │
  │ mapping               │                             │ was silently underreported.                                                                                                                        │
  ├───────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Real forecast in      │ citizen-screens.jsx:196–215 │ Home screen now uses forecast.forecast array (from getForecast() API call) when ≥2 days available, showing day-name labels. Falls back to          │
  │ hourly strip          │                             │ prcp-derived estimates labelled "Est." when forecast unavailable. Eliminates synthetic hardcoded "+2h/+4h" mocked data.                            │
  ├───────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Static alerts no      │ citizen-screens.jsx:456     │ displayAlerts = liveAlerts.length > 0 ? liveAlerts : staticAlerts. Static contextual alerts are now fallback-only — they disappear when the        │
  │ longer pollute        │                             │ backend provides real anomaly data.                                                                                                                │
  ├───────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Alert filters         │ citizen-screens.jsx         │ Added const [filter, setFilter] = useState("all"). Each alert object now has a scope field ("area" or "national"). Filter pills have onClick(() => │
  │ functional            │                             │  setFilter(...)). Empty-filter state shows a message. Active filter pill is visually highlighted.                                                  │
  └───────────────────────┴─────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  PHASE 4 — Infrastructure Hardening (P3) ✓

  ┌───────────────────┬──────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │        Fix        │           File           │                                                                          Change                                                                           │
  ├───────────────────┼──────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ CI tests use      │ .github/workflows/ci.yml │ Added services.postgres (postgres:16-alpine) with health check. Changed DATABASE_URL from sqlite:///test.db to                                            │
  │ PostgreSQL        │                          │ postgresql://hydroguard:ci_test_password@localhost:5432/hydroguard_test. PostgreSQL-specific bugs now caught in CI.                                       │
  ├───────────────────┼──────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Smoke test waits  │ .github/workflows/ci.yml │ Replaced sleep 10 with a 12-iteration polling loop (sleep 5 × 12 = 60 s max). Tests both /health and /api/v2/cities to verify full startup (DB + ML model │
  │ correctly         │                          │  registry). JWT_SECRET_KEY now injected into smoke test container.                                                                                        │
  ├───────────────────┼──────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ mypy extended     │ .github/workflows/ci.yml │ Expanded from 2 files to 4: config.py, security.py, schemas/__init__.py, db/database.py.                                                                  │
  │ coverage          │                          │                                                                                                                                                           │
  ├───────────────────┼──────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ CD pipeline       │ .github/workflows/ci.yml │ Replaced placeholder echo with: (1) publish job that builds and pushes to Docker Hub with both latest and sha tags; (2) deploy job using                  │
  │ implemented       │                          │ appleboy/ssh-action to SSH into VPS, pull updated image, and restart compose stack. Clear comment documents required secrets.                             │
  └───────────────────┴──────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  PHASE 5 — Cleanup ✓

  ┌────────────────┬──────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │      Fix       │               File               │                                                                        Change                                                                        │
  ├────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Dead file      │ backend/analytics_aliases.py     │ File removed. Had broken import (from app.services.anomaly_service import AnomalyRepository), was never imported by main.py, and duplicated          │
  │ deleted        │ (root)                           │ app/api/routes/analytics_aliases.py.                                                                                                                 │
  ├────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ CLAUDE.md      │ CLAUDE.md                        │ Version bumped v3.1→v3.2, model architecture corrected (LSTM+Attention→TCN+Fusion), city count corrected (fixed 10→dynamic discovery), mypy targets  │
  │ updated        │                                  │ updated, train command flag --no-lstm→--no-tcn corrected.                                                                                            │
  └────────────────┴──────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  B. Risk Summary After Fixes

  Resolved Risks

  - JWT secret bypass via DEBUG mode — eliminated
  - Brute-force attacks on login/register — mitigated (rate limited at both nginx and FastAPI layers)
  - Plaintext HTTP in production — eliminated (HTTPS enforced, HTTP redirects)
  - Admin dashboard crash on load — fixed
  - Citizen sign-out non-functional — fixed
  - Token refresh infinite loop — fixed (max 3 failures)
  - Route collision /database/statistics — fixed
  - DB session data corruption risk — fixed (explicit rollback)
  - v3.2 "Moderate" risk band silently mapped to "safe" — fixed
  - Mocked hourly forecast shown as real data — fixed
  - CI tests using SQLite instead of PostgreSQL — fixed
  - No CD pipeline — implemented
  - Dead file with broken import — removed
  - Security headers absent — added (both nginx and FastAPI middleware)
  - SPA sub-path routing broken in nginx — fixed

  Remaining Risks (Require Ops Action, Not Code Changes)

  ┌──────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────┬───────────────────────────────────────────────────────┐
  │                   Risk                   │                                            Action Required                                            │                       Severity                        │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ No TLS certs in nginx/certs/             │ Run bash nginx/generate_dev_cert.sh for dev; use Let's Encrypt for prod                               │ CRITICAL if deploying publicly                        │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ GitHub Secrets not set                   │ Add DOCKERHUB_USERNAME, DOCKERHUB_TOKEN, VPS_HOST, VPS_USER, VPS_SSH_KEY, JWT_SECRET_KEY in GitHub    │ CRITICAL for CD to work                               │
  │                                          │ repository settings                                                                                   │                                                       │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ OOD detector trained on zero-variance    │ Retrain all city models after FeaturePipelineV2 is producing real rolling deltas                      │ HIGH — ML signal quality                              │
  │ features                                 │                                                                                                       │                                                       │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ TCN 24-step cold-start zeros             │ Seed _CityBuffer from historical CSV rows on startup                                                  │ MEDIUM — risk underestimated for first 24 predictions │
  │                                          │                                                                                                       │  per city                                             │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ Weak labels are heuristic                │ Incorporate ground-truth flood event labels from PMD/NDMA records                                     │ MEDIUM — long-term ML quality                         │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ WebSocket token in query string          │ Architecture limitation (browsers cannot send WS headers); document in security policy                │ LOW — acceptable trade-off                            │
  ├──────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ Single-worker WebSocket fan-out          │ Redis pub/sub bridge needed if scaling to >1 uvicorn worker                                           │ LOW — current single-worker is fine                   │
  └──────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────┘

  ---
  C. Deployment Verdict

  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │   READY FOR PRODUCTION WITH MONITORING REQUIRED             │
  │                                                             │
  │   Prerequisites before going live:                          │
  │   1. Place TLS certs in nginx/certs/ (or run               │
  │      generate_dev_cert.sh for staging)                      │
  │   2. Set all GitHub Secrets for CD to function             │
  │   3. Set JWT_SECRET_KEY (≥64 chars) in .env                │
  │   4. Retrain city models to resolve OOD detector issue     │
  │                                                             │
  │   Score before fixes:  6.5 / 10                            │
  │   Score after fixes:   8.2 / 10                            │
  │                                                             │
  │   Remaining gap is operational (certs, secrets, retraining)│
  │   not code — no further blocking code issues exist.         │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘

  Post-deployment monitoring checklist:
  - Rate limit 429 responses on /auth/login — alert if >50/hour (brute force indicator)
  - /health endpoint — alert if drift_status flips to CRITICAL
  - /api/v2/cities/{slug}/status — alert if has_model: false for a trained city (model file corruption)
  - Docker log stream — watch for JWT_SECRET_KEY warnings (would indicate env misconfiguration)
  - Nginx access log — watch for 499 (client disconnects, often TLS cert issues)