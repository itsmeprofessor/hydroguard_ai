# Group A — ML Inference Quality: Design Specification

**Date:** 2026-05-24  
**Project:** HydroGuard-AI v3.5  
**Phase:** Group A (highest priority — no retraining required)  
**Status:** Approved for implementation planning  

---

## 1. Problem Statement

### 1.1 MC Dropout Not Wired

`city_model_service.predict_v2()` calls `model.predict()` (deterministic, single forward pass). The `ae_variance` and `tcn_variance` fields returned in every V2 response are **sigmoid-transformed z-scores relative to the training error distribution** — not stochastic uncertainty estimates. The response fields `uncertainty` and `model_entropy` therefore carry no genuine epistemic signal.

`CityHybridModel.predict_mc()` exists and is fully implemented but is never called from the live inference path.

### 1.2 Calibration ECE Measured on the Wrong Set

`training_metrics.json` records `calibration_ece_after = 0.0` for every trained city. Isotonic regression is piecewise-constant and trivially achieves zero ECE on the calibration set it was fitted on. Whether this reflects real calibration quality on unseen data is unknown. ECE has never been measured on the independent test set using the saved calibrators.

---

## 2. Scope

### In Scope

| Change | File(s) |
|---|---|
| Public parallel-MC interface on `CityHybridModel` | `backend/app/ml/models/city_hybrid.py` |
| Parallel MC dispatch + uncertainty merge in `predict_v2()` | `backend/app/services/city_model_service.py` |
| New response fields on `PredictionResponseV2` | `backend/app/schemas/v2.py` |
| New config knobs | `backend/app/core/config.py` |
| Read-only calibration audit script | `scripts/calibration_audit.py` |
| Regression + concurrency tests | `tests/test_mc_inference.py` |

### Explicitly Out of Scope

- Retraining any city model
- Modifying, replacing, or re-fitting any calibrator
- Changing saved thresholds, fusion models, or ECDF scalers
- DB schema changes
- Frontend (Flutter / web apps) changes
- nginx or infrastructure changes

---

## 3. Configuration — All Tunable Values

All numeric constants live in `backend/app/core/config.py`. No value is hardcoded inside inference or branch logic.

| Config Key | Default | Description |
|---|---|---|
| `ENABLE_MC_INFERENCE` | `true` | Feature flag — disables MC and reverts to deterministic |
| `MC_DROPOUT_SAMPLES` | `15` | Stochastic passes per branch per request |
| `MC_INFERENCE_TIMEOUT_MS` | `3000` | Wall-clock timeout for the parallel gather; fallback triggered on exceed |
| `MC_AE_UNCERTAINTY_WEIGHT` | `0.60` | Weight of AE CoV in the uncertainty merge blend |
| `MC_TCN_UNCERTAINTY_WEIGHT` | `0.40` | Weight of TCN CoV in the uncertainty merge blend |
| `MC_UNCERTAINTY_MIN` | `0.0` | Lower clip bound for per-branch CoV after normalisation |
| `MC_UNCERTAINTY_MAX` | `1.0` | Upper clip bound for per-branch CoV after normalisation |
| `MC_STABILITY_THRESHOLD_MODERATE` | `0.25` | `epistemic_uncertainty` above this → `"moderate_uncertainty"` |
| `MC_STABILITY_THRESHOLD_HIGH` | `0.55` | `epistemic_uncertainty` above this → `"high_uncertainty"` |
| `MAX_CONCURRENT_MC_THREADS` | `4` | Semaphore bound on concurrent TF thread-pool workers |
| `CALIBRATION_ECE_BINS` | `15` | Bin count for ECE calculation in calibration audit |

All defaults represent safe, conservative operational presets for the current FYP deployment scale.

---

## 4. Component Design

### 4.1 `CityHybridModel` — Parallel-Safe Public Interface

#### Private Branch Methods (internal only, never called externally)

**`_mc_ae_branch(x: np.ndarray, n_samples: int, uncertainty_min: float, uncertainty_max: float) → dict`**

