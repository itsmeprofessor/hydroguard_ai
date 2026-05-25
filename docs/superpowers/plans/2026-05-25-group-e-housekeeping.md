# Group E — Housekeeping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring CLAUDE.md into alignment with the actual v3.2+ codebase (architecture section still describes v3.1), add inline comments to nginx.conf where context is missing, and remove all stale references to decommissioned features.

**Architecture:** Three sequential documentation tasks — all changes are find/replace edits to two files (`CLAUDE.md` and `nginx/nginx.conf`). No source code changes. No tests in the traditional sense; verification is by grep.

**Tech Stack:** Text editor, grep.

---

## File Map

| File | Change |
|---|---|
| `CLAUDE.md` | Architecture section rewrite (Tasks 1 + 2) |
| `nginx/nginx.conf` | Inline comment additions (Task 3) |

---

### Task 1: CLAUDE.md — Architecture section (lifespan, models, anomaly_service, BahdanauAttention, preprocessing)

**Files:**
- Modify: `CLAUDE.md:87-198`

---

- [ ] **Step 1: Fix App lifespan item 2 (line 89)**

Find this exact text in `CLAUDE.md`:
```
2. Verifies `anomaly_service.get_model_info()` and logs model type/version.
```

Replace with:
```
2. Calls `city_model_service.refresh_registry()` — scans the master CSV + `saved_models/city_models/` to build `CITY_REGISTRY`. Then `warm_up_tcn_buffers()` seeds each city's TCN rolling window (seq_len=30) from the most-recent rows of the master CSV.
```

---

- [ ] **Step 2: Fix request flow (line 95)**

Find:
```
**Request flow:** Router → `Depends(get_current_user|require_role|require_admin)` → service layer (`anomaly_service`) → Repository (DB) → `broadcast_service.emit_*` → ConnectionManager → all sockets in channel.
```

Replace with:
```
**Request flow:** Router → `Depends(get_current_user|require_role|require_admin)` → service layer (`city_model_service.predict_v2()` for city predictions; `anomaly_service` was decommissioned in v3.2) → Repository (DB) → `broadcast_service.emit_*` → ConnectionManager → all sockets in channel.
```

---

- [ ] **Step 3: Fix City-specific hybrid models section heading + goal (line 142-144)**

Find:
```
#### City-specific hybrid models (v3.1) (`app/ml/models/`, `app/services/city_model_service.py`)

**Goal**: per-city models capture each city's unique seasonal patterns, monsoon profiles, and topographic vulnerabilities. The global `anomaly_service` remains as a fallback for cities without trained models.
```

Replace with:
```
#### City-specific hybrid models (v3.2+) (`app/ml/models/`, `app/services/city_model_service.py`)

**Goal**: per-city models capture each city's unique seasonal patterns, monsoon profiles, and topographic vulnerabilities. `anomaly_service` was decommissioned in v3.2; the fallback for untrained cities is a rule-based heuristic in `city_model_service._build_degraded_response()`.
```

---

- [ ] **Step 4: Rewrite architecture block (lines 146-151) — Autoencoder through output dict**

Find:
```
**Architecture (one model per city)** in `app/ml/models/city_hybrid.py`:
- **Autoencoder**: Dense `[64, 32, 16]` → latent **8** → mirrored decoder → `linear` reconstruction. Dropout 0.20.
- **LSTM + Attention**: `LSTM(64, return_sequences=True)` → **`BahdanauAttention(units=32)`** (additive, causal — `app/ml/models/attention.py`) → `LSTM(32)` → `Dense(16)` → `Dense(1, sigmoid)`. Sequence length = 7.
- **NO BiLSTM** — strictly causal forward LSTM, suitable for real-time forecasting.
- **Hybrid score**: `0.55 × ae_score + 0.45 × lstm_score`, both normalised to `[0, 1]`.
- **Standardised output dict** (always returned): `{ risk_level: "Low"|"Medium"|"High", anomaly_score, confidence, is_anomaly, ae_score, lstm_score, hri_score (0–100) }`.
```

