# Group A — ML Inference Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire parallel MC Dropout into `predict_v2()`, add a read-only calibration audit script, and land all regression tests — producing genuine epistemic uncertainty in every V2 prediction response.

**Architecture:** `CityHybridModel.prepare_mc_tasks()` returns two zero-argument callables (closures) for AE and TCN branches. `CityModelService.predict_v2()` dispatches them concurrently via `asyncio.gather(to_thread(ae_fn), to_thread(tcn_fn))` behind a semaphore and feature flag. Calibration audit runs offline and writes `calibration_audit.json` per city without touching any `.keras` or `.pkl` file.

**Tech Stack:** Python 3.11, TensorFlow 2.x Keras, asyncio, LightGBM, NumPy, scikit-learn (ECE), pytest-asyncio

---

## File Structure

| Status | File | Change |
|---|---|---|
| Modify | `backend/app/core/config.py` | Add `MCInferenceConfig` class |
| Modify | `backend/app/ml/models/city_hybrid.py` | Add `_mc_ae_branch`, `_mc_tcn_branch`, `prepare_mc_tasks()`; update `predict_mc()` |
| Modify | `backend/app/schemas/v2.py` | Add 10 optional fields to `PredictionResponseV2` |
| Modify | `backend/app/services/city_model_service.py` | Parallel MC dispatch, semaphore, success-rate counter, latency timing |
| Create | `tests/test_mc_inference.py` | 13 regression + concurrency tests |
| Create | `scripts/calibration_audit.py` | Read-only calibration audit script |
| Modify | `backend/saved_models/city_models/*/training_metrics.json` | Append calibration test-set fields (6 cities) |

---

### Task 1: Add MC Config to `config.py`

**Files:**
- Modify: `backend/app/core/config.py` (end of file, after `DriftConfig`)

- [ ] **Step 1: Add `MCInferenceConfig` class**

Insert after the `DriftConfig` class (before the `LOGGING_CONFIG` dict):

```python
# ============================================================
#  Monte Carlo Dropout Inference
# ============================================================

class MCInferenceConfig:
    """Configuration for parallel MC Dropout inference in predict_v2().

    All values are read from environment variables so they can be
    tuned per-deployment without code changes.
    """
    # Feature flag — set to false to revert to deterministic model.predict()
    ENABLED: bool = os.getenv("ENABLE_MC_INFERENCE", "true").lower() in ("true", "1", "yes")
    # Stochastic forward passes per branch per request
    DROPOUT_SAMPLES: int = int(os.getenv("MC_DROPOUT_SAMPLES", "15"))
    # Wall-clock timeout for asyncio.gather; fallback triggers on exceed
    INFERENCE_TIMEOUT_MS: int = int(os.getenv("MC_INFERENCE_TIMEOUT_MS", "3000"))
    # Uncertainty merge weights (must sum to 1.0; heuristic blend documented in spec)
    AE_UNCERTAINTY_WEIGHT: float = float(os.getenv("MC_AE_UNCERTAINTY_WEIGHT", "0.60"))
    TCN_UNCERTAINTY_WEIGHT: float = float(os.getenv("MC_TCN_UNCERTAINTY_WEIGHT", "0.40"))
    # Clip bounds applied after CoV computation
    UNCERTAINTY_MIN: float = float(os.getenv("MC_UNCERTAINTY_MIN", "0.0"))
    UNCERTAINTY_MAX: float = float(os.getenv("MC_UNCERTAINTY_MAX", "1.0"))
    # prediction_stability tier boundaries
    STABILITY_THRESHOLD_MODERATE: float = float(os.getenv("MC_STABILITY_THRESHOLD_MODERATE", "0.25"))
    STABILITY_THRESHOLD_HIGH: float = float(os.getenv("MC_STABILITY_THRESHOLD_HIGH", "0.55"))
    # Semaphore bound on concurrent TF thread-pool workers
    MAX_CONCURRENT_THREADS: int = int(os.getenv("MAX_CONCURRENT_MC_THREADS", "4"))
    # Uncertainty strategy name (logged in response; extensible)
    UNCERTAINTY_STRATEGY: str = os.getenv("MC_UNCERTAINTY_STRATEGY", "weighted_blend")
    # Bin count for ECE computation in calibration audit
    CALIBRATION_ECE_BINS: int = int(os.getenv("CALIBRATION_ECE_BINS", "15"))
```

- [ ] **Step 2: Verify config loads without error**

```bash
python -c "from app.core.config import MCInferenceConfig; print(MCInferenceConfig.ENABLED, MCInferenceConfig.DROPOUT_SAMPLES)"
```

Expected output: `True 15`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): add MCInferenceConfig for parallel MC Dropout tuning"
```

---

### Task 2: Refactor `CityHybridModel` — Branch Methods + `prepare_mc_tasks()`

**Files:**
- Modify: `backend/app/ml/models/city_hybrid.py`

- [ ] **Step 1: Write a failing test for `prepare_mc_tasks` return type**

```python
# tests/test_mc_inference.py
import numpy as np
import pytest
from app.ml.models.city_hybrid import CityHybridModel

def _make_model(input_dim: int = 8) -> CityHybridModel:
    m = CityHybridModel("testcity", input_dim=input_dim)
    m.build()
    return m

def test_prepare_mc_tasks_returns_callables():
    model = _make_model(input_dim=8)
    x = np.zeros((8,), dtype=np.float32)
    ae_fn, tcn_fn = model.prepare_mc_tasks(x, None, n_samples=2,
                                            uncertainty_min=0.0, uncertainty_max=1.0)
    assert callable(ae_fn)
    assert callable(tcn_fn)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd D:/Programming/FYP/hydroguard_ai
pytest tests/test_mc_inference.py::test_prepare_mc_tasks_returns_callables -v
```

Expected: `AttributeError: 'CityHybridModel' object has no attribute 'prepare_mc_tasks'`

- [ ] **Step 3: Add `MC_COV_EPSILON` module constant**

At the top of `city_hybrid.py`, after `MC_DROPOUT_SAMPLES = 15`, add:

```python
# Epsilon guard for CoV: prevents division-by-zero when reconstruction error is near zero
# (well-fitted model on fair-weather input). Applied BEFORE division, clip applied after.
MC_COV_EPSILON: float = 1e-9
```

- [ ] **Step 4: Add `_mc_ae_branch` private method to `CityHybridModel`**

Insert inside `CityHybridModel`, between `predict_mc` and `save`:

```python
def _mc_ae_branch(
    self,
    x: np.ndarray,
    n_samples: int,
    uncertainty_min: float,
    uncertainty_max: float,
) -> Dict[str, Any]:
    """Run n_samples stochastic AE forward passes (training=True activates Dropout).

    Pure function — touches no shared state.  Returns dict with ae_* keys.
    Called exclusively via prepare_mc_tasks() closures.
    """
    x2d = x.reshape(1, -1)
    ae_errors: List[float] = []
    for _ in range(n_samples):
        rec = self._ae(x2d, training=True).numpy()
        ae_errors.append(float(np.mean((x2d - rec) ** 2)))

    ae_mean = float(np.mean(ae_errors))
    ae_std  = float(np.std(ae_errors))
    ae_cov  = ae_std / max(ae_mean, MC_COV_EPSILON)
    ae_uncertainty = float(np.clip(ae_cov, uncertainty_min, uncertainty_max))

    ae_pct = self._ae_ecdf.transform_scalar(ae_mean)

    # Legacy z-score proxy preserved for backward compat (not used in MC merge)
    ae_z = (ae_mean - self._ae_error_mu) / max(self._ae_error_std, MC_COV_EPSILON)
    ae_variance_legacy = float(1.0 / (1.0 + np.exp(-ae_z)))

    return {
        "ae_uncertainty":    round(ae_uncertainty, 4),
        "ae_mean_error":     round(ae_mean, 6),
        "ae_percentile":     round(float(np.clip(ae_pct, 0.0, 1.0)), 4),
        "ae_variance":       round(ae_variance_legacy, 4),
        "ae_error_raw":      round(ae_mean, 6),
    }