- Input: read-only `(1, input_dim)` array `x`.
- Runs `n_samples` forward passes with `self._ae(x2d, training=True)` (Dropout active).
- Computes:
  - `ae_errors`: `[float]` — per-pass MSE values
  - `ae_mean_error`: `float` — mean across passes
  - `ae_uncertainty`: coefficient of variation, computed as:
  ```
  EPSILON = 1e-9
  ae_uncertainty = std(ae_errors) / max(mean(ae_errors), EPSILON)
  ae_uncertainty = clip(ae_uncertainty, uncertainty_min, uncertainty_max)
  ```
  The epsilon guard is applied **before** division to prevent division-by-zero in near-zero error regimes (fair weather on well-fitted models). The clip is applied **after** the safe division — applying clip first and dividing after would produce incorrect behaviour when the mean is near zero. `EPSILON` is a module-level constant, not hardcoded inline.
  - `ae_percentile`: ECDF rank of `ae_mean_error`. The ECDF is computed exclusively over the **training error distribution** (fitted during `train()` on `X_train`, stored in `self._ae_ecdf`). It is never refit on calibration or test data. This ensures normalization is anchored to the training regime and cannot leak calibration signal into the percentile score.
  - `ae_variance_legacy`: z-score proxy (preserved for `predict()` backward compat, not used in MC path)
- Touches no shared state. Pure function except for TF graph execution.
- Returns plain `dict`.

**`_mc_tcn_branch(sequence_snapshot: np.ndarray, x_target: np.ndarray, n_samples: int, uncertainty_min: float, uncertainty_max: float) → dict`**

- Input: `sequence_snapshot` is a **caller-provided immutable copy** of the rolling window (`sequence.copy()` called before dispatch). The live `_CityBuffer` is **never passed into this method**.
- Invariant enforced at call site: branch method signature accepts only `np.ndarray`, never a `_CityBuffer` or any mutable buffer object.
- Runs `n_samples` forward passes with `self._tcn(seq3d, training=True)`.
- Computes analogous `tcn_*` fields.
- Returns plain `dict`.

#### Public Orchestration-Safe Interface

**`prepare_mc_tasks(x: np.ndarray, sequence: Optional[np.ndarray], n_samples: int, uncertainty_min: float, uncertainty_max: float) → Tuple[Callable, Callable]`**

Returns two zero-argument callables (closures) — one for each branch — ready to be dispatched to `asyncio.to_thread`. The service layer orchestrates concurrency; `CityHybridModel` only prepares the units of work.

```
ae_fn, tcn_fn = model.prepare_mc_tasks(x_vec, seq_snapshot, n_samples, unc_min, unc_max)
ae_result, tcn_result = await asyncio.gather(
    asyncio.to_thread(ae_fn),
    asyncio.to_thread(tcn_fn),
)
```

This keeps branch method names private while giving the service layer a clean, encapsulation-respecting interface.

**`predict_mc()` (sequential, test/backward-compat only)** — delegates to `_mc_ae_branch` + `_mc_tcn_branch` sequentially. Preserved for unit tests and external callers that rely on this interface.

> **Invariant:** `predict_mc()` must **never** be used inside the production inference path once `ENABLE_MC_INFERENCE=true`. It is marked `# INTERNAL / TEST ONLY — use prepare_mc_tasks() for production parallel dispatch` in source. This prevents accidental sequential-MC degradation during debugging or future refactoring.

**`predict()` (unchanged)** — deterministic single-pass path. Not modified.

---

### 4.2 `CityModelService.predict_v2()` — Parallel Dispatch

#### Inference Path When `ENABLE_MC_INFERENCE=true`

