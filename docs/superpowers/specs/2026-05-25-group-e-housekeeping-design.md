# Group E — CLAUDE.md Accuracy Pass, nginx Docs, Orphan Removal Design

## Goal

Bring CLAUDE.md into alignment with the actual v3.2+ codebase (the current file still
describes v3.1 internals), add inline comments to `nginx/nginx.conf` where context is
missing, and remove or correct all stale references to decommissioned features.

---

## Context: What's Wrong

The CLAUDE.md header correctly says "BahdanauAttention → TCN" but the Architecture body
contradicts this at every turn. The result: any developer (or AI agent) reading CLAUDE.md
gets a completely wrong mental model of the inference stack.

Key inaccuracies found by code audit:

| Area | CLAUDE.md says | Reality |
|---|---|---|
| Model architecture | LSTM + BahdanauAttention | TCN (CausalTCN, dilations=[1,2,4,8,16,32], seq_len=30) |
| Score blending | `0.55×ae + 0.45×lstm` | LightGBM FusionModel → IsotonicCalibrator |
| Uncertainty | Not mentioned | Monte Carlo Dropout (N stochastic passes, epistemic variance) |
| OOD detection | Not mentioned | `ood_detector.pkl`, Mahalanobis distance, non-blocking |
| Saved-model layout | `autoencoder/`, `lstm_attention/`, `ae_calibration.npy` | `autoencoder.keras`, `tcn_reconstructor.keras`, `ae_ecdf.pkl`, `tcn_ecdf.pkl`, `lgbm_model.pkl`, `calibrator.pkl`, `preprocessor_v2.joblib`, `ood_detector.pkl`, `training_metrics.json` |
| Output signature | `{anomaly_score, is_anomaly, lstm_score, confidence}` | `{event_probability, risk_band, is_alert, hri_score, confidence_interval, uncertainty, model_entropy, component_scores, drivers, inference_mode, epistemic_uncertainty, …}` |
| Preprocessing | `utils/preprocessing.py` (v1) | `app/ml/preprocessing_v2.py` — `WeatherDataPreprocessorV2`, NUMERICAL_V2 (28 base + 9 Karachi coastal) |
| anomaly_service | Active fallback | Decommissioned in v3.2; file does not exist; `__init__.py` has tombstone comment |
| BahdanauAttention | Documented as live, `custom_objects` required | Does not exist in main repo; no imports anywhere |
| TCN seq_len | Documents seq_len=7 (LSTM window) | seq_len=30 (TCN_SEQ_LEN constant) |
| App lifespan | "Verifies `anomaly_service.get_model_info()`" | Not present; city_model_service loads lazily |
| Request flow | Routes through `anomaly_service` | Routes through `city_model_service` exclusively |
| Frontend served by nginx | Conflates citizen_app (React) with citizen_flutter_app (Flutter) | nginx serves `citizen_flutter_app/build/web` (compiled Flutter); citizen_app is a separate React+Babel app |
| nginx rate limits | Not documented in nginx section | 5 r/m auth, 60 r/m predict, 200 r/m general API |

---

## Track 1: CLAUDE.md Full Accuracy Pass

**File:** `CLAUDE.md` (root of repo)

### 1a. Architecture header (already correct — no change)

The version note at the top is accurate. No change needed.

### 1b. City-specific hybrid models section — complete rewrite

Replace the current section (which describes LSTM+BahdanauAttention+weighted-blend) with:

**Architecture (one model per city)** in `app/ml/models/city_hybrid.py`:
- **Autoencoder**: Dense `[64, 32, 16]` → latent **8** → mirrored decoder → `linear`. Dropout 0.20.
  Physics-weighted MSE loss: prcp 3×, pressure 2.5×, humidity 2×. Trained on fair-weather rows only.
  Score: `ECDFScaler(ae_error) → ae_percentile ∈ [0,1]`.
- **TCN**: `CausalTCN(filters=128, kernel=3, dilations=[1,2,4,8,16,32], seq_len=30)`.
  Receptive field = 127 observations (≈4 months of daily data). Trained as next-step reconstructor.
  Score: `ECDFScaler(tcn_error) → tcn_percentile ∈ [0,1]`.