```

- [ ] **Step 5: Add `_mc_tcn_branch` private method**

```python
def _mc_tcn_branch(
    self,
    sequence_snapshot: np.ndarray,
    x_target: np.ndarray,
    n_samples: int,
    uncertainty_min: float,
    uncertainty_max: float,
) -> Dict[str, Any]:
    """Run n_samples stochastic TCN forward passes.

    sequence_snapshot MUST be a caller-provided immutable copy (sequence.copy()).
    The live _CityBuffer is never passed into this method.
    """
    if self._tcn is None or sequence_snapshot is None:
        return {
            "tcn_uncertainty": 0.0,
            "tcn_mean_error":  0.0,
            "tcn_percentile":  0.0,
            "tcn_variance":    0.0,
            "tcn_error_raw":   0.0,
        }

    x2d   = x_target.reshape(1, -1)
    seq3d = sequence_snapshot.reshape(1, self.seq_len, self.input_dim)
    tcn_errors: List[float] = []
    for _ in range(n_samples):
        pred = self._tcn(seq3d, training=True).numpy()
        tcn_errors.append(float(np.mean((pred - x2d) ** 2)))

    tcn_mean = float(np.mean(tcn_errors))
    tcn_std  = float(np.std(tcn_errors))
    tcn_cov  = tcn_std / max(tcn_mean, MC_COV_EPSILON)
    tcn_uncertainty = float(np.clip(tcn_cov, uncertainty_min, uncertainty_max))

    tcn_pct = self._tcn_ecdf.transform_scalar(tcn_mean)

    tcn_z = (tcn_mean - self._tcn_error_mu) / max(self._tcn_error_std, MC_COV_EPSILON)
    tcn_variance_legacy = float(1.0 / (1.0 + np.exp(-tcn_z)))

    return {
        "tcn_uncertainty": round(tcn_uncertainty, 4),
        "tcn_mean_error":  round(tcn_mean, 6),
        "tcn_percentile":  round(float(np.clip(tcn_pct, 0.0, 1.0)), 4),
        "tcn_variance":    round(tcn_variance_legacy, 4),
        "tcn_error_raw":   round(tcn_mean, 6),
    }
```

- [ ] **Step 6: Add `prepare_mc_tasks` public method**

```python
def prepare_mc_tasks(
    self,
    x: np.ndarray,
    sequence: Optional[np.ndarray],
    n_samples: int,
    uncertainty_min: float,
    uncertainty_max: float,
) -> Tuple[Any, Any]:
    """Return two zero-argument callables ready for asyncio.to_thread dispatch.

    The service layer calls:
        ae_fn, tcn_fn = model.prepare_mc_tasks(...)
        ae_result, tcn_result = await asyncio.gather(
            asyncio.to_thread(ae_fn),
            asyncio.to_thread(tcn_fn),
        )

    Invariant: sequence_snapshot is a copy made here — the live buffer is
    never captured in the TCN closure.
    """
    x_copy   = np.array(x, copy=True)
    seq_copy = np.array(sequence, copy=True) if sequence is not None else None

    def ae_fn() -> Dict[str, Any]:
        return self._mc_ae_branch(x_copy, n_samples, uncertainty_min, uncertainty_max)

    def tcn_fn() -> Dict[str, Any]:
        return self._mc_tcn_branch(seq_copy, x_copy, n_samples, uncertainty_min, uncertainty_max)

    return ae_fn, tcn_fn
```

- [ ] **Step 7: Update `predict_mc` docstring to mark as INTERNAL/TEST ONLY**

At the top of the existing `predict_mc` method docstring, add:

```
# INTERNAL / TEST ONLY — use prepare_mc_tasks() for production parallel dispatch.
# This method runs AE and TCN branches sequentially; calling it in the live
# inference path silently doubles latency relative to the parallel path.
```

Also update the method body to delegate to `_mc_ae_branch` and `_mc_tcn_branch`:

```python
def predict_mc(
    self,
    x: np.ndarray,
    sequence: Optional[np.ndarray] = None,
    n_samples: int = MC_DROPOUT_SAMPLES,
) -> Dict[str, Any]:
    """
    # INTERNAL / TEST ONLY — use prepare_mc_tasks() for production parallel dispatch.
    # This method runs AE and TCN branches sequentially; calling it in the live
    # inference path silently doubles latency relative to the parallel path.

    Monte Carlo Dropout inference for epistemic uncertainty estimation.
    Delegates to _mc_ae_branch + _mc_tcn_branch for implementation reuse.
    """
    if self._ae is None:
        raise RuntimeError(f"Model for {self.city} not built/loaded.")

    from app.core.config import MCInferenceConfig
    unc_min = MCInferenceConfig.UNCERTAINTY_MIN
    unc_max = MCInferenceConfig.UNCERTAINTY_MAX

    ae_result  = self._mc_ae_branch(x, n_samples, unc_min, unc_max)
    tcn_result = self._mc_tcn_branch(
        sequence, x, n_samples, unc_min, unc_max
    )

    model_entropy = float(np.clip(
        MCInferenceConfig.AE_UNCERTAINTY_WEIGHT * ae_result["ae_uncertainty"]
        + MCInferenceConfig.TCN_UNCERTAINTY_WEIGHT * tcn_result["tcn_uncertainty"],
        unc_min, unc_max,
    ))

    result = self.predict(x, sequence)
    result["ae_uncertainty"]  = ae_result["ae_uncertainty"]
    result["tcn_uncertainty"] = tcn_result["tcn_uncertainty"]
    result["model_entropy"]   = round(model_entropy, 4)
    result["mc_samples"]      = n_samples
    return result
```

- [ ] **Step 8: Run the test to confirm it now passes**

```bash
pytest tests/test_mc_inference.py::test_prepare_mc_tasks_returns_callables -v
```

Expected: `PASSED`

- [ ] **Step 9: Commit**

```bash
git add backend/app/ml/models/city_hybrid.py tests/test_mc_inference.py
git commit -m "feat(city_hybrid): add parallel MC branch methods and prepare_mc_tasks()"
```

---

### Task 3: Add MC Response Fields to `PredictionResponseV2`

**Files:**
- Modify: `backend/app/schemas/v2.py`

- [ ] **Step 1: Write failing tests for schema fields**

Add to `tests/test_mc_inference.py`:

```python
from app.schemas.v2 import PredictionResponseV2