```
1. Immutable snapshot:
   seq_snapshot = sequence.copy() if sequence is not None else None

2. Prepare tasks:
   ae_fn, tcn_fn = model.prepare_mc_tasks(
       x_vec, seq_snapshot, MC_DROPOUT_SAMPLES,
       MC_UNCERTAINTY_MIN, MC_UNCERTAINTY_MAX
   )

3. Acquire semaphore (MAX_CONCURRENT_MC_THREADS):
   async with _mc_semaphore:
       ae_result, tcn_result = await asyncio.wait_for(
           asyncio.gather(
               asyncio.to_thread(ae_fn),
               asyncio.to_thread(tcn_fn),
           ),
           timeout=MC_INFERENCE_TIMEOUT_MS / 1000,
       )

4. Deterministic merge:
   epistemic_uncertainty = clip(
       MC_AE_UNCERTAINTY_WEIGHT * ae_result["ae_uncertainty"]
     + MC_TCN_UNCERTAINTY_WEIGHT * tcn_result["tcn_uncertainty"],
       MC_UNCERTAINTY_MIN, MC_UNCERTAINTY_MAX
   )

5. Stability classification:
   prediction_stability = classify(epistemic_uncertainty,
       MC_STABILITY_THRESHOLD_MODERATE,
       MC_STABILITY_THRESHOLD_HIGH)

6. inference_mode = "mc_dropout"
   uncertainty_available = True
   degraded_reason = None
   mc_samples_used = MC_DROPOUT_SAMPLES
```

#### Fallback Path (timeout or exception)

```
result = model.predict(x_vec, sequence)    # deterministic
ae_pct  = result["ae_percentile"]
tcn_pct = result["tcn_percentile"]
inference_mode       = "fallback_deterministic"
uncertainty_available = False
epistemic_uncertainty = None
prediction_stability  = None
degraded_reason       = "timeout" | "exception"
mc_samples_used       = 1
```

Fallback is logged at `WARNING` level with city slug, reason, and latency.

> **Invariant — no fake uncertainty on fallback:** When `inference_mode = "fallback_deterministic"`, `epistemic_uncertainty` must remain `None`. It must never be filled with a last-known value, approximated from the z-score proxy, or estimated from the deterministic `ae_variance`/`tcn_variance`. Fake uncertainty on fallback is worse than null — it silently misrepresents model confidence. The `uncertainty_available = False` flag is the contract to downstream consumers.

#### Feature Flag Off (`ENABLE_MC_INFERENCE=false`)

Same as deterministic `model.predict()` but `inference_mode = "deterministic"`, `degraded_reason = "disabled"`.

---

### 4.3 Uncertainty Merge — Heuristic, Documented

The blend:

```
epistemic_uncertainty = clip(
    MC_AE_UNCERTAINTY_WEIGHT * ae_CoV + MC_TCN_UNCERTAINTY_WEIGHT * tcn_CoV,
    MC_UNCERTAINTY_MIN, MC_UNCERTAINTY_MAX
)
```

is an **operationally convenient heuristic**, not a statistically calibrated uncertainty model. It is documented as such in code comments. The weights are configurable. Future strategies (e.g., `"max_branch"`, `"entropy_proxy"`, `"learned_meta"`) are supported via an `uncertainty_strategy` field set to `"weighted_blend"` in the response and config.

Uncertainty strategy is selected from config:

```python
UNCERTAINTY_STRATEGY = "weighted_blend"   # future: "max_branch" | "entropy_proxy"
```

---

### 4.4 TensorFlow Thread Safety

TensorFlow 2.x Keras models support concurrent inference calls from multiple threads when models do not share variables. AE and TCN are separate `keras.Model` instances with no shared weights. Concurrent `model(x, training=True)` calls are safe under this constraint.

**Safeguard:** `asyncio.Semaphore(MAX_CONCURRENT_MC_THREADS)` at the service level bounds simultaneous TF thread-pool workers across all city requests. If TF runtime instability appears during testing, the semaphore bound is reduced without changing inference logic.