Replace with:
```
**Architecture (one model per city)** in `app/ml/models/city_hybrid.py`:
- **Autoencoder**: Dense `[64, 32, 16]` → latent **8** → mirrored decoder → `linear`. Dropout 0.20. Physics-weighted MSE loss (prcp 3×, pressure 2.5×, humidity 2×). Trained on fair-weather rows only. Score: `ECDFScaler(ae_error) → ae_percentile ∈ [0, 1]`.
- **TCN**: `CausalTCN(filters=128, kernel=3, dilations=[1,2,4,8,16,32], seq_len=30)`. Receptive field = 127 observations (~4 months). Trained as next-step reconstructor on full training set. Score: `ECDFScaler(tcn_error) → tcn_percentile ∈ [0, 1]`.
- **NO LSTM. NO BahdanauAttention. NO BiTCN.** Strictly causal.
- **Fusion**: `ae_percentile` + `tcn_percentile` + derived features → `FusionModel` (LightGBM) → raw `P(event)` → `IsotonicCalibrator` → `event_probability`.
- **Uncertainty**: Monte Carlo Dropout — N stochastic forward passes at inference. Outputs `epistemic_uncertainty` (weighted AE + TCN variance blend), `model_entropy`, `prediction_stability` (`stable|warming_up|degraded`).
- **OOD detection**: `OODDetector` (`ood_detector.pkl`) uses Mahalanobis distance. OOD is **non-blocking** — sets elevated uncertainty but does not stop inference.
- **Standardised output dict** (v3.2+): `{ inference_id, event_probability, confidence_interval, uncertainty, model_entropy, risk_band, hri_score, is_alert, alert_tier, component_scores: {ae_percentile, tcn_percentile, p_event_raw, ae_variance, tcn_variance}, drivers, sequence_context, inference_mode, epistemic_uncertainty, prediction_stability, degraded_reason }`.
```

---

- [ ] **Step 5: Rewrite CityModelService description (lines 153-158)**

Find:
```
**`CityModelService` singleton** in `app/services/city_model_service.py`:
- `CITY_REGISTRY` — canonical slug → name / province / population / lat-lon / regional vulnerability for all 10 cities.
- Lazy-loads each city's saved model on first access; per-city `RLock` makes loading thread-safe.
- Per-city LSTM rolling buffer (`_CityBuffer`, length 7) — model emits AE-only score until the buffer fills.
- `predict(city, features, preprocessor)` is the single entry point. Falls back to a **rule-based heuristic** (`prcp/humidity/pressure` weighted score × city vulnerability) when no model exists, returning the same standardised dict with `source="heuristic"`.
- In-memory **alert log** per city (last 20 anomalies) accessed via `get_recent_alerts()`.
```

Replace with:
```
**`CityModelService` singleton** in `app/services/city_model_service.py`:
- `CITY_METADATA` / `CITY_REGISTRY` — canonical slug → name / province / population / lat-lon / vulnerability. Populated by `refresh_registry()` on startup; rescanned on `POST /cities/refresh`.
- Lazy-loads each city's model set on first access; per-city `RLock` keeps loading thread-safe.
- Per-city TCN rolling buffer (`_CityBuffer`, length=`TCN_SEQ_LEN`=30) — TCN branch activates only after the buffer fills; before that, AE branch only.
- `predict_v2(city_slug, raw_weather)` is the primary async entry point. Falls back to `_build_degraded_response()` (rule-based heuristic, `source="heuristic"`) when no model is loaded.
- In-memory **alert log** per city (last 20 alerts) via `get_recent_alerts()`.
```

---

- [ ] **Step 6: Rewrite saved-model layout (lines 160-168)**

Find:
```
**Saved-model layout**:
```
backend/saved_models/city_models/
└── <slug>/
    ├── autoencoder/         # Keras SavedModel
    ├── lstm_attention/      # Keras SavedModel (optional — skipped if <100 sequences)
    ├── ae_calibration.npy   # [mean, std, p99] from training reconstruction errors
    └── preprocessor.joblib  # WeatherDataPreprocessor fitted on this city's data
```
```