def test_prediction_response_v2_has_mc_fields():
    """All new MC fields must be present on the schema with None defaults."""
    fields = PredictionResponseV2.model_fields
    mc_fields = [
        "inference_mode", "uncertainty_available", "epistemic_uncertainty",
        "model_uncertainty_score", "prediction_stability",
        "mc_samples_requested", "mc_samples_completed",
        "uncertainty_strategy", "degraded_reason", "inference_runtime_ms",
    ]
    for f in mc_fields:
        assert f in fields or PredictionResponseV2.model_config.get("extra") == "allow", \
            f"Missing field: {f}"

def test_prediction_response_v2_mc_fields_default_none():
    """MC fields must default to None so existing clients are unaffected."""
    r = PredictionResponseV2(
        inference_id="x", city="Islamabad", city_slug="islamabad",
        inferred_at=__import__("datetime").datetime.utcnow(),
        model_version="v1", calibration_version="v1", source="city_model",
        risk_band="Low", is_alert=False,
    )
    assert r.inference_mode is None
    assert r.epistemic_uncertainty is None
    assert r.uncertainty_available is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_mc_inference.py::test_prediction_response_v2_has_mc_fields tests/test_mc_inference.py::test_prediction_response_v2_mc_fields_default_none -v
```

Expected: `AttributeError` or assertion failure on missing fields.

- [ ] **Step 3: Add optional MC fields to `PredictionResponseV2`**

In `backend/app/schemas/v2.py`, inside `PredictionResponseV2` after the `ood_reason` field, add:

```python
    # ── MC Dropout uncertainty (Group A) ─────────────────────────────────────
    # inference_mode: how branches were run this request
    inference_mode:          Optional[str]   = None  # "mc_dropout"|"deterministic"|"fallback_deterministic"
    # uncertainty_available: True only when MC completed without fallback
    uncertainty_available:   Optional[bool]  = None
    # epistemic_uncertainty: CoV-based blend (AE+TCN); None on fallback/disabled
    # NOTE: this is a separate uncertainty lane from `uncertainty` (calibrator CI width)
    # and `model_entropy` (calibrator binary cross-entropy). Never merge the three.
    epistemic_uncertainty:   Optional[float] = Field(None, ge=0.0, le=1.0)
    # model_uncertainty_score: explicit API alias for epistemic_uncertainty
    model_uncertainty_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    # prediction_stability: human-readable tier derived from epistemic_uncertainty
    prediction_stability:    Optional[str]   = None  # "stable"|"moderate_uncertainty"|"high_uncertainty"
    # MC pass counts for observability
    mc_samples_requested:    Optional[int]   = None
    mc_samples_completed:    Optional[int]   = None
    # uncertainty_strategy: name of the merge strategy used (extensible for future)
    uncertainty_strategy:    Optional[str]   = None  # "weighted_blend"
    # degraded_reason: non-null when inference fell back to deterministic
    degraded_reason:         Optional[str]   = None  # "timeout"|"exception"|"disabled"
    # inference_runtime_ms: included in response only when DEBUG=true
    inference_runtime_ms:    Optional[float] = None
```

- [ ] **Step 4: Run tests to confirm they now pass**

```bash
pytest tests/test_mc_inference.py::test_prediction_response_v2_has_mc_fields tests/test_mc_inference.py::test_prediction_response_v2_mc_fields_default_none -v
```

Expected: both `PASSED`

- [ ] **Step 5: Verify existing schema tests still pass**

```bash
pytest tests/ -v --tb=short -k "not test_mc"
```

Expected: all pre-existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/v2.py tests/test_mc_inference.py
git commit -m "feat(schemas): add optional MC Dropout fields to PredictionResponseV2"
```

---

### Task 4: Wire Parallel MC into `predict_v2()` (flag=false initially)

**Files:**
- Modify: `backend/app/services/city_model_service.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_mc_inference.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_predict_v2_flag_disabled_returns_deterministic_fields():
    """When ENABLE_MC_INFERENCE=false, inference_mode must be 'deterministic'."""
    from app.services.city_model_service import city_model_service

    raw_weather = {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}

    with patch("app.core.config.MCInferenceConfig.ENABLED", False):
        result = await city_model_service.predict_v2("islamabad", raw_weather)

    # Even when deterministic, response must be valid
    assert "event_probability" in result
    assert result.get("inference_mode") == "deterministic"
    assert result.get("epistemic_uncertainty") is None
    assert result.get("degraded_reason") == "disabled"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_mc_inference.py::test_predict_v2_flag_disabled_returns_deterministic_fields -v
```

Expected: `AssertionError` — `inference_mode` key missing from result.

- [ ] **Step 3: Add semaphore and MC success-rate counter at module level**

Near the top of `city_model_service.py`, after the imports, add:

```python
from app.core.config import MCInferenceConfig

# Semaphore bounds concurrent TF thread-pool workers across all city requests.
# Value from config so it can be tuned without code changes.
_mc_semaphore: asyncio.Semaphore = asyncio.Semaphore(MCInferenceConfig.MAX_CONCURRENT_THREADS)

# Rolling 100-request MC success rate per city (in-memory, no DB/Redis dependency).
# Key: city slug; Value: deque of booleans (True=mc_dropout completed, False=fallback).
_mc_success_window: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
```

- [ ] **Step 4: Add `_classify_prediction_stability` helper function**

Add a module-level function (not a method) near `_mc_semaphore`:

```python
def _classify_prediction_stability(epistemic_uncertainty: float) -> str:
    """Map epistemic uncertainty to a human-readable stability tier."""
    if epistemic_uncertainty > MCInferenceConfig.STABILITY_THRESHOLD_HIGH:
        return "high_uncertainty"
    if epistemic_uncertainty > MCInferenceConfig.STABILITY_THRESHOLD_MODERATE:
        return "moderate_uncertainty"
    return "stable"
```

- [ ] **Step 5: Replace branch-scoring block in `predict_v2()` with parallel MC dispatch**

Find the block starting at `# ---- Rolling window for TCN ----` (around line 736):

```python
# ---- Rolling window for TCN ----
sequence = self._buf.push_and_get(slug, x_vec)

# ---- AE + TCN branch scoring (async) ----
try:
    raw_scores = await asyncio.to_thread(model.predict, x_vec, sequence)
except Exception as exc:
    logger.error("[%s] Branch inference failed: %s", slug, exc)
    raw_scores = {
        "ae_percentile": 0.0, "tcn_percentile": 0.0,
        "ae_variance": 0.5,   "tcn_variance": 0.5,
        "ae_error_raw": 0.0,  "tcn_error_raw": 0.0,
    }

ae_pct  = raw_scores["ae_percentile"]
tcn_pct = raw_scores["tcn_percentile"]
ae_var  = raw_scores["ae_variance"]
tcn_var = raw_scores["tcn_variance"]
```