**GPU contention note:** The semaphore bounds *logical* Python concurrency. TensorFlow still serialises some GPU ops internally (kernel launch queuing, memory allocation). Under concurrent `training=True` calls on GPU, nondeterministic latency spikes and rare OOM bursts remain possible even with variable isolation. The semaphore mitigates this — it does not eliminate it. On CPU-only inference (the expected FYP deployment), this risk does not apply. If GPU deployment is introduced later, per-device locking or `tf.function` pre-compilation should be evaluated.

---

### 4.5 Latency Instrumentation

`time.perf_counter()` wraps each stage. Timing is **purely passive** — metrics collection never affects inference control flow.

| Field | Captures |
|---|---|
| `ae_mc_latency_ms` | Time for AE branch (wall clock, concurrent) |
| `tcn_mc_latency_ms` | Time for TCN branch (wall clock, concurrent) |
| `fusion_latency_ms` | LightGBM FusionModel |
| `calibration_latency_ms` | IsotonicCalibrator transform |
| `total_prediction_latency_ms` | Full `predict_v2()` wall time |

**Production behavior:** stage timings logged at `DEBUG` level only; included in response body only when `DEBUG=true`. Always logged in aggregate at `INFO` when `total_prediction_latency_ms > MC_INFERENCE_TIMEOUT_MS * 0.75` (approaching timeout budget).

---

### 4.6 Response Schema — New Fields on `PredictionResponseV2`

All new fields are **Optional with `None` defaults** — existing clients with no knowledge of these fields continue to work unchanged.

| Field | Type | Values / Notes |
|---|---|---|
| `inference_mode` | `str` | `"mc_dropout"` \| `"deterministic"` \| `"fallback_deterministic"` |
| `uncertainty_available` | `bool` | `True` only when MC ran to completion |
| `epistemic_uncertainty` | `float \| None` | CoV-based blend; `None` on fallback/disabled |
| `model_uncertainty_score` | `float \| None` | Alias of `epistemic_uncertainty`; explicit API name for consumers |
| `prediction_stability` | `str \| None` | `"stable"` \| `"moderate_uncertainty"` \| `"high_uncertainty"` |
| `mc_samples_requested` | `int \| None` | `MC_DROPOUT_SAMPLES` config value at request time |
| `mc_samples_completed` | `int \| None` | Actual passes completed (equals requested unless partial failure) |
| `uncertainty_strategy` | `str \| None` | `"weighted_blend"` (current); extensible |
| `degraded_reason` | `str \| None` | `"timeout"` \| `"exception"` \| `"disabled"` \| `None` |
| `inference_runtime_ms` | `float \| None` | `total_prediction_latency_ms`; included in response when `DEBUG=true` |

**Preserved unchanged:** `uncertainty` (calibrator-CI-derived aleatoric width), `confidence_interval`, `event_probability`, `risk_band`, `alert_tier`, `is_alert`, `component_scores`, `model_entropy`.

**On `model_entropy` specifically:** the current response contains a `model_entropy` field set by `calibrator.model_entropy(p_calib)` — this is the **binary cross-entropy of the calibrated probability** (`-p log p - (1-p) log(1-p)`), a measure of decision uncertainty, not MC epistemic uncertainty. This field is preserved unchanged. The new `epistemic_uncertainty` field is a separate MC-derived signal and must not be confused with or replace the calibrator's `model_entropy`.

The three uncertainty lanes in the final response are:
- `uncertainty` — calibrator CI width (aleatoric / statistical)
- `model_entropy` — binary cross-entropy of calibrated p (decision uncertainty)
- `epistemic_uncertainty` — MC Dropout CoV blend (epistemic / model uncertainty)

---

### 4.7 Calibration Audit Script (`scripts/calibration_audit.py`)

**Execution:** `python scripts/calibration_audit.py [--city <slug>] [--all]`

**Read-only contract:** writes only `calibration_audit.json` and appends to `training_metrics.json`. Never touches `.keras`, `.pkl` model files, calibrators, thresholds, or fusion models.

**Per-city audit steps:**