- **Fusion**: `ae_percentile` + `tcn_percentile` + derived features → `FusionModel` (LightGBM binary classifier) → `P(event)` → `IsotonicCalibrator` → `event_probability`.
- **Uncertainty**: Monte Carlo Dropout — N stochastic forward passes at inference. Outputs: `epistemic_uncertainty` (weighted blend of AE + TCN variance), `model_entropy`, `prediction_stability` (`stable|warming_up|degraded`).
- **OOD detection**: `OODDetector` (`ood_detector.pkl`) — Mahalanobis distance in feature space. OOD is **non-blocking**; sets `ood_detected=True` and raises `epistemic_uncertainty` but does not stop inference.
- **No LSTM. No BahdanauAttention. No BiTCN. Strictly causal.**

**Standardised output dict** (v3.2+):
```
{
  inference_id, city, city_slug, inferred_at, model_version, source,
  event_probability,   # IsotonicCalibrator output ∈ [0,1]
  confidence_interval, # [lo, hi]
  uncertainty,         # epistemic uncertainty scalar
  model_entropy,       # None when MC disabled
  risk_band,           # "Low" | "Moderate" | "High" | "Critical"
  hri_score,           # 0–100 int
  is_alert,            # bool
  alert_tier,          # 1–5 (severity tier)
  component_scores: { ae_percentile, tcn_percentile, p_event_raw, ae_variance, tcn_variance },
  drivers,             # SHAP-derived top contributors
  weather_inputs,      # raw inputs echoed back
  climatology_context, # prcp_climo_pct, pressure_climo_z, etc.
  coastal_features,    # Karachi only; null for other cities
  sequence_context: { buffer_size, required_size, tcn_active },
  inference_mode,      # "mc_dropout" | "fallback_deterministic"
  epistemic_uncertainty, model_uncertainty_score, prediction_stability,
  mc_samples_requested, mc_samples_completed, degraded_reason
}
```

### 1c. Remove the "Anomaly detection" section

Delete the entire section (`app/services/anomaly_service.py`) — it describes a decommissioned
service. Replace with a one-line note in the City-specific hybrid models section:

> `anomaly_service` was decommissioned in v3.2. All inference routes through `city_model_service`.
> The fallback for cities without trained models is a rule-based heuristic in `city_model_service._build_degraded_response()`.

### 1d. Remove the "Bahdanau Attention layer" section entirely

`app/ml/models/attention.py` does not exist in the main repo. No imports anywhere. Delete the section.

### 1e. Update saved-model layout

Replace the current layout block with:
```
backend/saved_models/city_models/
└── <slug>/
    ├── autoencoder.keras        # Keras 3 SavedModel (AE branch)
    ├── tcn_reconstructor.keras  # Keras 3 SavedModel (TCN branch)
    ├── ae_ecdf.pkl              # ECDFScaler fitted on AE reconstruction errors
    ├── tcn_ecdf.pkl             # ECDFScaler fitted on TCN reconstruction errors
    ├── lgbm_model.pkl           # LightGBM FusionModel (binary P(event))
    ├── calibrator.pkl           # IsotonicCalibrator
    ├── preprocessor_v2.joblib   # WeatherDataPreprocessorV2 fitted on city's data
    ├── ood_detector.pkl         # OODDetector (Mahalanobis; non-blocking)
    ├── cal_data.npz             # Held-out calibration arrays (for audit scripts)
    └── training_metrics.json    # Training provenance + evaluation metrics
```

### 1f. Update ML & preprocessing reference

Change `utils/preprocessing.py` to `app/ml/preprocessing_v2.py`. Note that
`utils/preprocessing.py` still exists and is used only by the legacy global-model
scripts (`scripts/train.py`, `scripts/evaluate.py`, `scripts/tune_threshold.py`);
it is NOT used by v3.2 inference.

Update NUMERICAL_V2 description: 28 base numerical features + 9 Karachi-specific
coastal features (auto-excluded for other cities via `num_present` filter).

### 1g. Update app lifespan

Remove: "Verifies `anomaly_service.get_model_info()` and logs model type/version."
Replace: lifespan now calls `city_model_service.refresh_registry()` and warms TCN
buffers via `warm_up_tcn_buffers()` from the master CSV.