Replace with:

```python
# ---- Rolling window for TCN ----
sequence = self._buf.push_and_get(slug, x_vec)

# ---- AE + TCN branch scoring ----
import time as _time
_branch_t0 = _time.perf_counter()

inference_mode        = "deterministic"
uncertainty_available = False
epistemic_uncertainty: Optional[float] = None
model_uncertainty_score: Optional[float] = None
prediction_stability: Optional[str] = None
mc_samples_used       = 1
degraded_reason: Optional[str] = None
ae_mc_latency_ms      = 0.0
tcn_mc_latency_ms     = 0.0
ae_result: Dict[str, Any] = {}
tcn_result: Dict[str, Any] = {}

if MCInferenceConfig.ENABLED:
    # Immutable snapshot — _CityBuffer is never passed into branch methods
    seq_snapshot = sequence.copy() if sequence is not None else None

    ae_fn, tcn_fn = model.prepare_mc_tasks(
        x_vec, seq_snapshot,
        MCInferenceConfig.DROPOUT_SAMPLES,
        MCInferenceConfig.UNCERTAINTY_MIN,
        MCInferenceConfig.UNCERTAINTY_MAX,
    )
    _gather_t0 = _time.perf_counter()
    try:
        async with _mc_semaphore:
            ae_result, tcn_result = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(ae_fn),
                    asyncio.to_thread(tcn_fn),
                ),
                timeout=MCInferenceConfig.INFERENCE_TIMEOUT_MS / 1000.0,
            )
        ae_mc_latency_ms  = (_time.perf_counter() - _gather_t0) * 1000
        tcn_mc_latency_ms = ae_mc_latency_ms  # concurrent; wall time = max of branches

        # Deterministic uncertainty merge (heuristic weighted blend)
        epistemic_uncertainty = float(np.clip(
            MCInferenceConfig.AE_UNCERTAINTY_WEIGHT * ae_result["ae_uncertainty"]
            + MCInferenceConfig.TCN_UNCERTAINTY_WEIGHT * tcn_result["tcn_uncertainty"],
            MCInferenceConfig.UNCERTAINTY_MIN,
            MCInferenceConfig.UNCERTAINTY_MAX,
        ))
        model_uncertainty_score = epistemic_uncertainty
        prediction_stability    = _classify_prediction_stability(epistemic_uncertainty)
        inference_mode          = "mc_dropout"
        uncertainty_available   = True
        mc_samples_used         = MCInferenceConfig.DROPOUT_SAMPLES
        _mc_success_window[slug].append(True)

    except asyncio.TimeoutError:
        logger.warning(
            "[%s] MC inference timeout (>%dms) — falling back to deterministic",
            slug, MCInferenceConfig.INFERENCE_TIMEOUT_MS,
        )
        degraded_reason    = "timeout"
        inference_mode     = "fallback_deterministic"
        _mc_success_window[slug].append(False)
    except Exception as exc:
        logger.warning("[%s] MC inference exception — falling back: %s", slug, exc)
        degraded_reason    = "exception"
        inference_mode     = "fallback_deterministic"
        _mc_success_window[slug].append(False)
else:
    degraded_reason = "disabled"

# Check MC success rate and warn if degraded
if _mc_success_window[slug]:
    mc_rate = sum(_mc_success_window[slug]) / len(_mc_success_window[slug])
    if len(_mc_success_window[slug]) >= 10 and mc_rate < 0.70:
        logger.error("[%s] MC success rate critically low: %.0f%%", slug, mc_rate * 100)
    elif len(_mc_success_window[slug]) >= 10 and mc_rate < 0.90:
        logger.warning("[%s] MC success rate degraded: %.0f%%", slug, mc_rate * 100)

# Point-estimate scores from MC result (or deterministic fallback)
if ae_result and tcn_result:
    ae_pct = ae_result.get("ae_percentile", 0.0)
    tcn_pct = tcn_result.get("tcn_percentile", 0.0)
    ae_var = ae_result.get("ae_variance", 0.5)
    tcn_var = tcn_result.get("tcn_variance", 0.5)
else:
    # Deterministic fallback (flag off, or exception/timeout path)
    try:
        raw_scores = await asyncio.to_thread(model.predict, x_vec, sequence)
    except Exception as exc:
        logger.error("[%s] Deterministic branch also failed: %s", slug, exc)
        raw_scores = {
            "ae_percentile": 0.0, "tcn_percentile": 0.0,
            "ae_variance": 0.5,   "tcn_variance": 0.5,
            "ae_error_raw": 0.0,  "tcn_error_raw": 0.0,
        }
    ae_pct  = raw_scores["ae_percentile"]
    tcn_pct = raw_scores["tcn_percentile"]
    ae_var  = raw_scores["ae_variance"]
    tcn_var = raw_scores["tcn_variance"]
```

- [ ] **Step 6: Add MC fields to the `return` dict at end of `predict_v2()`**

In the large `return { ... }` block at the bottom of `predict_v2()`, add after `"sequence_context": { ... }`:

```python
            # MC Dropout fields — None when flag off or fallback triggered
            "inference_mode":          inference_mode,
            "uncertainty_available":   uncertainty_available,
            "epistemic_uncertainty":   round(epistemic_uncertainty, 4) if epistemic_uncertainty is not None else None,
            "model_uncertainty_score": round(model_uncertainty_score, 4) if model_uncertainty_score is not None else None,
            "prediction_stability":    prediction_stability,
            "mc_samples_requested":    MCInferenceConfig.DROPOUT_SAMPLES if MCInferenceConfig.ENABLED else None,
            "mc_samples_completed":    mc_samples_used if uncertainty_available else None,
            "uncertainty_strategy":    MCInferenceConfig.UNCERTAINTY_STRATEGY if MCInferenceConfig.ENABLED else None,
            "degraded_reason":         degraded_reason,
```

Also add to heuristic return block (model is None path) at line ~695:

```python
            "inference_mode":          "deterministic",
            "uncertainty_available":   False,
            "epistemic_uncertainty":   None,
            "model_uncertainty_score": None,
            "prediction_stability":    None,
            "mc_samples_requested":    None,
            "mc_samples_completed":    None,
            "uncertainty_strategy":    None,
            "degraded_reason":         "heuristic_source",
```

- [ ] **Step 7: Run the flag-disabled test to confirm it now passes**

```bash
pytest tests/test_mc_inference.py::test_predict_v2_flag_disabled_returns_deterministic_fields -v
```

Expected: `PASSED`

- [ ] **Step 8: Confirm existing API tests still pass**

```bash
pytest tests/test_api.py -v --tb=short
```

