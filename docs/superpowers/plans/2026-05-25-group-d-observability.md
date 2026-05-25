# Group D Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add runtime health telemetry to HydroGuard-AI v3.5: three background ticks that surface MC Dropout degradation, PSI drift, and epistemic uncertainty stability into the existing `/ws/health` WebSocket and the admin MonitoringScreen.

**Architecture:** A new `RuntimeHealthCollector` service holds three asyncio background tasks running at 30s/300s/3600s cadences. Each tick samples in-memory counters and the existing DriftMonitor, assembles a `SystemHealthSnapshot`, and broadcasts it via the already-defined (but never-called) `emit_health()` in `broadcast_service.py`. No new DB tables, no new Redis keys, no new routes.

**Tech Stack:** Python 3.11, FastAPI lifespan context, asyncio, Pydantic v2, React 18 + Babel-Standalone (no bundler)

---

## File Map

| Action | File | Change |
|--------|------|--------|
| Modify | `backend/app/core/config.py` | Add `HealthCollectorConfig` class after `MCInferenceConfig` |
| Modify | `.env.example` | Document `HealthCollectorConfig` env vars |
| Create | `backend/app/schemas/health.py` | `CityHealthSnapshot`, `SystemHealthSnapshot` Pydantic models |
| Modify | `backend/app/ml/drift/monitor.py` | Add `_latest_psi` dict; populate in `_check_drift()` |
| Modify | `backend/app/services/city_model_service.py` | Add 3 module-level counters + 4 accessor functions + hot-path instrumentation in `predict_v2()` |
| Create | `backend/app/services/health_collector.py` | `RuntimeHealthCollector` + `get_health_collector()` singleton |
| Modify | `backend/app/main.py` | Start/stop `RuntimeHealthCollector` in lifespan around `yield` |
| Modify | `frontend/web_dashboard/admin_dashboard/screens/others.jsx` | Add `cityHealth` prop + 6-card health grid to `MonitoringScreen` |
| Modify | `frontend/web_dashboard/admin_dashboard/app.jsx` | Add `cityHealth` state + `/ws/health` subscription |
| Create | `tests/test_health_collector.py` | Unit tests for counter accessors, snapshot builder, stability bands |

---

## Task 1: `HealthCollectorConfig` in `config.py` and `.env.example`

**Files:**
- Modify: `backend/app/core/config.py:377` (after `MCInferenceConfig` class)
- Modify: `.env.example` (append new section)
- Test: `tests/test_health_collector.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_health_collector.py`:

```python
"""Tests for Group D health collector — counters, snapshot builder, stability."""
import pytest


class TestHealthCollectorConfig:
    def test_defaults_are_sensible(self):
        from backend.app.core.config import HealthCollectorConfig as HC
        assert HC.HEALTH_TICK_INTERVAL_S == 30
        assert HC.DRIFT_TICK_INTERVAL_S == 300
        assert HC.CONFIDENCE_TICK_INTERVAL_S == 3600
        assert HC.MC_WINDOW_SIZE == 100
        assert HC.EPISTEMIC_BUFFER_SIZE == 200
        assert 0.0 < HC.MC_DEGRADED_THRESHOLD < 1.0
        assert 0.0 < HC.MC_CRITICAL_THRESHOLD < HC.MC_DEGRADED_THRESHOLD
        assert 0.0 < HC.PREPROCESS_FAIL_DEGRADED < HC.PREPROCESS_FAIL_CRITICAL
        assert HC.EPISTEMIC_WARMUP_MIN_SAMPLES >= 10
```

- [ ] **Step 2: Run to verify it fails**

```
cd D:\Programming\FYP\hydroguard_ai
pytest tests/test_health_collector.py::TestHealthCollectorConfig -v
```

Expected: `ImportError` — `HealthCollectorConfig` does not exist yet.

- [ ] **Step 3: Add `HealthCollectorConfig` to `config.py`**

In `backend/app/core/config.py`, insert the following block immediately after the `MCInferenceConfig` class (after line 376, before the `# Logging` comment at line 379):

```python
# ============================================================
#  Runtime Health Collector
# ============================================================

class HealthCollectorConfig:
    """Configuration for the three background health-tick tasks.

    All values are env-var driven — no hardcoded thresholds.
    """
    # Background tick cadences (seconds)
    HEALTH_TICK_INTERVAL_S:     int   = int(os.getenv("HEALTH_TICK_INTERVAL_S",    "30"))
    DRIFT_TICK_INTERVAL_S:      int   = int(os.getenv("DRIFT_TICK_INTERVAL_S",     "300"))
    CONFIDENCE_TICK_INTERVAL_S: int   = int(os.getenv("CONFIDENCE_TICK_INTERVAL_S","3600"))

    # Rolling window sizes (number of requests)
    MC_WINDOW_SIZE:             int   = int(os.getenv("HEALTH_MC_WINDOW_SIZE",     "100"))
    EPISTEMIC_BUFFER_SIZE:      int   = int(os.getenv("HEALTH_EPISTEMIC_BUFFER",   "200"))

    # MC success rate thresholds — fraction of recent requests that completed MC
    # (1.0 = all requests used MC dropout; lower = more timeouts/fallbacks)
    MC_DEGRADED_THRESHOLD:      float = float(os.getenv("HEALTH_MC_DEGRADED",      "0.90"))
    MC_CRITICAL_THRESHOLD:      float = float(os.getenv("HEALTH_MC_CRITICAL",      "0.70"))

    # Preprocessing failure rate thresholds — fraction of calls where feature
    # extraction raised an exception
    PREPROCESS_FAIL_DEGRADED:   float = float(os.getenv("HEALTH_FAIL_DEGRADED",    "0.05"))
    PREPROCESS_FAIL_CRITICAL:   float = float(os.getenv("HEALTH_FAIL_CRITICAL",    "0.20"))

    # Epistemic warmup: minimum successful MC inferences before 2σ/3σ stability
    # bands can be computed. City shows "warming_up" until this count is reached.
    EPISTEMIC_WARMUP_MIN_SAMPLES: int = int(os.getenv("HEALTH_EPISTEMIC_WARMUP",   "50"))
```

- [ ] **Step 4: Add `.env.example` section**