Replace with:
```
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
    ├── cal_data.npz             # Held-out calibration arrays (for audit scripts)
    └── training_metrics.json    # Training provenance + evaluation metrics
```
```

---

- [ ] **Step 7: Rewrite training pipeline description (lines 170-175)**

Find:
```
**Training** (`scripts/train_city.py`): args `--city <name>` or `--all`; `--data`, `--epochs`, `--batch-size`, `--no-lstm`, `--seed`, `--min-records`. Per-city training pipeline:
1. Filter master CSV to one city (`city` column).
2. Fit `WeatherDataPreprocessor` on that city's data.
3. Split (no leakage), train AE first, calibrate `[mean, std, p99]` on AE errors.
4. If ≥100 sequences, train LSTM+Attention on overlapping length-7 windows.
5. Save → registry hot-swap via `city_model_service.register_model(slug, model)`.
```

Replace with:
```
**Training** (`scripts/train_city.py`): args `--city <name>` or `--all`; `--data`, `--epochs`, `--batch-size`, `--no-tcn`, `--seed`, `--min-records`, `--force`. Per-city training pipeline:
1. Filter master CSV to one city (`city` column). For Karachi: compute 9 coastal features.
2. Fit `WeatherDataPreprocessorV2` on the training split (no leakage).
3. 4-way split (train / cal / test / implicit holdout). Train AE on fair-weather rows; fit `ECDFScaler` on AE errors.
4. If ≥30 sequences, train TCN reconstructor; fit `ECDFScaler` on TCN errors.
5. Train `FusionModel` (LightGBM) on cal split branch outputs. Fit `IsotonicCalibrator`.
6. Train `OODDetector` on training features (Mahalanobis covariance).
7. Save all artifacts → `city_model_service.register_model(slug, ...)` hot-swap (only if `input_dim` unchanged; dimension change requires container restart).
```

---

- [ ] **Step 8: Remove the Bahdanau Attention section (lines 177-180)**

Find and delete this entire block:
```

**Bahdanau Attention layer** (`app/ml/models/attention.py`):
- Score: `e_t = V · tanh(W·h_t + U·s)`, weights `softmax(e_t)`, context `Σ aₜ · hₜ`.
- Optional `mask` argument for padding handling.
- `get_config` / `from_config` implemented — Keras-loadable via `custom_objects={"BahdanauAttention": BahdanauAttention}`.
```

(Replace with empty string — just delete it.)

---

- [ ] **Step 9: Remove the Anomaly detection section (lines 182-193)**

Find and delete this entire block:
```
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
```

(Replace with empty string — just delete it.)

---

- [ ] **Step 10: Update ML & preprocessing heading (line 195)**

Find:
```
#### ML & preprocessing (`app/ml/`, `utils/preprocessing.py`)
```

Replace with:
```
#### ML & preprocessing (`app/ml/`, `app/ml/preprocessing_v2.py`)
```

---

- [ ] **Step 11: Update preprocessing bullet point (lines 197-198)**

Find:
```
- **Feature groups** (`ModelConfig`): primary (`prcp`, `humidity`, `pressure`, `cloud_cover` — heavily weighted), secondary (`dew_point`, `wspd`), context (`tmin`, `tmax`, `tavg`, `temp_range` — barely weighted to suppress diurnal noise). Numerical → median imputation → weight × StandardScaler. Temporal → MinMax. Categorical → one-hot, **unseen categories produce all-zero rows** rather than failing.
- **Drift detection** (`app/ml/drift/detector.py`): PSI on `[prcp, humidity, pressure, cloud_cover]`. WARN at 0.10, CRIT at 0.20. Surfaced via `/health`.
```

Replace with:
```
- **`WeatherDataPreprocessorV2`** (`app/ml/preprocessing_v2.py`): 28 base numerical features (`NUMERICAL_V2`) + 9 Karachi-specific coastal features (auto-excluded for other cities via `num_present` filter) + 4 temporal + 2 OHE categorical. Fit on training split only; `input_dim` property returns the actual fitted dimension. `utils/preprocessing.py` (v1, `WeatherDataPreprocessor`) is still used by the legacy global-model scripts (`scripts/train.py`, `scripts/evaluate.py`) — it is NOT used by v3.2 inference.
- **Drift detection** (`app/ml/drift/detector.py`): PSI on `[prcp, humidity, pressure, cloud_cover]`. WARN at 0.10, CRIT at 0.20. Surfaced via `/health`.
```

---

- [ ] **Step 12: Verify removals with grep**

Run:
```
python -m pytest --collect-only -q 2>nul || true
grep -n "anomaly_service\|BahdanauAttention\|lstm_attention\|0\.55.*ae\|LSTM + Attention\|lstm_score\|is_anomaly.*confidence" CLAUDE.md
```

Expected: zero matches (or only matches inside code blocks that are intentional — e.g., a `# legacy` comment).

---