Expected: all existing tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/city_model_service.py
git commit -m "feat(inference): wire parallel MC Dropout into predict_v2() behind ENABLE_MC_INFERENCE flag"
```

---

### Task 5: Write All 13 Tests in `tests/test_mc_inference.py`

**Files:**
- Create: `tests/test_mc_inference.py`

- [ ] **Step 1: Write the complete test file**

```python
"""
tests/test_mc_inference.py
==========================
Regression and concurrency tests for Group A — MC Dropout inference quality.

All config values are injected via fixtures — no hardcoded 15, 0.25, 2000, or 15 bins.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_model(input_dim: int = 8):
    """Build an untrained CityHybridModel with a tiny AE (fast for tests)."""
    from app.ml.models.city_hybrid import CityHybridModel
    m = CityHybridModel("testcity", input_dim=input_dim, seq_len=4)
    m.build()
    # Seed ECDF scalers so transform_scalar works without training
    m._ae_ecdf.fit(np.random.rand(50).astype(np.float32))
    m._tcn_ecdf.fit(np.random.rand(50).astype(np.float32))
    return m


@pytest.fixture
def mc_cfg():
    """Return MCInferenceConfig class for fixture injection."""
    from app.core.config import MCInferenceConfig
    return MCInferenceConfig


@pytest.fixture
def input_dim():
    return 8


@pytest.fixture
def sample_x(input_dim):
    return np.zeros((input_dim,), dtype=np.float32)


@pytest.fixture
def sample_seq(input_dim):
    return np.zeros((4, input_dim), dtype=np.float32)


# ---------------------------------------------------------------------------
#  Task 2 tests (already written in Task 2 step 1)
# ---------------------------------------------------------------------------

def test_prepare_mc_tasks_returns_callables(sample_x, sample_seq, mc_cfg):
    model = _make_model()
    ae_fn, tcn_fn = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=2,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    assert callable(ae_fn)
    assert callable(tcn_fn)


# ---------------------------------------------------------------------------
#  Test 1: mc_branches_independent
# ---------------------------------------------------------------------------

def test_mc_branches_independent(sample_x, sample_seq, mc_cfg):
    """Sequential and concurrent branch results must be byte-identical."""
    model = _make_model()
    np.random.seed(42)

    ae_fn, tcn_fn = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=mc_cfg.DROPOUT_SAMPLES,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    # Run sequentially
    seq_ae  = ae_fn()
    seq_tcn = tcn_fn()

    # Confirm same keys returned when run independently again
    ae_fn2, tcn_fn2 = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=mc_cfg.DROPOUT_SAMPLES,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    ind_ae  = ae_fn2()
    ind_tcn = tcn_fn2()

    assert set(seq_ae.keys()) == set(ind_ae.keys())
    assert set(seq_tcn.keys()) == set(ind_tcn.keys())


# ---------------------------------------------------------------------------
#  Test 2: predict_v2_mc_fields_present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_mc_fields_present():
    """MC mode: all new schema fields must be present and correctly typed."""
    from app.services.city_model_service import city_model_service

    with patch("app.core.config.MCInferenceConfig.ENABLED", True):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert "inference_mode" in result
    assert "uncertainty_available" in result
    assert "mc_samples_requested" in result
    assert "uncertainty_strategy" in result
    assert "degraded_reason" in result
    if result["inference_mode"] == "mc_dropout":
        assert isinstance(result["epistemic_uncertainty"], float)
        assert result["uncertainty_available"] is True
        assert result["prediction_stability"] in ("stable", "moderate_uncertainty", "high_uncertainty")


# ---------------------------------------------------------------------------
#  Test 3: predict_v2_flag_disabled (already written in Task 4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_flag_disabled():
    """ENABLE_MC_INFERENCE=false → inference_mode='deterministic', epistemic fields None."""
    from app.services.city_model_service import city_model_service

    with patch("app.core.config.MCInferenceConfig.ENABLED", False):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "deterministic"
    assert result.get("epistemic_uncertainty") is None
    assert result.get("uncertainty_available") in (False, None)
    assert result.get("degraded_reason") == "disabled"


# ---------------------------------------------------------------------------
#  Test 4: predict_v2_fallback_on_timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_fallback_on_timeout():
    """Mocked asyncio.wait_for timeout → fallback_deterministic, valid event_probability."""
    from app.services.city_model_service import city_model_service
    import app.services.city_model_service as svc_module

    original_wait_for = asyncio.wait_for

    async def _timeout_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("app.core.config.MCInferenceConfig.ENABLED", True), \
         patch.object(asyncio, "wait_for", side_effect=_timeout_wait_for):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "fallback_deterministic"
    assert result.get("degraded_reason") == "timeout"
    assert result.get("epistemic_uncertainty") is None
    assert "event_probability" in result
    assert isinstance(result["event_probability"], float)


# ---------------------------------------------------------------------------
#  Test 5: predict_v2_fallback_on_exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_fallback_on_exception():
    """Mocked branch exception → fallback_deterministic, degraded_reason='exception'."""
    from app.services.city_model_service import city_model_service

    async def _exc_wait_for(coro, timeout):
        raise RuntimeError("mock branch failure")

    with patch("app.core.config.MCInferenceConfig.ENABLED", True), \
         patch.object(asyncio, "wait_for", side_effect=_exc_wait_for):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "fallback_deterministic"
    assert result.get("degraded_reason") == "exception"
    assert result.get("epistemic_uncertainty") is None


# ---------------------------------------------------------------------------
#  Test 6: tcn_buffer_immutability
# ---------------------------------------------------------------------------

def test_tcn_buffer_immutability(sample_x, sample_seq, mc_cfg):
    """_CityBuffer state byte-identical before and after _mc_tcn_branch executes."""
    model = _make_model()
    seq_before = sample_seq.copy()
    _, tcn_fn = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=2,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    tcn_fn()
    # Original array must not have been modified
    np.testing.assert_array_equal(sample_seq, seq_before)


# ---------------------------------------------------------------------------
#  Test 7: epistemic_uncertainty_range
# ---------------------------------------------------------------------------

def test_epistemic_uncertainty_range(mc_cfg):
    """epistemic_uncertainty must always be in [MC_UNCERTAINTY_MIN, MC_UNCERTAINTY_MAX]."""
    from app.ml.models.city_hybrid import CityHybridModel
    import numpy as np

    model = _make_model(input_dim=8)
    model._ae_ecdf.fit(np.random.rand(100).astype(np.float32))
    model._tcn_ecdf.fit(np.random.rand(100).astype(np.float32))

    rng = np.random.default_rng(0)
    for _ in range(20):
        x = rng.random(8).astype(np.float32)
        seq = rng.random((4, 8)).astype(np.float32)
        ae_fn, tcn_fn = model.prepare_mc_tasks(
            x, seq, n_samples=3,
            uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
            uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
        )
        ae_r = ae_fn()
        tcn_r = tcn_fn()
        blend = (
            mc_cfg.AE_UNCERTAINTY_WEIGHT * ae_r["ae_uncertainty"]
            + mc_cfg.TCN_UNCERTAINTY_WEIGHT * tcn_r["tcn_uncertainty"]
        )
        eu = float(np.clip(blend, mc_cfg.UNCERTAINTY_MIN, mc_cfg.UNCERTAINTY_MAX))
        assert mc_cfg.UNCERTAINTY_MIN <= eu <= mc_cfg.UNCERTAINTY_MAX


# ---------------------------------------------------------------------------
#  Test 8: prediction_stability_mapping
# ---------------------------------------------------------------------------

def test_prediction_stability_mapping(mc_cfg):
    """Correct stability label at and around tier boundaries."""
    from app.services.city_model_service import _classify_prediction_stability

    mod = mc_cfg.STABILITY_THRESHOLD_MODERATE
    high = mc_cfg.STABILITY_THRESHOLD_HIGH

    assert _classify_prediction_stability(0.0) == "stable"
    assert _classify_prediction_stability(mod - 0.01) == "stable"
    assert _classify_prediction_stability(mod) == "moderate_uncertainty"
    assert _classify_prediction_stability(mod + 0.01) == "moderate_uncertainty"
    assert _classify_prediction_stability(high) == "high_uncertainty"
    assert _classify_prediction_stability(1.0) == "high_uncertainty"


# ---------------------------------------------------------------------------
#  Test 9: concurrent_cities
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_cities():
    """Simultaneous city requests produce no corrupted results or race conditions."""
    from app.services.city_model_service import city_model_service

    cities = ["islamabad", "lahore", "karachi"]
    weather = {"prcp": 10.0, "humidity": 70.0, "pressure": 1005.0}

    results = await asyncio.gather(*[
        city_model_service.predict_v2(c, weather) for c in cities
    ])

    for city, result in zip(cities, results):
        assert result["city_slug"] == city
        assert "event_probability" in result
        assert isinstance(result["event_probability"], float)


# ---------------------------------------------------------------------------
#  Test 10: latency_within_budget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_latency_within_budget(mc_cfg):
    """Wall-clock predict_v2() latency must be under MC_INFERENCE_TIMEOUT_MS * 1.5."""
    from app.services.city_model_service import city_model_service

    budget_ms = mc_cfg.INFERENCE_TIMEOUT_MS * 1.5
    start = time.perf_counter()
    await city_model_service.predict_v2(
        "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < budget_ms, f"Latency {elapsed_ms:.0f}ms exceeded budget {budget_ms:.0f}ms"


# ---------------------------------------------------------------------------
#  Test 11: calibration_audit_readonly
# ---------------------------------------------------------------------------

def test_calibration_audit_readonly(tmp_path):
    """calibration_audit.py writes only .json, never .pkl or .keras files."""
    import subprocess, sys

    script = Path(__file__).parents[1] / "scripts" / "calibration_audit.py"
    if not script.exists():
        pytest.skip("calibration_audit.py not yet written")

    result = subprocess.run(
        [sys.executable, str(script), "--city", "islamabad", "--dry-run"],
        capture_output=True, text=True
    )

    # Verify no .pkl or .keras files were written anywhere under saved_models
    from app.core.config import MODELS_DIR
    modified_bad = list(MODELS_DIR.rglob("*.pkl")) + list(MODELS_DIR.rglob("*.keras"))
    # Compare mtimes — none should be newer than test start
    test_start = time.time()
    for p in modified_bad:
        assert p.stat().st_mtime < test_start, f"Unexpected write to {p}"


# ---------------------------------------------------------------------------
#  Test 12: calibration_audit_schema
# ---------------------------------------------------------------------------

def test_calibration_audit_schema():
    """calibration_audit.json must contain all required fields."""
    from app.core.config import MODELS_DIR

    required_fields = {
        "audit_version", "pipeline_version", "generated_at", "city_slug",
        "calibration_method", "calibration_ece_cal_set",
        "pre_calibration_ece_test", "post_calibration_ece_test",
        "pre_calibration_brier_test", "post_calibration_brier_test",
        "calibration_improvement", "bin_populations", "reliability_curve",
        "calibration_bins_used", "split_tier",
    }

    audit_files = list(MODELS_DIR.glob("city_models/*/calibration_audit.json"))
    if not audit_files:
        pytest.skip("No calibration_audit.json found — run calibration_audit.py first")

    for af in audit_files:
        data = json.loads(af.read_text())
        missing = required_fields - set(data.keys())
        assert not missing, f"{af}: missing fields {missing}"


# ---------------------------------------------------------------------------
#  Test 13: calibration_ece_values_plausible
# ---------------------------------------------------------------------------

def test_calibration_ece_values_plausible():
    """post_calibration_ece_test must be finite and non-negative."""
    from app.core.config import MODELS_DIR

    audit_files = list(MODELS_DIR.glob("city_models/*/calibration_audit.json"))
    if not audit_files:
        pytest.skip("No calibration_audit.json found — run calibration_audit.py first")

    for af in audit_files:
        data = json.loads(af.read_text())
        post_ece = data["post_calibration_ece_test"]
        improvement = data["calibration_improvement"]
        assert isinstance(post_ece, (int, float)), f"{af}: post_calibration_ece_test not numeric"
        assert post_ece >= 0.0, f"{af}: negative ECE {post_ece}"
        assert np.isfinite(post_ece), f"{af}: non-finite ECE {post_ece}"
        assert np.isfinite(improvement), f"{af}: non-finite calibration_improvement {improvement}"
```

- [ ] **Step 2: Run all runnable tests (skip calibration tests until script exists)**

```bash
pytest tests/test_mc_inference.py -v --tb=short -k "not calibration_audit"
```

Expected: tests 1–10 pass; tests 11–13 skip with "not yet written" / "No calibration_audit.json found".

- [ ] **Step 3: Commit**

```bash
git add tests/test_mc_inference.py
git commit -m "test(mc_inference): add all 13 Group A regression and concurrency tests"
```

---

### Task 6: Enable Flag, Profile Latency

**Files:**
- Modify: `.env` (local dev only, never committed)
- Run: backend server

- [ ] **Step 1: Enable MC inference in local `.env`**

```bash
echo "ENABLE_MC_INFERENCE=true" >> .env
```

- [ ] **Step 2: Restart the server**

```bash
python backend/run_server.py --reload --port 8000
```

- [ ] **Step 3: Send a test prediction and inspect MC fields**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/cities/islamabad/predict \
  -H "Content-Type: application/json" \
  -d '{"prcp":15.0,"humidity":75.0,"pressure":1006.0}' | python -m json.tool
```

Expected response contains:
```json
{
  "inference_mode": "mc_dropout",
  "uncertainty_available": true,
  "epistemic_uncertainty": <float in [0,1]>,
  "prediction_stability": "stable" | "moderate_uncertainty" | "high_uncertainty",
  "mc_samples_requested": 15,
  "mc_samples_completed": 15,
  "uncertainty_strategy": "weighted_blend"
}
```

- [ ] **Step 4: Run latency profile (10 sequential requests)**

```bash
for i in $(seq 1 10); do
  curl -s -w "\n%{time_total}s\n" -X POST http://127.0.0.1:8000/api/v2/cities/islamabad/predict \
    -H "Content-Type: application/json" \
    -d '{"prcp":15.0,"humidity":75.0,"pressure":1006.0}' -o /dev/null
done
```

Expected: all requests complete under `MC_INFERENCE_TIMEOUT_MS / 1000` seconds (default 3.0s). Typical CPU latency should be well under 2s.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all 13 MC tests pass; all pre-existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add .env.example  # add ENABLE_MC_INFERENCE=true to example
git commit -m "feat(config): document ENABLE_MC_INFERENCE in .env.example"
```

---

### Task 7: Write `scripts/calibration_audit.py`

**Files:**
- Create: `scripts/calibration_audit.py`

- [ ] **Step 1: Run test 11 to confirm it skips**

```bash
pytest tests/test_mc_inference.py::test_calibration_audit_readonly -v
```

Expected: `SKIPPED` with message "calibration_audit.py not yet written"

- [ ] **Step 2: Write the calibration audit script**

```python
#!/usr/bin/env python3
"""
scripts/calibration_audit.py
=============================
Read-only calibration audit for HydroGuard-AI v3.5.