1. Load saved calibrator from `saved_models/city_models/<slug>/calibrator.pkl`
2. Reconstruct evaluation split using a strict three-tier hierarchy (evaluated in order — first applicable wins):

   **Tier 1 — Year-based holdout** (`holdout_strategy = "year_2023_plus"`, `holdout_rows > 0`):  
   Filter master CSV to rows with `date >= 2023-01-01` for this city slug. Used for Islamabad and Lahore.

   **Tier 2 — Temporal last-15% split** (`holdout_strategy = "last_15pct_fallback"`, `holdout_rows = 0`, test rows available):  
   Sort city rows chronologically; take the last 15% as the evaluation split. Used for Karachi, Gilgit, Peshawar, Quetta.

   **Tier 3 — Stored test split** (no holdout, no temporal split reproducible):  
   Re-derive from `test_n_rows` in `training_metrics.json` using the same chronological tail. Only used if Tiers 1 and 2 cannot be reconstructed cleanly (e.g., CSV unavailable or row count mismatch).

   The tier used is recorded in `calibration_audit.json["split_tier"]` (values: `"year_holdout"`, `"last_15pct"`, `"stored_test"`). This prevents double-evaluation inconsistencies and ensures calibration metrics use a single, documented denominator per city.

   After split reconstruction: re-apply `WeatherDataPreprocessorV2` (loaded from `preprocessor_v2.joblib`), apply FusionModel to reconstruct uncalibrated probabilities for the split.
3. Compute:
   - `pre_calibration_ece_test`: ECE before isotonic transform (raw fusion probabilities vs test labels)
   - `post_calibration_ece_test`: ECE after isotonic transform on test set
   - `pre_calibration_brier_test`
   - `post_calibration_brier_test`
   - `calibration_improvement`: `pre - post` (positive = calibrator helps)
   - `bin_populations`: histogram of `CALIBRATION_ECE_BINS` equal-width bins
   - `reliability_curve`: `(mean_predicted, fraction_positive)` per bin
4. Write `calibration_audit.json`:

```json
{
  "audit_version": "1.0",
  "pipeline_version": "v3.5",
  "generated_at": "<ISO timestamp>",
  "city_slug": "<slug>",
  "calibration_method": "isotonic",
  "calibration_ece_cal_set": <existing value from training_metrics>,
  "pre_calibration_ece_test": <float>,
  "post_calibration_ece_test": <float>,
  "pre_calibration_brier_test": <float>,
  "post_calibration_brier_test": <float>,
  "calibration_improvement": <float>,
  "bin_populations": [...],
  "reliability_curve": [{"predicted": ..., "actual": ...}, ...],
  "calibration_bins_used": <int from config>,
  "notes": ""
}
```

5. Append to `training_metrics.json` (non-destructively — **all existing fields preserved**):

```json
"calibration_ece_after":         <unchanged — original field kept for backward compat>,
"calibration_ece_cal_set":       <copy of calibration_ece_after, explicit alias>,
"calibration_ece_test_set":      <from audit — the new truthful metric>,
"calibration_brier_test_after":  <from audit>,
"calibration_bins_used":         <from config>,
"calibration_audit_path":        "saved_models/city_models/<slug>/calibration_audit.json"
```

`calibration_ece_after` is never overwritten. `calibration_ece_cal_set` is added as an alias with the same value, clarifying semantics. `calibration_ece_test_set` is the new independent metric.

---

### 4.8 Observability Contract — MC Success Rate

`degraded_reason` and `inference_mode` give per-request visibility. At the system level, the following spec-level monitor is required (implementation deferred to Group D — Operational Resilience, but architected for here):

**`MC_SUCCESS_RATE` per city, rolling 100-request window:**
- Computed as: `(requests with inference_mode="mc_dropout") / total_requests`
- Alert threshold: `MC_SUCCESS_RATE < 0.90` for any city → `WARNING` log + surfaced in `/health` response
- Alert threshold: `MC_SUCCESS_RATE < 0.70` → `ERROR` log; consider auto-disabling MC for that city