- [ ] **Step 13: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: rewrite CLAUDE.md Architecture section for v3.2+ (TCN, FusionModel, remove anomaly_service + BahdanauAttention)"
```

---

### Task 2: CLAUDE.md — Infrastructure + Key Constraints

**Files:**
- Modify: `CLAUDE.md:328-383`

---

- [ ] **Step 1: Fix docker-compose nginx mount (line 328)**

Find:
```
- **`nginx:alpine`** — mounts `./nginx/nginx.conf` (ro), `./nginx/certs` (ro), and `./frontend/web_dashboard/admin_dashboard` → `/usr/share/nginx/html`. Ports `80:80`, `443:443`.
```

Replace with:
```
- **`nginx:alpine`** — mounts `./nginx/nginx.conf` (ro), `./nginx/certs` (ro), and `./frontend/citizen_flutter_app/build/web` → `/usr/share/nginx/html` (compiled Flutter web app). Ports `80:80`, `443:443`.
```

---

- [ ] **Step 2: Expand nginx.conf paragraph (lines 330-332)**

Find:
```
### `nginx/nginx.conf`

Upstream `hydroguard_api` → `hydroguard-api:8000`. WebSocket upgrade at `/ws/*` (`Upgrade`/`Connection` headers, 86400 s timeouts). Regex match for API paths (`/predict`, `/anomalies`, `/analytics`, `/risk-map`, `/train`, `/health`, `/auth`, `/model`, `/docs`, `/redoc`, `/openapi.json`). All other paths → static SPA with `try_files $uri $uri/ /index.html`. HTTPS server block present but cert paths commented.
```

Replace with:
```
### `nginx/nginx.conf`

Upstream `hydroguard_api` → `hydroguard-api:8000`. WebSocket upgrade at `/ws/*` (`Upgrade`/`Connection` headers, 86400 s keep-alive). Regex match for API paths (`/anomalies`, `/analytics`, `/risk-map`, `/train`, `/health`, `/auth`, `/model`, `/docs`, `/redoc`, `/openapi.json`, `/cities`, `/weather`, `/drift`, `/database`, `/api`). All other paths → Flutter SPA with `try_files $uri $uri/ /index.html`.

**Rate limits (per source IP):**
- `auth/(login|register)`: 5 req/min, burst=3 — brute-force protection
- `api/v2/cities/*/predict` + `/predict`: 60 req/min, burst=10
- All other API routes: 200 req/min, burst=50

**Frontend served:** `citizen_flutter_app/build/web` (compiled Flutter). The React `citizen_app` is served by FastAPI at `/citizen`, not by nginx.

**HTTPS:** Self-signed certs for local dev — `openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem -subj "/CN=localhost"`. Production: use Certbot. Certs mounted `:ro`; to renew, update host files and `docker compose restart nginx`.
```

---

- [ ] **Step 3: Fix Key Constraints — ML architecture bullet (line 364)**

Find:
```
- **ML architecture is fixed**: Autoencoder + LSTM + **Bahdanau Attention** per-city hybrid. **No BiLSTM**: the system must remain causal so the LSTM can be used for real-time forecasting. The global `anomaly_service` (legacy AE+LSTM hybrid, no attention) is kept only as a fallback.
```

Replace with:
```
- **ML architecture is fixed**: Autoencoder + **TCN** + **LightGBM FusionModel** + **IsotonicCalibrator** per-city. No BiTCN, no LSTM, no BahdanauAttention — strictly causal. MC Dropout provides epistemic uncertainty. `anomaly_service` is decommissioned; the fallback for untrained cities is the rule-based heuristic in `city_model_service`.
```

---

- [ ] **Step 4: Fix Key Constraints — city model description bullet (line 365)**

Find:
```
- **City-specific models are required**: each of the 10 cities trains its own AE+LSTM+Attention model. `CityModelService` lazy-loads them; missing models route through a heuristic. Don't replace the per-city design with a single global model.
```

Replace with:
```
- **City-specific models are required**: each city trains its own AE+TCN+FusionModel set (`scripts/train_city.py`). `CityModelService` lazy-loads them; missing models route through the rule-based heuristic. Don't replace the per-city design with a single global model.
```

---

- [ ] **Step 5: Fix Key Constraints — output signature bullet (line 366)**

Find:
```
- **Standardised output dict**: every prediction returns `{ risk_level, anomaly_score, confidence, is_anomaly, ae_score, lstm_score, hri_score }`. Risk levels are `Low | Medium | High` (no `Critical` — that maps to `High` in v3.1). The backend translates this to scenario `safe | warn | crit` via `_risk_to_scenario` in `app/api/routes/city_predictions.py`.
```

Replace with:
```
- **Standardised output dict**: v2 predictions return `{ inference_id, event_probability, confidence_interval, uncertainty, risk_band, hri_score, is_alert, alert_tier, component_scores, drivers, sequence_context, inference_mode, epistemic_uncertainty, prediction_stability, degraded_reason }`. The v1 `/cities/{city}/forecast` translates `risk_band` to scenario `safe | warn | crit` via `_risk_to_scenario`.
```

---

- [ ] **Step 6: Remove BahdanauAttention custom_objects bullet (line 382)**

Find:
```
- **Bahdanau Attention is custom** — when loading saved LSTM models, always pass `custom_objects={"BahdanauAttention": BahdanauAttention}` to `keras.models.load_model`. `CityHybridModel.load()` already does this.
```

Replace with:
```
- **TCN is custom** — `app/ml/models/tcn.py` implements `CausalTCN`. When loading TCN models, `CityHybridModel.load()` handles all custom object registration automatically.
```

---

- [ ] **Step 7: Verify no stale references remain**

Run:
```
grep -n "BahdanauAttention\|anomaly_service\|lstm_score\|AE+LSTM" CLAUDE.md
```

Expected: zero matches.

---

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: fix CLAUDE.md Infrastructure + Key Constraints for v3.2+ (nginx frontend, rate limits, TCN constraints)"
```