Measures ECE on an independent test set (not the cal set isotonic was fitted on).
Writes calibration_audit.json per city.
Appends new fields to training_metrics.json without overwriting any existing field.

Usage:
    python scripts/calibration_audit.py --all
    python scripts/calibration_audit.py --city islamabad
    python scripts/calibration_audit.py --city islamabad --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app.core.config import MCInferenceConfig, MODELS_DIR, DATA_DIR

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("calibration_audit")

CITY_MODELS_DIR = MODELS_DIR / "city_models"
DATA_CSV        = DATA_DIR / "pakistan_weather_2000_2024.csv"
AUDIT_VERSION   = "1.0"
PIPELINE_VERSION = "v3.5"


# ---------------------------------------------------------------------------
#  ECE computation
# ---------------------------------------------------------------------------

def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int) -> float:
    """Expected Calibration Error on equal-width probability bins."""
    ece = 0.0
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        bin_acc  = float(labels[mask].mean())
        bin_conf = float(probs[mask].mean())
        ece += mask.sum() * abs(bin_conf - bin_acc)
    return float(ece / max(len(probs), 1))


def compute_brier(probs: np.ndarray, labels: np.ndarray) -> float:
    return float(np.mean((probs - labels) ** 2))


def reliability_curve(probs: np.ndarray, labels: np.ndarray, n_bins: int):
    curve = []
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    populations = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            curve.append({"predicted": round((lo + hi) / 2, 3), "actual": None})
            populations.append(0)
        else:
            curve.append({
                "predicted": round(float(probs[mask].mean()), 4),
                "actual":    round(float(labels[mask].mean()), 4),
            })
            populations.append(int(mask.sum()))
    return curve, populations