This metric catches **silent fallback dominance** — the scenario where MC inference is nominally enabled but consistently timing out or failing, causing every live prediction to silently degrade to deterministic while `inference_mode` logging goes unnoticed in production.

The rolling window counter is in-memory per city in `CityModelService`. No Redis or DB dependency.

---

## 5. Test Plan

**File:** `tests/test_mc_inference.py`

| Test | What it validates |
|---|---|
| `test_mc_branches_independent` | `_mc_ae_branch` and `_mc_tcn_branch` return identical results whether run sequentially or concurrently (no shared state) |
| `test_predict_v2_mc_fields_present` | All new schema fields present and correctly typed in MC mode |
| `test_predict_v2_flag_disabled` | `ENABLE_MC_INFERENCE=false` → `inference_mode="deterministic"`, all `epistemic_*` fields are `None` |
| `test_predict_v2_fallback_on_timeout` | Mocked timeout → `inference_mode="fallback_deterministic"`, `degraded_reason="timeout"`, valid `event_probability` returned |
| `test_predict_v2_fallback_on_exception` | Mocked branch exception → same fallback behavior |
| `test_tcn_buffer_immutability` | `_CityBuffer` state byte-identical before and after `_mc_tcn_branch` executes |
| `test_epistemic_uncertainty_range` | `epistemic_uncertainty` always in `[MC_UNCERTAINTY_MIN, MC_UNCERTAINTY_MAX]` |
| `test_prediction_stability_mapping` | Correct `prediction_stability` label for boundary values of `epistemic_uncertainty` |
| `test_concurrent_cities` | `MAX_CONCURRENT_TEST_REQUESTS` simultaneous city requests → no corrupted results, no race conditions |
| `test_latency_within_budget` | `total_prediction_latency_ms < MC_LATENCY_BUDGET_MS` on mock model (CPU, no GPU required) |
| `test_calibration_audit_readonly` | `calibration_audit.py` writes only `.json`, never `.pkl` / `.keras` |
| `test_calibration_audit_schema` | `calibration_audit.json` contains all required fields including `audit_version`, `generated_at` |
| `test_calibration_ece_values_plausible` | `post_calibration_ece_test` is finite, non-negative; `calibration_improvement` is finite |

All config values injected via test fixtures — no hardcoded `15`, `0.25`, `2000`, or `15 bins` inside test code.

---

## 6. Rollout Sequence

1. `config.py` additions (no runtime effect yet)
2. `city_hybrid.py` — add `prepare_mc_tasks()`, private branch methods, update `predict_mc()`
3. `schemas/v2.py` — add optional fields (backward-compatible)
4. `city_model_service.py` — wire parallel MC into `predict_v2()` behind flag (`ENABLE_MC_INFERENCE=false` initially)
5. `tests/test_mc_inference.py` — all tests passing before flag is enabled
6. Enable `ENABLE_MC_INFERENCE=true`, profile latency, verify p99 < budget
7. `scripts/calibration_audit.py` — run audit, inspect results, commit `calibration_audit.json` per city
8. Update `training_metrics.json` for all 6 cities with test-set calibration fields

---

## 7. Acceptance Criteria

- [ ] All 13 tests in `test_mc_inference.py` pass
- [ ] `epistemic_uncertainty` is a real stochastic estimate (CoV), not a z-score proxy
- [ ] `inference_mode` is present and correct in every V2 prediction response
- [ ] `degraded_reason` is non-null and logged whenever fallback activates
- [ ] p99 latency < `MC_LATENCY_BUDGET_MS` under `MAX_CONCURRENT_TEST_REQUESTS` concurrent requests
- [ ] `_CityBuffer` state provably unchanged after any MC TCN branch execution
- [ ] `calibration_audit.json` present for all 6 trained cities after audit run
- [ ] `training_metrics.json` contains `calibration_ece_test_set` for all 6 cities
- [ ] No `.pkl` or `.keras` artifacts modified during audit
- [ ] `ENABLE_MC_INFERENCE=false` restores fully deterministic behavior with zero test regression