Append to `.env.example` (after the `CALIBRATION_ECE_BINS` block):

```
# ── Runtime Health Collector ───────────────────────────────────────────────────
#
#  Three background asyncio tasks sample in-memory inference counters and the
#  DriftMonitor, then broadcast a SystemHealthSnapshot to /ws/health.
#  All state is in-memory and resets on restart — no DB writes.

# Background tick cadences (seconds)
HEALTH_TICK_INTERVAL_S=30
DRIFT_TICK_INTERVAL_S=300
CONFIDENCE_TICK_INTERVAL_S=3600

# Rolling window sizes (number of requests)
# HEALTH_MC_WINDOW_SIZE: last N predict_v2 calls used for MC success/timeout rates
# HEALTH_EPISTEMIC_BUFFER: last N successful MC inferences for uncertainty stats
HEALTH_MC_WINDOW_SIZE=100
HEALTH_EPISTEMIC_BUFFER=200

# MC success rate thresholds — fraction of recent requests that completed MC dropout
# (1.0 = perfect; lower means more timeouts/fallbacks than expected)
HEALTH_MC_DEGRADED=0.90
HEALTH_MC_CRITICAL=0.70

# Preprocessing failure rate thresholds — fraction where feature extraction raised
HEALTH_FAIL_DEGRADED=0.05
HEALTH_FAIL_CRITICAL=0.20

# Epistemic warmup: min successful MC inferences before per-city stability bands
# (2σ/3σ) can be computed from the observed distribution. "warming_up" until ready.
HEALTH_EPISTEMIC_WARMUP=50
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/test_health_collector.py::TestHealthCollectorConfig -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py .env.example tests/test_health_collector.py
git commit -m "feat(group-d): HealthCollectorConfig + env docs"
```

---

## Task 2: Pydantic health schemas

**Files:**
- Create: `backend/app/schemas/health.py`
- Test: `tests/test_health_collector.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_health_collector.py`:

```python
class TestHealthSchemas:
    def test_city_health_snapshot_defaults(self):
        from backend.app.schemas.health import CityHealthSnapshot
        snap = CityHealthSnapshot(
            city_slug="islamabad",
            mc_success_rate=None,
            timeout_rate=None,
            preprocess_fail_rate=None,
            inference_health="unknown",
            psi_max=None,
            psi_status="unknown",
            top_drifted_feature=None,
            epistemic_mean=None,
            epistemic_std=None,
            epistemic_drift=None,
            epistemic_stability="warming_up",
            baseline_ready=False,
        )
        assert snap.city_slug == "islamabad"
        assert snap.inference_health == "unknown"
        assert snap.baseline_ready is False

    def test_system_health_snapshot_roundtrip(self):
        from datetime import datetime, timezone
        from backend.app.schemas.health import CityHealthSnapshot, SystemHealthSnapshot
        city = CityHealthSnapshot(
            city_slug="lahore",
            mc_success_rate=0.95,
            timeout_rate=0.05,
            preprocess_fail_rate=0.01,
            inference_health="ok",
            psi_max=0.08,
            psi_status="ok",
            top_drifted_feature="humidity",
            epistemic_mean=0.12,
            epistemic_std=0.03,
            epistemic_drift=1.2,
            epistemic_stability="stable",
            baseline_ready=True,
        )
        snap = SystemHealthSnapshot(
            snapshot_at=datetime.now(timezone.utc),
            cities={"lahore": city},
            global_status="ok",
            active_city_count=1,
        )
        payload = snap.model_dump(mode="json")
        assert payload["global_status"] == "ok"
        assert "lahore" in payload["cities"]
        assert payload["cities"]["lahore"]["mc_success_rate"] == 0.95
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_health_collector.py::TestHealthSchemas -v
```

Expected: `ModuleNotFoundError` — `backend.app.schemas.health` does not exist.

- [ ] **Step 3: Create `backend/app/schemas/health.py`**

```python
"""
HydroGuard-AI — Runtime Health Snapshot Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class CityHealthSnapshot(BaseModel):
    city_slug: str

    # Domain 1 — Inference health
    mc_success_rate:      Optional[float]   # None if < 10 observations
    timeout_rate:         Optional[float]   # None if < 10 observations
    preprocess_fail_rate: Optional[float]   # None if < 10 observations
    inference_health:     str               # "ok" | "degraded" | "critical" | "unknown"

    # Domain 2 — Drift
    psi_max:              Optional[float]   # highest PSI across monitored features
    psi_status:           str               # "ok" | "warn" | "critical" | "unknown"
    top_drifted_feature:  Optional[str]     # feature name with highest PSI

    # Domain 3 — Epistemic stability
    epistemic_mean:       Optional[float]   # mean of epistemic buffer
    epistemic_std:        Optional[float]   # std dev of epistemic buffer
    epistemic_drift:      Optional[float]   # |current_mean - warmup_mean| / warmup_std
    epistemic_stability:  str               # "warming_up" | "stable" | "drifting" | "anomalous"
    baseline_ready:       bool


class SystemHealthSnapshot(BaseModel):
    snapshot_at:        datetime
    cities:             Dict[str, CityHealthSnapshot]
    global_status:      str   # "ok" | "degraded" | "critical" | "unknown"
    active_city_count:  int
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_health_collector.py::TestHealthSchemas -v
```

Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/health.py tests/test_health_collector.py
git commit -m "feat(group-d): health snapshot Pydantic schemas"
```

---

## Task 3: Expose latest PSI results from `DriftMonitor`

**Files:**
- Modify: `backend/app/ml/drift/monitor.py:71` (`__init__`) and `:148` (`_check_drift`)
- Test: `tests/test_health_collector.py` (append)

**Context:** `_check_drift()` currently computes `psi_scores: Dict[str, float]` (feature → PSI value) but throws it away after logging and DB writes. We store the latest result in `self._latest_psi` so the health collector can read it without re-computing.

Note: `PSI_WARN` and `PSI_CRIT` are **module-level constants** in `monitor.py` (lines 32–33), not class attributes. Access them as `from app.ml.drift.monitor import PSI_WARN, PSI_CRIT`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_health_collector.py`:

```python
class TestDriftMonitorLatestPsi:
    def test_latest_psi_starts_empty(self):
        from backend.app.ml.drift.monitor import DriftMonitor
        dm = DriftMonitor(redis_client=None)
        assert dm._latest_psi == {}

    def test_latest_psi_populated_after_check(self):
        """After _check_drift runs, _latest_psi[slug][feature] is set."""
        import asyncio
        from backend.app.ml.drift.monitor import DriftMonitor, MONITORED_FEATURES

        dm = DriftMonitor(redis_client=None)
        slug = "islamabad"
        # Seed enough observations for PSI computation
        for feat in MONITORED_FEATURES[:4]:
            dm._recent[slug][feat] = [float(i % 10) for i in range(20)]

        asyncio.run(dm._check_drift(slug))
        # On first check with no Redis reference, PSI defaults to 0.0
        # but _latest_psi should be populated
        assert slug in dm._latest_psi
        assert isinstance(dm._latest_psi[slug], dict)
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_health_collector.py::TestDriftMonitorLatestPsi -v
```

Expected: `AttributeError` — `DriftMonitor` has no `_latest_psi`.

- [ ] **Step 3: Add `_latest_psi` to `DriftMonitor.__init__`**

In `backend/app/ml/drift/monitor.py`, in `DriftMonitor.__init__` (line 71), add one line after the existing assignments:

```python
def __init__(self, redis_client=None):
    self._redis    = redis_client
    self._counters: Dict[str, int]             = defaultdict(int)
    self._recent:   Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    self._latest_psi: Dict[str, Dict[str, float]] = defaultdict(dict)  # NEW
```

- [ ] **Step 4: Populate `_latest_psi` in `_check_drift`**

In `backend/app/ml/drift/monitor.py`, in `_check_drift` (starting at line 127), after `psi_scores` is fully built (just before the `if not psi_scores:` guard), add one line:

The relevant section currently reads (around line 146):
```python
        if not psi_scores:
            return

        max_psi = max(psi_scores.values())
```

Change it to:
```python
        if not psi_scores:
            return

        # Store latest PSI for health collector (in-memory, no DB dependency)
        self._latest_psi[city_slug] = dict(psi_scores)

        max_psi = max(psi_scores.values())
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_health_collector.py::TestDriftMonitorLatestPsi -v
```

Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/ml/drift/monitor.py tests/test_health_collector.py
git commit -m "feat(group-d): expose _latest_psi on DriftMonitor"
```

---

## Task 4: Counter instrumentation in `city_model_service.py`

**Files:**
- Modify: `backend/app/services/city_model_service.py`
- Test: `tests/test_health_collector.py` (append)

**Context:** Add three module-level deques and four accessor functions. Then instrument three points in `predict_v2()`: preprocessing success/failure and MC success/timeout/exception.

Current module-level counters (lines 50–53):
```python
_mc_success_window: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
_mc_last_warn_at: Dict[str, float] = defaultdict(float)
```

We add after line 53. The import for `HealthCollectorConfig` goes on the existing import line at line 37:
```python
from app.core.config import DATA_DIR, MODELS_DIR, MCInferenceConfig
```

- [ ] **Step 1: Write failing tests**

Append to `tests/test_health_collector.py`:

```python
class TestCityModelCounters:
    def setup_method(self):
        """Reset module-level counters before each test."""
        import backend.app.services.city_model_service as cms
        cms._timeout_counter.clear()
        cms._preprocess_fail_counter.clear()
        cms._epistemic_buffer.clear()

    def test_mc_success_rate_returns_none_below_10(self):
        import backend.app.services.city_model_service as cms
        # Empty window → None
        assert cms.get_mc_success_rate("islamabad") is None
        # 9 observations → still None
        for _ in range(9):
            cms._mc_success_window["islamabad"].append(True)
        assert cms.get_mc_success_rate("islamabad") is None

    def test_mc_success_rate_correct_fraction(self):
        import backend.app.services.city_model_service as cms
        # 8 successes + 2 failures = 0.80
        for _ in range(8):
            cms._mc_success_window["karachi"].append(True)
        for _ in range(2):
            cms._mc_success_window["karachi"].append(False)
        rate = cms.get_mc_success_rate("karachi")
        assert rate is not None
        assert abs(rate - 0.80) < 0.01

    def test_timeout_rate_correct(self):
        import backend.app.services.city_model_service as cms
        for _ in range(9):
            cms._timeout_counter["lahore"].append(True)
        cms._timeout_counter["lahore"].append(False)  # 1 timeout in 10
        rate = cms.get_timeout_rate("lahore")
        assert rate is not None
        assert abs(rate - 0.10) < 0.01

    def test_preprocess_fail_rate_correct(self):
        import backend.app.services.city_model_service as cms
        for _ in range(19):
            cms._preprocess_fail_counter["peshawar"].append(True)
        cms._preprocess_fail_counter["peshawar"].append(False)  # 1 fail in 20
        rate = cms.get_preprocess_fail_rate("peshawar")
        assert rate is not None
        assert abs(rate - 0.05) < 0.01

    def test_epistemic_buffer_snapshot_returns_list(self):
        import backend.app.services.city_model_service as cms
        cms._epistemic_buffer["quetta"].extend([0.1, 0.2, 0.3])
        buf = cms.get_epistemic_buffer_snapshot("quetta")
        assert buf == [0.1, 0.2, 0.3]
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_health_collector.py::TestCityModelCounters -v
```

Expected: `AttributeError` — `_timeout_counter`, accessor functions do not exist yet.

- [ ] **Step 3: Update import in `city_model_service.py`**

On line 37, add `HealthCollectorConfig` to the existing import:

```python
from app.core.config import DATA_DIR, MODELS_DIR, MCInferenceConfig, HealthCollectorConfig
```

- [ ] **Step 4: Add new module-level counters after line 53**

After the `_mc_last_warn_at` declaration (line 53), add:

```python
# Per-city ring buffer: True = MC completed within timeout, False = timed out / errored.
_timeout_counter: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE)
)

# Per-city ring buffer: True = preprocessing succeeded, False = raised exception.
_preprocess_fail_counter: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE)
)