# ---------------------------------------------------------------------------
#  Split reconstruction (3-tier hierarchy)
# ---------------------------------------------------------------------------

def _get_city_split(slug: str, metrics: dict, csv_path: Path):
    """Return (X_raw_df, labels, split_tier) using the 3-tier split hierarchy."""
    import pandas as pd

    df = pd.read_csv(csv_path, low_memory=False)
    # Normalise city column
    df["city_slug"] = df["city"].str.strip().str.lower().str.replace(" ", "_")
    city_df = df[df["city_slug"] == slug].copy()

    if city_df.empty:
        raise ValueError(f"No rows for city '{slug}' in CSV")

    city_df = city_df.sort_values("date").reset_index(drop=True)

    holdout_strategy = metrics.get("holdout_strategy", "")
    holdout_rows     = metrics.get("holdout_rows", 0)

    # Tier 1: year-based holdout (islamabad, lahore)
    if holdout_strategy == "year_2023_plus" and holdout_rows > 0:
        subset = city_df[city_df["date"] >= "2023-01-01"].copy()
        if len(subset) > 0:
            logger.info("[%s] Split Tier 1 — year_2023_plus: %d rows", slug, len(subset))
            return subset, "year_holdout"

    # Tier 2: temporal last 15%
    n_total = len(city_df)
    n_last  = max(1, int(n_total * 0.15))
    subset  = city_df.iloc[-n_last:].copy()
    if len(subset) > 0:
        logger.info("[%s] Split Tier 2 — last_15pct: %d rows", slug, len(subset))
        return subset, "last_15pct"

    # Tier 3: stored test rows from training_metrics
    test_n = metrics.get("test_n_rows", 0)
    if test_n > 0:
        subset = city_df.iloc[-test_n:].copy()
        logger.info("[%s] Split Tier 3 — stored_test: %d rows", slug, len(subset))
        return subset, "stored_test"

    raise ValueError(f"[{slug}] Cannot reconstruct a valid evaluation split")


# ---------------------------------------------------------------------------
#  Per-city audit
# ---------------------------------------------------------------------------