---

### Task 3: nginx/nginx.conf inline comments

**Files:**
- Modify: `nginx/nginx.conf:27-29` (rate limit zone block)
- Modify: `nginx/nginx.conf:63-64` (WebSocket timeout)
- Modify: `nginx/nginx.conf:98` (REST proxy timeout)
- Modify: `nginx/nginx.conf:116-117` (HTTPS cert lines)

---

- [ ] **Step 1: Add per-IP NAT caveat after rate-limit zone definitions**

Find in `nginx/nginx.conf`:
```
    # ── Rate limiting zones ───────────────────────────────────
    limit_req_zone $binary_remote_addr zone=auth_zone:10m    rate=5r/m;
    limit_req_zone $binary_remote_addr zone=predict_zone:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=api_zone:10m     rate=200r/m;
```

Replace with:
```
    # ── Rate limiting zones ───────────────────────────────────
    # All zones key on $binary_remote_addr (source IP).
    # Clients behind shared NAT (office/university) share the same quota.
    limit_req_zone $binary_remote_addr zone=auth_zone:10m    rate=5r/m;
    limit_req_zone $binary_remote_addr zone=predict_zone:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=api_zone:10m     rate=200r/m;
```

---

- [ ] **Step 2: Explain WebSocket 86400s timeout (HTTP server)**

Find in `nginx/nginx.conf` (inside the HTTP server block):
```
            proxy_read_timeout 86400s;
            proxy_send_timeout 86400s;
        }

        # Auth endpoints — strict brute-force protection
```

Replace with:
```
            # 86400 s = 24 h: WebSocket connections must stay open for real-time push.
            # Standard proxy timeouts (~60 s) would silently drop idle connections.
            proxy_read_timeout 86400s;
            proxy_send_timeout 86400s;
        }

        # Auth endpoints — strict brute-force protection
```

---

- [ ] **Step 3: Explain REST API 120s timeout**

Find in `nginx/nginx.conf`:
```
            proxy_read_timeout 120s;
        }

        # Flutter web app — SPA catch-all
```

Replace with:
```
            # 120 s: city model training triggers (/cities/{city}/train) can take up
            # to 90 s. A shorter timeout would produce spurious 504 Gateway Timeout.
            proxy_read_timeout 120s;
        }

        # Flutter web app — SPA catch-all
```

---

- [ ] **Step 4: Add cert renewal caveat in HTTPS server block**

Find in `nginx/nginx.conf`:
```
        ssl_certificate     /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
```

Replace with:
```
        ssl_certificate     /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        # Certs are mounted read-only from ./nginx/certs/ on the host.
        # To renew: update files on host, then: docker compose restart nginx
        # nginx will fail to start if these files do not exist.
```

---

- [ ] **Step 5: Verify comment additions are present**

Run:
```
grep -n "shared NAT\|86400 s = 24 h\|training triggers\|mounted read-only" nginx/nginx.conf
```

Expected: 4 matches (one per new comment).

---

- [ ] **Step 6: Commit**

```bash
git add nginx/nginx.conf
git commit -m "docs: add inline comments to nginx.conf (rate limits, WS timeout, REST timeout, cert renewal)"
```