# Per-city ring buffer of epistemic_uncertainty values from successful MC passes.
_epistemic_buffer: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.EPISTEMIC_BUFFER_SIZE)
)
```

- [ ] **Step 5: Add four module-level accessor functions**

Add these functions immediately after the counter declarations (still at module level, before the `CITY_METADATA` dict):

```python
def get_mc_success_rate(slug: str) -> Optional[float]:
    """Fraction of recent requests that completed MC dropout. None if < 10 obs."""
    w = _mc_success_window[slug]
    return (sum(w) / len(w)) if len(w) >= 10 else None


def get_timeout_rate(slug: str) -> Optional[float]:
    """Fraction of recent MC requests that timed out or errored. None if < 10 obs."""
    w = _timeout_counter[slug]
    if len(w) < 10:
        return None
    return 1.0 - (sum(w) / len(w))


def get_preprocess_fail_rate(slug: str) -> Optional[float]:
    """Fraction of recent predict_v2 calls where preprocessing failed. None if < 10 obs."""
    w = _preprocess_fail_counter[slug]
    return (1.0 - sum(w) / len(w)) if len(w) >= 10 else None


def get_epistemic_buffer_snapshot(slug: str) -> list:
    """Return a copy of the epistemic uncertainty buffer for a city."""
    return list(_epistemic_buffer[slug])
```

Note: `Optional` is already imported at the top of the file (`from typing import Any, Dict, List, Optional, Set`). No new imports needed.

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_health_collector.py::TestCityModelCounters -v
```

Expected: PASS (all 5 tests).

- [ ] **Step 7: Instrument preprocessing in `predict_v2()`**

Locate the preprocessing block in `predict_v2()` (around line 722–728 in the original file). It currently reads:

```python
        # ---- Preprocess ----
        preprocessor = self._preprocessors.get(slug)
        try:
            x_vec = self._preprocess(feat_dict, preprocessor, slug=slug)
        except Exception as exc:
            logger.error("[%s] Preprocess failed: %s", slug, exc)
            return self._build_degraded_response(slug, raw_weather, now, "preprocessing_failed")
```

Change to:

```python
        # ---- Preprocess ----
        preprocessor = self._preprocessors.get(slug)
        try:
            x_vec = self._preprocess(feat_dict, preprocessor, slug=slug)
            _preprocess_fail_counter[slug].append(True)
        except Exception as exc:
            logger.error("[%s] Preprocess failed: %s", slug, exc)
            _preprocess_fail_counter[slug].append(False)
            return self._build_degraded_response(slug, raw_weather, now, "preprocessing_failed")
```

- [ ] **Step 8: Instrument MC success path**

Locate the MC success recording (around line 781). It currently reads:

```python
                _mc_success_window[slug].append(True)
```

Change to:

```python
                _mc_success_window[slug].append(True)
                _timeout_counter[slug].append(True)
                if epistemic_uncertainty is not None:
                    _epistemic_buffer[slug].append(epistemic_uncertainty)
```

- [ ] **Step 9: Instrument MC timeout and exception paths**

Locate the timeout handler (around line 795–797):

```python
            except asyncio.TimeoutError:
                logger.info(...)
                degraded_reason = "timeout"
                inference_mode  = "fallback_deterministic"
                _mc_success_window[slug].append(False)
```

Add one line after `_mc_success_window[slug].append(False)`:

```python
                _timeout_counter[slug].append(False)
```

Do the same for the exception handler (around line 800–802):

```python
            except Exception as exc:
                logger.warning(...)
                degraded_reason = "exception"
                inference_mode  = "fallback_deterministic"
                _mc_success_window[slug].append(False)
```

Add:

```python
                _timeout_counter[slug].append(False)
```

- [ ] **Step 10: Run full test suite to confirm no regressions**

```
pytest tests/ -v --tb=short -x
```

Expected: same pass/fail as before (44 pass, 2 pre-existing failures in `test_api.py`). The 5 new `TestCityModelCounters` tests pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/city_model_service.py tests/test_health_collector.py
git commit -m "feat(group-d): counter instrumentation in city_model_service"
```

---

## Task 5: `RuntimeHealthCollector`

**Files:**
- Create: `backend/app/services/health_collector.py`
- Test: `tests/test_health_collector.py` (append)

**Context:** Three asyncio loops at different cadences. The inference loop drives the broadcast. The drift loop reads `_latest_psi` from DriftMonitor. The confidence loop computes 2σ/3σ bands using a per-city warmup baseline derived from the first `EPISTEMIC_WARMUP_MIN_SAMPLES` successful MC inferences.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_health_collector.py`:

```python
class TestRuntimeHealthCollector:
    def test_build_snapshot_all_unknown_when_empty(self):
        """With no observations, all cities report unknown/warming_up."""
        import backend.app.services.city_model_service as cms
        cms._timeout_counter.clear()
        cms._preprocess_fail_counter.clear()
        cms._epistemic_buffer.clear()
        cms._mc_success_window.clear()

        from backend.app.services.health_collector import RuntimeHealthCollector
        collector = RuntimeHealthCollector()
        collector._tick_inference_health()
        snap = collector._build_snapshot()
        assert snap.global_status in ("unknown", "ok")
        for city_snap in snap.cities.values():
            assert city_snap.inference_health in ("unknown", "ok")

    def test_inference_health_ok_above_thresholds(self):
        import backend.app.services.city_model_service as cms
        cms._mc_success_window.clear()
        cms._timeout_counter.clear()
        cms._preprocess_fail_counter.clear()

        for _ in range(15):
            cms._mc_success_window["islamabad"].append(True)
            cms._timeout_counter["islamabad"].append(True)
            cms._preprocess_fail_counter["islamabad"].append(True)

        from backend.app.services.health_collector import RuntimeHealthCollector
        collector = RuntimeHealthCollector()
        collector._tick_inference_health()
        snap = collector._build_snapshot()
        if "islamabad" in snap.cities:
            assert snap.cities["islamabad"].inference_health == "ok"

    def test_inference_health_critical_below_threshold(self):
        import backend.app.services.city_model_service as cms
        cms._mc_success_window.clear()
        cms._timeout_counter.clear()
        cms._preprocess_fail_counter.clear()

        # 5 success, 15 timeout → 25% success rate → critical
        for _ in range(5):
            cms._mc_success_window["karachi"].append(True)
            cms._timeout_counter["karachi"].append(True)
        for _ in range(15):
            cms._mc_success_window["karachi"].append(False)
            cms._timeout_counter["karachi"].append(False)
        for _ in range(20):
            cms._preprocess_fail_counter["karachi"].append(True)

        from backend.app.services.health_collector import RuntimeHealthCollector
        collector = RuntimeHealthCollector()
        collector._tick_inference_health()
        snap = collector._build_snapshot()
        if "karachi" in snap.cities:
            assert snap.cities["karachi"].inference_health == "critical"

    def test_epistemic_stability_warming_up_below_threshold(self):
        import backend.app.services.city_model_service as cms
        cms._epistemic_buffer.clear()
        cms._epistemic_buffer["lahore"].extend([0.1] * 10)  # fewer than WARMUP_MIN

        from backend.app.core.config import HealthCollectorConfig
        from backend.app.services.health_collector import RuntimeHealthCollector
        collector = RuntimeHealthCollector()
        collector._tick_confidence_health()
        snap = collector._build_snapshot()
        if "lahore" in snap.cities:
            assert snap.cities["lahore"].epistemic_stability == "warming_up"
            assert snap.cities["lahore"].baseline_ready is False

    def test_epistemic_stability_stable_within_2sigma(self):
        import backend.app.services.city_model_service as cms
        from backend.app.core.config import HealthCollectorConfig
        cms._epistemic_buffer.clear()

        n = HealthCollectorConfig.EPISTEMIC_WARMUP_MIN_SAMPLES + 20
        vals = [0.15] * n  # constant → zero drift
        cms._epistemic_buffer["peshawar"].extend(vals)

        from backend.app.services.health_collector import RuntimeHealthCollector
        collector = RuntimeHealthCollector()
        collector._tick_confidence_health()
        snap = collector._build_snapshot()
        if "peshawar" in snap.cities:
            assert snap.cities["peshawar"].epistemic_stability == "stable"
            assert snap.cities["peshawar"].baseline_ready is True
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_health_collector.py::TestRuntimeHealthCollector -v
```

Expected: `ModuleNotFoundError` — `health_collector` does not exist.

- [ ] **Step 3: Create `backend/app/services/health_collector.py`**