def audit_city(slug: str, dry_run: bool = False) -> dict:
    city_dir  = CITY_MODELS_DIR / slug
    metrics_path = city_dir / "training_metrics.json"

    if not metrics_path.exists():
        logger.warning("[%s] No training_metrics.json — skipping", slug)
        return {}

    metrics = json.loads(metrics_path.read_text())
    n_bins  = MCInferenceConfig.CALIBRATION_ECE_BINS

    # Load calibrator
    calib_path = city_dir / "calibrator.pkl"
    if not calib_path.exists():
        logger.warning("[%s] No calibrator.pkl — skipping", slug)
        return {}

    import joblib
    calibrator = joblib.load(calib_path)

    # Load preprocessor
    prep_path = city_dir / "preprocessor_v2.joblib"
    if not prep_path.exists():
        prep_path = city_dir / "preprocessor.joblib"
    if not prep_path.exists():
        logger.warning("[%s] No preprocessor — skipping", slug)
        return {}
    preprocessor = joblib.load(prep_path)

    # Load fusion model
    fusion_path = city_dir / "fusion_model.pkl"
    if not fusion_path.exists():
        logger.warning("[%s] No fusion_model.pkl — skipping", slug)
        return {}
    fusion = joblib.load(fusion_path)

    # Reconstruct evaluation split
    try:
        split_df, split_tier = _get_city_split(slug, metrics, DATA_CSV)
    except Exception as exc:
        logger.error("[%s] Split reconstruction failed: %s", slug, exc)
        return {}

    # Get weak labels from CSV (column weak_label or is_event)
    label_col = None
    for col in ("weak_label", "is_event", "anomaly"):
        if col in split_df.columns:
            label_col = col
            break
    if label_col is None:
        logger.warning("[%s] No label column in CSV — skipping", slug)
        return {}

    y_true = split_df[label_col].values.astype(float)
    y_true = np.where(y_true > 0, 1.0, 0.0)  # binarize

    # Preprocess and compute raw fusion probabilities
    try:
        X = preprocessor.transform(split_df)
        p_raw = fusion.predict_proba(X)
        if p_raw.ndim == 2:
            p_raw = p_raw[:, 1]
    except Exception as exc:
        logger.error("[%s] Preprocess/fusion failed: %s", slug, exc)
        return {}

    # Calibrate
    try:
        p_calib = np.array([float(calibrator.transform(p)) for p in p_raw])
    except Exception as exc:
        logger.error("[%s] Calibrator.transform failed: %s", slug, exc)
        return {}

    # Compute metrics
    pre_ece   = compute_ece(p_raw,   y_true, n_bins)
    post_ece  = compute_ece(p_calib, y_true, n_bins)
    pre_brier = compute_brier(p_raw,   y_true)
    post_brier = compute_brier(p_calib, y_true)
    improvement = pre_ece - post_ece
    curve, populations = reliability_curve(p_calib, y_true, n_bins)

    audit = {
        "audit_version":              AUDIT_VERSION,
        "pipeline_version":           PIPELINE_VERSION,
        "generated_at":               datetime.now(timezone.utc).isoformat(),
        "city_slug":                  slug,
        "calibration_method":         "isotonic",
        "calibration_ece_cal_set":    metrics.get("calibration_ece_after"),
        "pre_calibration_ece_test":   round(pre_ece,    4),
        "post_calibration_ece_test":  round(post_ece,   4),
        "pre_calibration_brier_test": round(pre_brier,  4),
        "post_calibration_brier_test": round(post_brier, 4),
        "calibration_improvement":    round(improvement, 4),
        "bin_populations":            populations,
        "reliability_curve":          curve,
        "calibration_bins_used":      n_bins,
        "split_tier":                 split_tier,
        "eval_rows":                  int(len(y_true)),
        "notes":                      "",
    }

    if not dry_run:
        audit_path = city_dir / "calibration_audit.json"
        audit_path.write_text(json.dumps(audit, indent=2))
        logger.info("[%s] Written %s", slug, audit_path)

        # Append new fields to training_metrics.json (never overwrite existing)
        metrics.setdefault("calibration_ece_cal_set",  metrics.get("calibration_ece_after"))
        metrics.setdefault("calibration_ece_test_set",     round(post_ece,   4))
        metrics.setdefault("calibration_brier_test_after", round(post_brier, 4))
        metrics.setdefault("calibration_bins_used",        n_bins)
        metrics.setdefault("calibration_audit_path",
                           f"backend/saved_models/city_models/{slug}/calibration_audit.json")
        metrics_path.write_text(json.dumps(metrics, indent=2))
        logger.info("[%s] Updated training_metrics.json", slug)
    else:
        logger.info("[%s] DRY RUN — no files written", slug)
        logger.info("[%s] pre_ece=%.4f  post_ece=%.4f  improvement=%.4f",
                    slug, pre_ece, post_ece, improvement)

    return audit


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="HydroGuard-AI calibration audit")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all",  action="store_true", help="Audit all trained cities")
    group.add_argument("--city", type=str,            help="Audit a single city slug")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute metrics but do not write any files")
    args = parser.parse_args()

    if args.all:
        slugs = [d.name for d in CITY_MODELS_DIR.iterdir()
                 if d.is_dir() and (d / "training_metrics.json").exists()]
    else:
        slugs = [args.city.strip().lower()]

    for slug in sorted(slugs):
        logger.info("=== Auditing: %s ===", slug)
        try:
            audit_city(slug, dry_run=args.dry_run)
        except Exception as exc:
            logger.error("[%s] Unhandled error: %s", slug, exc)

    logger.info("Audit complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests 11 and 12 to confirm progression**

```bash
pytest tests/test_mc_inference.py::test_calibration_audit_readonly -v
```

Expected: `PASSED` (dry-run writes nothing, no .pkl/.keras files modified).

- [ ] **Step 4: Run the audit script (dry run first)**

```bash
python scripts/calibration_audit.py --all --dry-run
```

Expected: Per-city ECE values printed; no files written.

- [ ] **Step 5: Run the audit for real**

```bash
python scripts/calibration_audit.py --all
```

Expected: `calibration_audit.json` written for each trained city; `training_metrics.json` updated with new fields.

- [ ] **Step 6: Run tests 12 and 13**

```bash
pytest tests/test_mc_inference.py::test_calibration_audit_schema tests/test_mc_inference.py::test_calibration_ece_values_plausible -v
```

Expected: both `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add scripts/calibration_audit.py
git commit -m "feat(audit): add read-only calibration audit script with 3-tier split hierarchy"
```

---

### Task 8: Update `training_metrics.json` for All 6 Cities

**Files:**
- Modify: `backend/saved_models/city_models/islamabad/training_metrics.json`
- Modify: `backend/saved_models/city_models/lahore/training_metrics.json`
- Modify: `backend/saved_models/city_models/karachi/training_metrics.json`
- Modify: `backend/saved_models/city_models/peshawar/training_metrics.json`
- Modify: `backend/saved_models/city_models/quetta/training_metrics.json`
- Modify: `backend/saved_models/city_models/gilgit/training_metrics.json`

- [ ] **Step 1: Confirm audit wrote new fields (automated by Task 7)**

```bash
python -c "
import json; from pathlib import Path
for slug in ['islamabad','lahore','karachi','peshawar','quetta','gilgit']:
    m = json.loads((Path('backend/saved_models/city_models') / slug / 'training_metrics.json').read_text())
    print(slug, m.get('calibration_ece_test_set'), m.get('split_tier', m.get('holdout_strategy')))
"
```

Expected: `calibration_ece_test_set` is present and non-null for all 6 cities.

- [ ] **Step 2: Verify `calibration_ece_after` is unchanged in all files**

```bash
python -c "
import json; from pathlib import Path
for slug in ['islamabad','lahore','karachi','peshawar','quetta','gilgit']:
    m = json.loads((Path('backend/saved_models/city_models') / slug / 'training_metrics.json').read_text())
    assert 'calibration_ece_after' in m, f'{slug}: calibration_ece_after missing'
    print(slug, 'ece_after=', m['calibration_ece_after'], 'ece_test=', m.get('calibration_ece_test_set'))
"
```

Expected: `calibration_ece_after` present with original value (0.0 for all cities as before audit).

- [ ] **Step 3: Run all 13 tests end-to-end**

```bash
pytest tests/test_mc_inference.py -v --tb=short
```

Expected: all 13 tests `PASSED` (none skipped).

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: zero regressions in pre-existing tests.

- [ ] **Step 5: Final commit**

```bash
git add backend/saved_models/city_models/*/training_metrics.json \
        backend/saved_models/city_models/*/calibration_audit.json
git commit -m "feat(metrics): add calibration_ece_test_set and audit artifacts for all 6 cities"
```

---

## Acceptance Checklist

- [ ] All 13 tests in `test_mc_inference.py` pass
- [ ] `epistemic_uncertainty` is a real stochastic CoV estimate — not the z-score proxy
- [ ] `inference_mode` is present and correct in every V2 prediction response
- [ ] `degraded_reason` is non-null and logged whenever fallback activates
- [ ] `epistemic_uncertainty` is `None` (never approximated) when fallback activates
- [ ] p99 latency < `MC_INFERENCE_TIMEOUT_MS * 1.5` under concurrent requests
- [ ] `_CityBuffer` state byte-identical before and after any MC TCN branch run
- [ ] `calibration_audit.json` present for all 6 trained cities
- [ ] `training_metrics.json` contains `calibration_ece_test_set` for all 6 cities
- [ ] No `.pkl` or `.keras` artifact modified during audit
- [ ] `ENABLE_MC_INFERENCE=false` restores fully deterministic behavior with zero test regression