### 1h. Update request flow

Remove: `→ service layer (anomaly_service) → Repository`
Replace: `→ service layer (city_model_service.predict_v2()) → FusionModel → Repository`

### 1i. Update Key Constraints section

- Line "ML architecture is fixed: Autoencoder + LSTM + **Bahdanau Attention**" →
  "ML architecture is fixed: Autoencoder + **TCN** + **LightGBM FusionModel** + **IsotonicCalibrator** per-city. MC Dropout for epistemic uncertainty."
- Line "each of the 10 cities trains its own AE+LSTM+Attention model" →
  "each city trains its own AE+TCN+FusionModel set"
- Remove: "Bahdanau Attention is custom — always pass `custom_objects`..." — no longer relevant.
- Update seq_len reference from 7 to 30.

### 1j. Update nginx paragraph in CLAUDE.md

Expand from one paragraph to include:
- Correct frontend: nginx serves `citizen_flutter_app/build/web` (compiled Flutter app)
- Rate limits: auth 5 r/m burst=3; predict 60 r/m burst=10; general API 200 r/m burst=50
- HTTPS: certs at `nginx/certs/`; self-signed generated with `openssl req ...`; production requires Certbot

---

## Track 2: nginx.conf Inline Comments

**File:** `nginx/nginx.conf`

The file already has a header comment block and section dividers. Add targeted comments
at the following locations (no structural changes to any directives):

1. **Rate-limit zone block** (after current zone definitions): add a note that limits are
   per-IP (`$binary_remote_addr`), not per-session — multiple users behind shared NAT
   (university/office) share the quota.

2. **WebSocket location `/ws/`**: add a note explaining the 86400 s (24 h) timeout —
   WebSocket connections must stay open indefinitely for real-time push; standard proxy
   timeouts would kill idle connections.

3. **REST API location timeout**: add a note explaining `proxy_read_timeout 120s` —
   training triggers (`/train`) can take up to 90 s; this headroom prevents premature
   504 Gateway Timeout.

4. **CSP header (HTTPS server block, line ~130)**: add a note explaining why
   `unsafe-inline` and `unsafe-eval` are present — required by Flutter CanvasKit WASM
   rendering and OpenStreetMap tile loading; not a mistake.

5. **HTTPS cert volume**: add a note that certs are mounted `:ro`; to renew, update
   files on the host and `docker compose restart nginx`.

---

## Track 3: Dead Code Sweep

**What was found by grepping the backend source:**

- `backend/utils/preprocessing.py` — still imported by legacy scripts (`train.py`,
  `evaluate.py`, `tune_threshold.py`). NOT dead; keep it. CLAUDE.md just incorrectly
  elevated it to the main inference preprocessor.
- `city_hybrid.py:614` — backward-compat name shim `lstm_attention.keras`. Intentional
  (allows loading old v3.1 checkpoints). Keep it.
- No dead imports, orphaned functions, or unreachable code were found in the backend
  source files.

**Conclusion:** The "orphan removal" in Group E is entirely in CLAUDE.md, not source
files. The source-level dead code sweep confirms no action is needed there.

---

## Testing / Verification

All changes are documentation-only (CLAUDE.md + nginx.conf comments). Verification:

1. After edits: `grep -n "BahdanauAttention\|lstm_attention\|anomaly_service\|0\.55.*ae" CLAUDE.md` → zero matches.
2. After edits: `grep -n "LSTM + Attention\|lstm_score\|is_anomaly.*confidence" CLAUDE.md` → zero matches.
3. nginx.conf: `nginx -t -c nginx/nginx.conf` (if nginx is locally available) or validate by parsing.
4. Full test suite still passes: `pytest tests/test_api.py -v --tb=short` — no code changes means no regression risk, but run as a sanity check.

---

## Constraints

- No source code changes — this is documentation and comments only.
- CLAUDE.md is the authoritative human reference; accuracy is more important than brevity.
- Do NOT remove `utils/preprocessing.py` — it is still used by legacy scripts.
- Do NOT remove the `lstm_attention.keras` fallback shim in `city_hybrid.py` — it handles
  loading old checkpoints.
- nginx.conf directive values (timeouts, limits) must not change — comments only.