```python
"""
HydroGuard-AI — Runtime Health Collector
==========================================
Three asyncio background tasks sample in-memory counters and the DriftMonitor,
then broadcast a SystemHealthSnapshot to /ws/health every HEALTH_TICK_INTERVAL_S.

No DB writes. No Redis writes. All state is in-memory; resets on restart.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.config import HealthCollectorConfig
from app.schemas.health import CityHealthSnapshot, SystemHealthSnapshot

logger = logging.getLogger(__name__)


class RuntimeHealthCollector:
    """
    Coordinates three asyncio tick tasks and merges their outputs into a
    single SystemHealthSnapshot broadcast on every inference tick.
    """

    def __init__(self) -> None:
        self._inference_state:  Dict[str, dict] = {}
        self._drift_state:      Dict[str, dict] = {}
        self._confidence_state: Dict[str, dict] = {}
        # Per-city epistemic warmup baseline: {slug: (warmup_mean, warmup_std)}
        self._epistemic_baseline: Dict[str, Tuple[float, float]] = {}
        self._tasks: List[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._tasks = [
            asyncio.ensure_future(self._loop_inference_health()),
            asyncio.ensure_future(self._loop_drift_health()),
            asyncio.ensure_future(self._loop_confidence_health()),
        ]
        logger.info(
            "RuntimeHealthCollector started (ticks: %ds / %ds / %ds)",
            HealthCollectorConfig.HEALTH_TICK_INTERVAL_S,
            HealthCollectorConfig.DRIFT_TICK_INTERVAL_S,
            HealthCollectorConfig.CONFIDENCE_TICK_INTERVAL_S,
        )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("RuntimeHealthCollector stopped")

    # ------------------------------------------------------------------
    # Tick loops
    # ------------------------------------------------------------------

    async def _loop_inference_health(self) -> None:
        while True:
            try:
                self._tick_inference_health()
                snapshot = self._build_snapshot()
                from app.services.broadcast_service import emit_health
                await emit_health(snapshot.model_dump(mode="json"))
            except Exception:
                logger.exception("Health collector inference tick failed")
            await asyncio.sleep(HealthCollectorConfig.HEALTH_TICK_INTERVAL_S)

    async def _loop_drift_health(self) -> None:
        while True:
            try:
                self._tick_drift_health()
            except Exception:
                logger.exception("Health collector drift tick failed")
            await asyncio.sleep(HealthCollectorConfig.DRIFT_TICK_INTERVAL_S)

    async def _loop_confidence_health(self) -> None:
        while True:
            try:
                self._tick_confidence_health()
            except Exception:
                logger.exception("Health collector confidence tick failed")
            await asyncio.sleep(HealthCollectorConfig.CONFIDENCE_TICK_INTERVAL_S)

    # ------------------------------------------------------------------
    # Domain 1 — Inference health (drives the 30s broadcast)
    # ------------------------------------------------------------------

    def _tick_inference_health(self) -> None:
        from app.services.city_model_service import (
            city_model_service,
            get_mc_success_rate,
            get_timeout_rate,
            get_preprocess_fail_rate,
        )
        cfg   = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            mc_rate   = get_mc_success_rate(slug)
            t_rate    = get_timeout_rate(slug)
            fail_rate = get_preprocess_fail_rate(slug)

            if mc_rate is None and fail_rate is None:
                health = "unknown"
            elif (
                (mc_rate  is not None and mc_rate  < cfg.MC_CRITICAL_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_CRITICAL)
            ):
                health = "critical"
            elif (
                (mc_rate  is not None and mc_rate  < cfg.MC_DEGRADED_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_DEGRADED)
            ):
                health = "degraded"
            else:
                health = "ok"

            state[slug] = {
                "mc_success_rate":    mc_rate,
                "timeout_rate":       t_rate,
                "preprocess_fail_rate": fail_rate,
                "inference_health":   health,
            }

        self._inference_state = state

    # ------------------------------------------------------------------
    # Domain 2 — Drift health (runs every 5 min)
    # ------------------------------------------------------------------

    def _tick_drift_health(self) -> None:
        from app.ml.drift.monitor import get_drift_monitor, PSI_WARN, PSI_CRIT
        from app.services.city_model_service import city_model_service

        monitor = get_drift_monitor()
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            if monitor is None:
                state[slug] = {"psi_max": None, "psi_status": "unknown", "top_drifted_feature": None}
                continue

            psi_results: dict = dict(getattr(monitor, "_latest_psi", {}).get(slug, {}))

            if not psi_results:
                state[slug] = {"psi_max": None, "psi_status": "unknown", "top_drifted_feature": None}
                continue

            psi_max  = max(psi_results.values())
            top_feat = max(psi_results, key=psi_results.__getitem__)

            if psi_max >= PSI_CRIT:
                psi_status = "critical"
            elif psi_max >= PSI_WARN:
                psi_status = "warn"
            else:
                psi_status = "ok"

            state[slug] = {
                "psi_max":             psi_max,
                "psi_status":          psi_status,
                "top_drifted_feature": top_feat,
            }

        self._drift_state = state

    # ------------------------------------------------------------------
    # Domain 3 — Epistemic confidence stability (runs every 60 min)
    # ------------------------------------------------------------------

    def _tick_confidence_health(self) -> None:
        from app.services.city_model_service import city_model_service, get_epistemic_buffer_snapshot
        cfg   = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            buf = get_epistemic_buffer_snapshot(slug)

            if len(buf) < cfg.EPISTEMIC_WARMUP_MIN_SAMPLES:
                state[slug] = {
                    "epistemic_mean":      None,
                    "epistemic_std":       None,
                    "epistemic_drift":     None,
                    "epistemic_stability": "warming_up",
                    "baseline_ready":      False,
                }
                continue

            ep_mean = sum(buf) / len(buf)
            ep_var  = sum((x - ep_mean) ** 2 for x in buf) / len(buf)
            ep_std  = math.sqrt(ep_var) if ep_var > 0 else 1e-9

            # Establish baseline once from first EPISTEMIC_WARMUP_MIN_SAMPLES values
            if slug not in self._epistemic_baseline:
                warmup = buf[:cfg.EPISTEMIC_WARMUP_MIN_SAMPLES]
                wm     = sum(warmup) / len(warmup)
                wv     = sum((x - wm) ** 2 for x in warmup) / len(warmup)
                ws     = math.sqrt(wv) if wv > 0 else 1e-9
                self._epistemic_baseline[slug] = (wm, ws)

            wm, ws = self._epistemic_baseline[slug]
            drift  = abs(ep_mean - wm) / ws

            # 2σ/3σ bands derived from warmup distribution — no hardcoded values
            if drift < 2.0:
                stability = "stable"
            elif drift < 3.0:
                stability = "drifting"
            else:
                stability = "anomalous"

            state[slug] = {
                "epistemic_mean":      ep_mean,
                "epistemic_std":       ep_std,
                "epistemic_drift":     drift,
                "epistemic_stability": stability,
                "baseline_ready":      True,
            }

        self._confidence_state = state

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------

    def _build_snapshot(self) -> SystemHealthSnapshot:
        from app.services.city_model_service import city_model_service
        cities: Dict[str, CityHealthSnapshot] = {}

        for slug in city_model_service.list_slugs():
            inf  = self._inference_state.get(slug, {})
            dft  = self._drift_state.get(slug, {})
            conf = self._confidence_state.get(slug, {})

            cities[slug] = CityHealthSnapshot(
                city_slug=slug,
                mc_success_rate=inf.get("mc_success_rate"),
                timeout_rate=inf.get("timeout_rate"),
                preprocess_fail_rate=inf.get("preprocess_fail_rate"),
                inference_health=inf.get("inference_health", "unknown"),
                psi_max=dft.get("psi_max"),
                psi_status=dft.get("psi_status", "unknown"),
                top_drifted_feature=dft.get("top_drifted_feature"),
                epistemic_mean=conf.get("epistemic_mean"),
                epistemic_std=conf.get("epistemic_std"),
                epistemic_drift=conf.get("epistemic_drift"),
                epistemic_stability=conf.get("epistemic_stability", "warming_up"),
                baseline_ready=conf.get("baseline_ready", False),
            )

        statuses = [c.inference_health for c in cities.values()]
        if "critical" in statuses:
            global_status = "critical"
        elif "degraded" in statuses:
            global_status = "degraded"
        elif all(s == "ok" for s in statuses if s != "unknown"):
            global_status = "ok"
        else:
            global_status = "unknown"

        return SystemHealthSnapshot(
            snapshot_at=datetime.now(timezone.utc),
            cities=cities,
            global_status=global_status,
            active_city_count=len(cities),
        )


# Module-level singleton
_collector: Optional[RuntimeHealthCollector] = None


def get_health_collector() -> RuntimeHealthCollector:
    global _collector
    if _collector is None:
        _collector = RuntimeHealthCollector()
    return _collector
```

- [ ] **Step 4: Run the collector tests**

```
pytest tests/test_health_collector.py::TestRuntimeHealthCollector -v
```

Expected: PASS (all 5 tests).

- [ ] **Step 5: Run full suite to confirm no regressions**

```
pytest tests/ -v --tb=short -x
```

Expected: 44 pass + 5 new TestRuntimeHealthCollector pass + prior 5 new tests. 2 pre-existing failures in `test_api.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/health_collector.py tests/test_health_collector.py
git commit -m "feat(group-d): RuntimeHealthCollector with 3-domain tick tasks"
```

---

## Task 6: Lifespan wiring in `main.py`

**Files:**
- Modify: `backend/app/main.py:140-148` (around `yield`)

**Context:** The `yield` is at line 141. The collector must start before `yield` (app serving) and stop after `yield` (shutdown). The relevant block currently reads:

```python
    logger.info("=== HydroGuard-AI ready ===")
    yield

    # Shutdown
    try:
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)
    logger.info("Shutdown complete.")
```

- [ ] **Step 1: No test needed** — lifecycle wiring is verified by the smoke test (Step 4). Skip to implementation.

- [ ] **Step 2: Insert collector start before `yield` in `main.py`**

Find the line `logger.info("=== HydroGuard-AI ready ===")` (line 140) and the `yield` (line 141). Replace those two lines with:

```python
    # 8. Start runtime health collector (non-blocking background ticks)
    try:
        from app.services.health_collector import get_health_collector
        _health_collector = get_health_collector()
        _health_collector.start()
        logger.info("RuntimeHealthCollector started")
    except Exception as exc:
        logger.warning("RuntimeHealthCollector start failed (non-fatal): %s", exc)
        _health_collector = None

    logger.info("=== HydroGuard-AI ready ===")
    yield

    # Shutdown
    if _health_collector is not None:
        try:
            await _health_collector.stop()
        except Exception as exc:
            logger.warning("RuntimeHealthCollector stop error: %s", exc)
    try:
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)
    logger.info("Shutdown complete.")
```

- [ ] **Step 3: Run the test suite**

```
pytest tests/ -v --tb=short
```

Expected: same result as before — no new failures from the lifespan change.

- [ ] **Step 4: Manual smoke test (start the server and verify health WS)**

Start the server in one terminal:
```bash
python backend/run_server.py --reload
```

In a second terminal, connect to the health WS using wscat or Python:
```bash
python -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:8000/ws/health') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        data = json.loads(msg)
        print('channel:', data.get('channel'))
        print('global_status:', data['data'].get('global_status'))
        print('cities:', list(data['data'].get('cities', {}).keys()))
asyncio.run(test())
"
```

Expected: within 30 seconds, prints `channel: health`, `global_status: unknown` or `ok`, and a list of city slugs.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(group-d): wire RuntimeHealthCollector into app lifespan"
```

---

## Task 7: Admin dashboard frontend

**Files:**
- Modify: `frontend/web_dashboard/admin_dashboard/screens/others.jsx:5` (`MonitoringScreen`)
- Modify: `frontend/web_dashboard/admin_dashboard/app.jsx:207` (state and WS)

**Context:**
- `MonitoringScreen({ liveEvents })` at line 5 of `others.jsx` currently takes only `liveEvents`
- `app.jsx` connects to `"anomalies"` WS at line 241; needs a parallel `"health"` connection
- `API.connectWs(channel, onMessage, onError)` already handles any channel string — no `api.js` changes needed
- This is JSX compiled by Babel-Standalone in the browser — no bundler, no `import`. All React hooks are destructured from the global `React` object already at the top of `others.jsx` (line 2: `const { useState, useEffect, useCallback, useRef } = React;`)

No test for the frontend — it is verified visually. The backend schema tests already cover the payload contract.

- [ ] **Step 1: Update `MonitoringScreen` in `others.jsx`**

Find line 5 in `frontend/web_dashboard/admin_dashboard/screens/others.jsx`:
```jsx
const MonitoringScreen = ({ liveEvents }) => {
```

Replace it with:
```jsx
const MonitoringScreen = ({ liveEvents, cityHealth }) => {
```

Then find the opening `return (` of `MonitoringScreen` (around line 41). It currently opens with:
```jsx
  return (
    <div className="screen">
      <div className="page-head">
```

Insert the health grid section immediately after `<div className="screen">` and before `<div className="page-head">`:

```jsx
  const statusColor = (s) => ({ ok: "#22c55e", degraded: "#f59e0b", critical: "#ef4444", warn: "#f59e0b", unknown: "#6b7280" }[s] || "#6b7280");
  const stabilityIcon = (s) => ({ stable: "✓", drifting: "~", anomalous: "⚠", warming_up: "…" }[s] || "?");
  const healthCities = cityHealth?.cities ? Object.values(cityHealth.cities) : [];

  return (
    <div className="screen">
      {healthCities.length > 0 && (
        <section style={{ marginBottom: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
            <h3 style={{ margin: 0 }}>City Health</h3>
            {cityHealth && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                System: <strong style={{ color: statusColor(cityHealth.global_status) }}>{cityHealth.global_status}</strong>
                {" · "}{healthCities.length} cities
              </span>
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: "10px" }}>
            {healthCities.map(c => (
              <div key={c.city_slug} style={{ border: `2px solid ${statusColor(c.inference_health)}`, borderRadius: "8px", padding: "12px", background: "var(--surface-2, rgba(255,255,255,0.04))" }}>
                <div style={{ fontWeight: 600, marginBottom: "6px", display: "flex", justifyContent: "space-between" }}>
                  <span>{c.city_slug}</span>
                  <span style={{ color: statusColor(c.inference_health) }}>● {c.inference_health}</span>
                </div>
                <div style={{ fontSize: "0.80rem", color: "var(--text-muted)", lineHeight: 1.6 }}>
                  <div>MC success: {c.mc_success_rate != null ? `${(c.mc_success_rate * 100).toFixed(1)}%` : "—"}</div>
                  <div>Preprocess fail: {c.preprocess_fail_rate != null ? `${(c.preprocess_fail_rate * 100).toFixed(1)}%` : "—"}</div>
                  <div style={{ color: statusColor(c.psi_status) }}>
                    PSI: {c.psi_max != null ? c.psi_max.toFixed(3) : "—"}
                    {c.top_drifted_feature ? ` (${c.top_drifted_feature})` : ""}
                  </div>
                  <div>
                    Uncertainty: {stabilityIcon(c.epistemic_stability)} {c.epistemic_stability}
                    {c.epistemic_mean != null ? ` μ=${c.epistemic_mean.toFixed(3)}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <div className="page-head">
```

**Important:** the two helper const declarations (`statusColor`, `stabilityIcon`, `healthCities`) must be inside the component function body, placed immediately before the `return`. Find the last line before `return (` in `MonitoringScreen` and insert them there.

The safest edit is:
1. Replace the existing opening of the return:
```jsx
  return (
    <div className="screen">
      <div className="page-head">
```
With:
```jsx
  const statusColor = (s) => ({ ok: "#22c55e", degraded: "#f59e0b", critical: "#ef4444", warn: "#f59e0b", unknown: "#6b7280" }[s] || "#6b7280");
  const stabilityIcon = (s) => ({ stable: "✓", drifting: "~", anomalous: "⚠", warming_up: "…" }[s] || "?");
  const healthCities = cityHealth?.cities ? Object.values(cityHealth.cities) : [];

  return (
    <div className="screen">
      {healthCities.length > 0 && (
        <section style={{ marginBottom: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
            <h3 style={{ margin: 0 }}>City Health</h3>
            {cityHealth && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                System: <strong style={{ color: statusColor(cityHealth.global_status) }}>{cityHealth.global_status}</strong>
                {" · "}{healthCities.length} cities
              </span>
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: "10px" }}>
            {healthCities.map(c => (
              <div key={c.city_slug} style={{ border: `2px solid ${statusColor(c.inference_health)}`, borderRadius: "8px", padding: "12px", background: "var(--surface-2, rgba(255,255,255,0.04))" }}>
                <div style={{ fontWeight: 600, marginBottom: "6px", display: "flex", justifyContent: "space-between" }}>
                  <span>{c.city_slug}</span>
                  <span style={{ color: statusColor(c.inference_health) }}>● {c.inference_health}</span>
                </div>
                <div style={{ fontSize: "0.80rem", color: "var(--text-muted)", lineHeight: 1.6 }}>
                  <div>MC success: {c.mc_success_rate != null ? `${(c.mc_success_rate * 100).toFixed(1)}%` : "—"}</div>
                  <div>Preprocess fail: {c.preprocess_fail_rate != null ? `${(c.preprocess_fail_rate * 100).toFixed(1)}%` : "—"}</div>
                  <div style={{ color: statusColor(c.psi_status) }}>
                    PSI: {c.psi_max != null ? c.psi_max.toFixed(3) : "—"}
                    {c.top_drifted_feature ? ` (${c.top_drifted_feature})` : ""}
                  </div>
                  <div>
                    Uncertainty: {stabilityIcon(c.epistemic_stability)} {c.epistemic_stability}
                    {c.epistemic_mean != null ? ` μ=${c.epistemic_mean.toFixed(3)}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <div className="page-head">
```

- [ ] **Step 2: Update `app.jsx` — add `cityHealth` state**

In `frontend/web_dashboard/admin_dashboard/app.jsx`, find the line (around 207):
```jsx
  const [liveEvents,  setLiveEvents]  = useState([]);
```

Add immediately after it:
```jsx
  const [cityHealth,  setCityHealth]  = useState(null);
```

- [ ] **Step 3: Add `/ws/health` subscription in `app.jsx`**

Find the `connectWs` callback that creates the anomalies WebSocket (around line 237):
```jsx
  const connectWs = useCallback(() => {
    clearTimeout(wsReconnectRef.current);
    if (wsRef.current) { try { wsRef.current.close(); } catch {} }

    const ws = API.connectWs("anomalies",
```

Add a parallel health WS subscription. Insert after the existing `connectWs` function (find where it ends and add a new function):

```jsx
  // ── Health WebSocket ─────────────────────────────────────────────────────
  const healthWsRef = useRef(null);
  useEffect(() => {
    const connectHealthWs = () => {
      if (healthWsRef.current) { try { healthWsRef.current.close(); } catch {} }
      const hws = API.connectWs("health",
        (data) => {
          if (data?.cities) setCityHealth(data);
        },
        () => {
          // Reconnect health WS after 10s on close
          setTimeout(connectHealthWs, 10000);
        }
      );
      healthWsRef.current = hws;
    };
    connectHealthWs();
    return () => { if (healthWsRef.current) try { healthWsRef.current.close(); } catch {} };
  }, []);
```

- [ ] **Step 4: Pass `cityHealth` to `MonitoringScreen`**

Find where `MonitoringScreen` is rendered in `app.jsx` (search for `<MonitoringScreen`). It currently reads:
```jsx
<MonitoringScreen liveEvents={liveEvents} />
```

Change to:
```jsx
<MonitoringScreen liveEvents={liveEvents} cityHealth={cityHealth} />
```

- [ ] **Step 5: Visual smoke test**

Start the server:
```bash
python backend/run_server.py --reload
```

Open the admin dashboard at `http://localhost:8000/frontend` (or serve `frontend/web_dashboard/admin_dashboard/` via `python -m http.server 3000`). Log in and navigate to **Real-Time Monitoring**. Within 30 seconds the health grid should appear above the live event feed with city cards. All cities will show "unknown" or "warming_up" until predictions have been made.

- [ ] **Step 6: Run the backend test suite one final time**

```
pytest tests/ -v --tb=short
```

Expected: all Group D tests pass; 2 pre-existing `test_api.py` failures remain.

- [ ] **Step 7: Commit**

```bash
git add frontend/web_dashboard/admin_dashboard/screens/others.jsx frontend/web_dashboard/admin_dashboard/app.jsx
git commit -m "feat(group-d): MonitoringScreen health grid + /ws/health subscription"
```

---

## Final verification

- [ ] **Run the full test suite**

```
pytest tests/ -v --tb=short
```

Expected output summary line: `X passed, 2 failed` where X is the prior pass count plus all new Group D tests, and the 2 failures are the pre-existing ones in `test_api.py::TestPrediction::test_predict_missing_city` and `test_api.py::TestV2Cities::test_predict_v2_missing_required`.

- [ ] **Run linter**

```
ruff check backend/ --select E,W,F,I --ignore E501
```

Expected: no new errors.

---

## Notes for the implementer

**Pre-existing test failures are NOT your problem:** `test_predict_missing_city` and `test_predict_v2_missing_required` in `test_api.py` have been failing since before Group D. Do not attempt to fix them.

**`PSI_WARN` / `PSI_CRIT` are module-level constants** in `monitor.py` (lines 32–33), not class attributes. Import them as `from app.ml.drift.monitor import PSI_WARN, PSI_CRIT` — not `DriftMonitor.PSI_WARN`.

**First broadcast will show "unknown" and "warming_up"** for all cities. This is correct — drift tick runs every 5 min and confidence tick runs every 60 min, so they won't have data for the first broadcast (30s). The UI gracefully shows "—" for missing values.

**Frontend is JSX-via-Babel-Standalone** — no `import` statements, no bundler. All React hooks are already destructured from `React` at the top of each JSX file. Do not add ES module syntax.

**`API.connectWs(channel, onMessage, onError)`** in `api.js` already accepts any channel string. Pass `"health"` for the health stream — no changes to `api.js` are needed.
