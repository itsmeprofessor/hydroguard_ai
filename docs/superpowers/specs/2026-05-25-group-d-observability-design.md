# Group D — Observability, Drift & Runtime Health Design

**Date:** 2026-05-25  
**Status:** Approved  
**Scope:** Domains 1–3 (Domain 4 system reliability deferred to a future session)

---

## Goal

Surface what is actually happening inside HydroGuard-AI at runtime: whether MC Dropout is degrading, whether input distributions are shifting, and whether the epistemic uncertainty signal is stable or drifting. All of this should flow into the existing `/ws/health` WebSocket and the admin `MonitoringScreen` without adding new transport layers or new persistence dependencies.

---

## Guiding Constraints

1. **No hardcoded thresholds.** Every numeric boundary lives in `HealthCollectorConfig` and is driven by an env var. Uncertainty drift thresholds are computed per-city from the first N successful MC inferences (statistical warmup), not from a fixed number.
2. **No new transport.** Use the existing `emit_health()` in `broadcast_service.py` (already defined, never called). Use the existing `/ws/health` channel.
3. **No new DB tables.** All health state is in-memory. It resets on restart — that is acceptable; it is telemetry, not a record of truth.
4. **Non-blocking.** Background asyncio tasks. Never touch the hot path (`predict_v2()`).
5. **System-wide snapshot.** One payload per tick containing all cities. Ensures any new `/ws/health` subscriber gets a complete picture immediately, not after waiting for each city's individual event.

---

## Architecture Overview

```
city_model_service.py
  _mc_success_window          (existing, 100-slot bool deque per city)
  _mc_last_warn_at            (existing, anti-spam float per city)
  _timeout_counter            (new, 100-slot bool deque per city)
  _preprocess_fail_counter    (new, 100-slot bool deque per city)
  _epistemic_buffer           (new, 200-slot float deque per city)

drift/monitor.py
  DriftMonitor.get_in_memory_state(slug)  (existing, {feat: {n, mean}})

health_collector.py  [NEW]
  RuntimeHealthCollector
    _tick_inference_health()   — every HEALTH_TICK_INTERVAL_S (default 30s)
    _tick_drift_health()       — every DRIFT_TICK_INTERVAL_S (default 300s)
    _tick_confidence_health()  — every CONFIDENCE_TICK_INTERVAL_S (default 3600s)
    start() / stop()

schemas/health.py  [NEW]
  CityHealthSnapshot (Pydantic)
  SystemHealthSnapshot (Pydantic)

config.py  [MODIFIED]
  class HealthCollectorConfig  (all env-var driven)

main.py  [MODIFIED]
  collector.start() after yield (in lifespan)
  collector.stop() in shutdown

broadcast_service.py  [MODIFIED]
  emit_health() already exists — no signature change needed

/ws/health  [EXISTING]
  receives SystemHealthSnapshot payloads every 30s

Frontend (worktree)
  app.jsx       — add cityHealth state, subscribe to hg:health
  others.jsx    — add cityHealth prop to MonitoringScreen, health grid
  api.js        — no changes needed (connectWs already handles "health")
  .env.example  — document HealthCollectorConfig vars
```

---

## Section 1 — Data Collection Layer

### 1.1 New module-level counters in `city_model_service.py`

Add three new module-level counters immediately after `_mc_last_warn_at`:

```python
# Per-city: True = MC completed within timeout, False = timed out / errored.
_timeout_counter: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

# Per-city: True = preprocessing succeeded, False = preprocessing raised.
_preprocess_fail_counter: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

# Per-city ring buffer of epistemic_uncertainty values (MC successes only).
_epistemic_buffer: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
```

The `maxlen` values are overridden at module import time by `HealthCollectorConfig`:

```python
# At module top, after the defaultdict declarations:
def _resize_health_counters() -> None:
    """Apply HealthCollectorConfig window sizes to newly created deques.
    
    Called once at import time. Existing city deques are already at their
    maxlen; this sets the factory default for cities discovered later.
    """
    from app.core.config import HealthCollectorConfig  # avoid circular at module level
    global _timeout_counter, _preprocess_fail_counter, _epistemic_buffer
    _timeout_counter        = defaultdict(lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE))
    _preprocess_fail_counter = defaultdict(lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE))
    _epistemic_buffer        = defaultdict(lambda: deque(maxlen=HealthCollectorConfig.EPISTEMIC_BUFFER_SIZE))

_resize_health_counters()
```

### 1.2 Instrumentation points in `predict_v2()`

Three recording calls — all in the hot path but O(1):

**After the MC gather block completes (success path):**
```python
_mc_success_window[slug].append(True)
_timeout_counter[slug].append(True)
if result.get("epistemic_uncertainty") is not None:
    _epistemic_buffer[slug].append(result["epistemic_uncertainty"])
```

**On MC timeout / fallback (degraded path):**
```python
_mc_success_window[slug].append(False)
_timeout_counter[slug].append(False)
```

**After preprocessing succeeds (before model call):**
```python
_preprocess_fail_counter[slug].append(True)
```

**In `_build_degraded_response()` when `degraded_reason == "preprocessing_failed"`:**
```python
_preprocess_fail_counter[slug].append(False)
```

### 1.3 Accessor functions (module-level, in `city_model_service.py`)

These are the only surface the `RuntimeHealthCollector` calls. No lock needed — `deque.append` is thread-safe in CPython.

```python
def get_mc_success_rate(slug: str) -> float | None:
    """Fraction of recent requests that completed MC dropout (not timed out).
    Returns None if fewer than 10 observations."""
    w = _mc_success_window[slug]
    return (sum(w) / len(w)) if len(w) >= 10 else None

def get_timeout_rate(slug: str) -> float | None:
    """Fraction of recent MC requests that timed out. None if < 10 obs."""
    w = _timeout_counter[slug]
    if len(w) < 10:
        return None
    return 1.0 - (sum(w) / len(w))

def get_preprocess_fail_rate(slug: str) -> float | None:
    """Fraction of recent predict_v2 calls where preprocessing failed."""
    w = _preprocess_fail_counter[slug]
    return (1.0 - sum(w) / len(w)) if len(w) >= 10 else None

def get_epistemic_buffer_snapshot(slug: str) -> list[float]:
    """Return a copy of the epistemic buffer for this city."""
    return list(_epistemic_buffer[slug])
```

---

## Section 2 — `HealthCollectorConfig` (in `config.py`)

Add after `MCInferenceConfig`:

```python
class HealthCollectorConfig:
    # Background tick cadences (seconds)
    HEALTH_TICK_INTERVAL_S:     int   = int(os.getenv("HEALTH_TICK_INTERVAL_S",    "30"))
    DRIFT_TICK_INTERVAL_S:      int   = int(os.getenv("DRIFT_TICK_INTERVAL_S",     "300"))
    CONFIDENCE_TICK_INTERVAL_S: int   = int(os.getenv("CONFIDENCE_TICK_INTERVAL_S","3600"))

    # Rolling window sizes (number of requests)
    MC_WINDOW_SIZE:             int   = int(os.getenv("HEALTH_MC_WINDOW_SIZE",     "100"))
    EPISTEMIC_BUFFER_SIZE:      int   = int(os.getenv("HEALTH_EPISTEMIC_BUFFER",   "200"))

    # MC success rate thresholds — fraction of requests that complete MC dropout
    # (1.0 = all requests used MC; lower = more fallbacks)
    MC_DEGRADED_THRESHOLD:      float = float(os.getenv("HEALTH_MC_DEGRADED",      "0.90"))
    MC_CRITICAL_THRESHOLD:      float = float(os.getenv("HEALTH_MC_CRITICAL",      "0.70"))

    # Preprocessing failure rate thresholds — fraction of requests where
    # feature extraction / scaler transform raised an exception
    PREPROCESS_FAIL_DEGRADED:   float = float(os.getenv("HEALTH_FAIL_DEGRADED",    "0.05"))
    PREPROCESS_FAIL_CRITICAL:   float = float(os.getenv("HEALTH_FAIL_CRITICAL",    "0.20"))

    # Epistemic uncertainty warmup — number of successful MC inferences per city
    # before stability bands can be computed. City is "warming_up" until this is met.
    EPISTEMIC_WARMUP_MIN_SAMPLES: int = int(os.getenv("HEALTH_EPISTEMIC_WARMUP",   "50"))
```

---

## Section 3 — Pydantic Schemas (`backend/app/schemas/health.py`) [NEW FILE]

```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CityHealthSnapshot(BaseModel):
    city_slug: str

    # Domain 1 — Inference health
    mc_success_rate: Optional[float]         # None if < 10 obs
    timeout_rate: Optional[float]            # None if < 10 obs
    preprocess_fail_rate: Optional[float]    # None if < 10 obs
    inference_health: str                    # "ok" | "degraded" | "critical" | "unknown"

    # Domain 2 — Drift
    psi_max: Optional[float]                 # highest PSI across all monitored features
    psi_status: str                          # "ok" | "warn" | "critical" | "unknown"
    top_drifted_feature: Optional[str]       # feature name with highest PSI

    # Domain 3 — Epistemic stability
    epistemic_mean: Optional[float]          # mean of buffer
    epistemic_std: Optional[float]           # std of buffer
    epistemic_drift: Optional[float]         # |current_mean - warmup_mean| / warmup_std
    epistemic_stability: str                 # "warming_up" | "stable" | "drifting" | "anomalous"
    baseline_ready: bool


class SystemHealthSnapshot(BaseModel):
    snapshot_at: datetime
    cities: Dict[str, CityHealthSnapshot]   # keyed by city_slug
    global_status: str                      # "ok" | "degraded" | "critical"
    active_city_count: int
```

---

## Section 4 — `RuntimeHealthCollector` (`backend/app/services/health_collector.py`) [NEW FILE]

```python
"""
HydroGuard-AI — Runtime Health Collector
==========================================
Three background asyncio tasks that sample the in-memory counters from
city_model_service and the DriftMonitor, then broadcast a SystemHealthSnapshot
to /ws/health every HEALTH_TICK_INTERVAL_S seconds.

No DB writes. No Redis writes. In-memory only.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.config import HealthCollectorConfig
from app.ml.drift.monitor import get_drift_monitor
from app.schemas.health import CityHealthSnapshot, SystemHealthSnapshot
from app.services import city_model_service as cms
from app.services.broadcast_service import emit_health

logger = logging.getLogger(__name__)


class RuntimeHealthCollector:
    """
    Runs three asyncio tasks at different cadences and merges their outputs
    into a single SystemHealthSnapshot broadcast every HEALTH_TICK_INTERVAL_S.
    """

    def __init__(self) -> None:
        # Populated by the three tick methods; merged in _build_snapshot()
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
        logger.info("RuntimeHealthCollector started (ticks: %ds / %ds / %ds)",
                    HealthCollectorConfig.HEALTH_TICK_INTERVAL_S,
                    HealthCollectorConfig.DRIFT_TICK_INTERVAL_S,
                    HealthCollectorConfig.CONFIDENCE_TICK_INTERVAL_S)

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
    # Domain 1 — Inference health (runs every 30s, drives the broadcast)
    # ------------------------------------------------------------------

    def _tick_inference_health(self) -> None:
        cfg = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in cms.list_slugs():
            mc_rate      = cms.get_mc_success_rate(slug)
            timeout_rate = cms.get_timeout_rate(slug)
            fail_rate    = cms.get_preprocess_fail_rate(slug)

            if mc_rate is None and fail_rate is None:
                health = "unknown"
            elif (
                (mc_rate is not None and mc_rate < cfg.MC_CRITICAL_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_CRITICAL)
            ):
                health = "critical"
            elif (
                (mc_rate is not None and mc_rate < cfg.MC_DEGRADED_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_DEGRADED)
            ):
                health = "degraded"
            else:
                health = "ok"

            state[slug] = {
                "mc_success_rate":    mc_rate,
                "timeout_rate":       timeout_rate,
                "preprocess_fail_rate": fail_rate,
                "inference_health":   health,
            }

        self._inference_state = state

    # ------------------------------------------------------------------
    # Domain 2 — Drift health (runs every 5min)
    # ------------------------------------------------------------------

    def _tick_drift_health(self) -> None:
        monitor = get_drift_monitor()
        state: Dict[str, dict] = {}

        for slug in cms.list_slugs():
            in_mem = monitor.get_in_memory_state(slug) if monitor else {}

            # The DriftMonitor also exposes the latest PSI results via a
            # public attribute set by _check_drift(). Access defensively.
            psi_results: dict = getattr(monitor, "_latest_psi", {}).get(slug, {})

            if not psi_results:
                state[slug] = {
                    "psi_max": None,
                    "psi_status": "unknown",
                    "top_drifted_feature": None,
                }
                continue

            psi_max  = max(psi_results.values(), default=0.0)
            top_feat = max(psi_results, key=psi_results.get) if psi_results else None

            from app.ml.drift.monitor import DriftMonitor
            if psi_max >= DriftMonitor.PSI_CRIT:
                psi_status = "critical"
            elif psi_max >= DriftMonitor.PSI_WARN:
                psi_status = "warn"
            else:
                psi_status = "ok"

            state[slug] = {
                "psi_max": psi_max,
                "psi_status": psi_status,
                "top_drifted_feature": top_feat,
            }

        self._drift_state = state

    # ------------------------------------------------------------------
    # Domain 3 — Epistemic confidence stability (runs every 60min)
    # ------------------------------------------------------------------

    def _tick_confidence_health(self) -> None:
        cfg = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in cms.list_slugs():
            buf = cms.get_epistemic_buffer_snapshot(slug)

            if len(buf) < cfg.EPISTEMIC_WARMUP_MIN_SAMPLES:
                state[slug] = {
                    "epistemic_mean":      None,
                    "epistemic_std":       None,
                    "epistemic_drift":     None,
                    "epistemic_stability": "warming_up",
                    "baseline_ready":      False,
                }
                continue

            arr       = buf
            ep_mean   = sum(arr) / len(arr)
            ep_var    = sum((x - ep_mean) ** 2 for x in arr) / len(arr)
            ep_std    = math.sqrt(ep_var) if ep_var > 0 else 1e-9

            # Establish baseline from first EPISTEMIC_WARMUP_MIN_SAMPLES values
            if slug not in self._epistemic_baseline:
                warmup = arr[:cfg.EPISTEMIC_WARMUP_MIN_SAMPLES]
                wm     = sum(warmup) / len(warmup)
                wv     = sum((x - wm) ** 2 for x in warmup) / len(warmup)
                ws     = math.sqrt(wv) if wv > 0 else 1e-9
                self._epistemic_baseline[slug] = (wm, ws)

            wm, ws = self._epistemic_baseline[slug]
            drift  = abs(ep_mean - wm) / ws

            # 2σ/3σ stability bands derived from warmup distribution
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
        slugs = cms.list_slugs()
        cities: Dict[str, CityHealthSnapshot] = {}

        for slug in slugs:
            inf  = self._inference_state.get(slug, {})
            dft  = self._drift_state.get(slug, {})
            conf = self._confidence_state.get(slug, {})

            cities[slug] = CityHealthSnapshot(
                city_slug=slug,
                # Domain 1
                mc_success_rate=inf.get("mc_success_rate"),
                timeout_rate=inf.get("timeout_rate"),
                preprocess_fail_rate=inf.get("preprocess_fail_rate"),
                inference_health=inf.get("inference_health", "unknown"),
                # Domain 2
                psi_max=dft.get("psi_max"),
                psi_status=dft.get("psi_status", "unknown"),
                top_drifted_feature=dft.get("top_drifted_feature"),
                # Domain 3
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

---

## Section 5 — `DriftMonitor` exposure of latest PSI

The existing `DriftMonitor` in `backend/app/ml/drift/monitor.py` runs PSI internally in `_check_drift()` but discards results after logging. Add a `_latest_psi` dict attribute and populate it:

```python
# In DriftMonitor.__init__:
self._latest_psi: Dict[str, Dict[str, float]] = defaultdict(dict)

# In DriftMonitor._check_drift(city_slug) after PSI is computed per feature:
self._latest_psi[city_slug][feature_name] = psi_value
```

This is the only change to the existing drift monitor. No signature change, no new public method beyond what the collector reads via `_latest_psi`.

---

## Section 6 — `main.py` lifecycle wiring

In `create_app()`'s `lifespan` async context manager, after the existing `yield`:

```python
# After city model warm-up, before yield:
from app.services.health_collector import get_health_collector
_health_collector = get_health_collector()
_health_collector.start()

yield  # app is running

# Shutdown (after yield):
await _health_collector.stop()
```

---

## Section 7 — `broadcast_service.py` — no signature change

`emit_health(status: Dict[str, Any])` at line 46 is already correct. The collector calls it with a `model_dump(mode="json")` dict. The existing implementation broadcasts `{"channel": "health", "data": status, "ts": ...}` to all `/ws/health` subscribers. No changes needed.

---

## Section 8 — Admin Dashboard Frontend

### 8.1 `app.jsx` changes

Add `cityHealth` state and subscribe to the `health` WebSocket channel:

```jsx
// New state (near liveEvents state):
const [cityHealth, setCityHealth] = React.useState(null);

// In the useEffect that sets up WebSocket (alongside the anomalies WS):
const healthWs = API.connectWs("health", (msg) => {
    if (msg?.data?.cities) {
        setCityHealth(msg.data);  // SystemHealthSnapshot payload
    }
}, () => logger.warn("Health WS closed"));

// Pass to MonitoringScreen:
<MonitoringScreen liveEvents={liveEvents} cityHealth={cityHealth} />
```

### 8.2 `others.jsx` — `MonitoringScreen` health grid

Add `cityHealth` to the `MonitoringScreen` prop signature and render a 6-card health grid above the existing live event feed:

```jsx
function MonitoringScreen({ liveEvents, cityHealth }) {
    const cities = cityHealth?.cities ? Object.values(cityHealth.cities) : [];

    const statusColor = (status) => ({
        ok:       "#22c55e",
        degraded: "#f59e0b",
        critical: "#ef4444",
        unknown:  "#6b7280",
        warn:     "#f59e0b",
    }[status] ?? "#6b7280");

    const stabilityIcon = (s) => ({
        stable:      "✓",
        drifting:    "~",
        anomalous:   "⚠",
        warming_up:  "…",
    }[s] ?? "?");

    return (
        <div className="screen monitoring-screen">
            {/* Health grid */}
            {cities.length > 0 && (
                <section className="health-grid">
                    <h3>City Health</h3>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "12px" }}>
                        {cities.map(c => (
                            <div key={c.city_slug} className="health-card" style={{
                                border: `2px solid ${statusColor(c.inference_health)}`,
                                borderRadius: "8px", padding: "12px"
                            }}>
                                <div style={{ fontWeight: 600, marginBottom: "6px" }}>
                                    {c.city_slug}
                                    <span style={{ float: "right", color: statusColor(c.inference_health) }}>
                                        ● {c.inference_health}
                                    </span>
                                </div>
                                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                                    MC success: {c.mc_success_rate != null
                                        ? `${(c.mc_success_rate * 100).toFixed(1)}%`
                                        : "—"}
                                </div>
                                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                                    Preprocess fail: {c.preprocess_fail_rate != null
                                        ? `${(c.preprocess_fail_rate * 100).toFixed(1)}%`
                                        : "—"}
                                </div>
                                <div style={{ fontSize: "0.82rem", color: statusColor(c.psi_status) }}>
                                    PSI: {c.psi_max != null ? c.psi_max.toFixed(3) : "—"}
                                    {c.top_drifted_feature && ` (${c.top_drifted_feature})`}
                                </div>
                                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                                    Uncertainty: {stabilityIcon(c.epistemic_stability)} {c.epistemic_stability}
                                    {c.epistemic_mean != null && ` μ=${c.epistemic_mean.toFixed(3)}`}
                                </div>
                            </div>
                        ))}
                    </div>
                    {cityHealth && (
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "6px" }}>
                            System: {cityHealth.global_status} · {cities.length} cities · {cityHealth.snapshot_at}
                        </div>
                    )}
                </section>
            )}

            {/* Existing live events feed — unchanged below */}
            ...
        </div>
    );
}
```

### 8.3 `api.js` — no changes

`connectWs(channel, onMessage, onError)` already supports any channel string. No changes needed.

---

## Section 9 — `.env.example` additions

Add a new `HealthCollectorConfig` block:

```
# ── Runtime Health Collector ───────────────────────────────────────────────────
#
#  Three background tasks sample in-memory inference counters and the drift
#  monitor, then broadcast a SystemHealthSnapshot to /ws/health.
#  All state is in-memory — it resets on restart. No DB writes.

# Background tick cadences (seconds)
HEALTH_TICK_INTERVAL_S=30
DRIFT_TICK_INTERVAL_S=300
CONFIDENCE_TICK_INTERVAL_S=3600

# Rolling window sizes (number of requests)
# MC_WINDOW_SIZE: last N predict_v2 calls used for MC success/timeout rates
# EPISTEMIC_BUFFER: last N successful MC inferences used for uncertainty stats
HEALTH_MC_WINDOW_SIZE=100
HEALTH_EPISTEMIC_BUFFER=200

# MC success rate thresholds — fraction of requests that completed MC dropout
# (1.0 = perfect; lower means more timeouts/fallbacks)
HEALTH_MC_DEGRADED=0.90
HEALTH_MC_CRITICAL=0.70

# Preprocessing failure rate thresholds — fraction of calls where feature
# extraction raised an exception
HEALTH_FAIL_DEGRADED=0.05
HEALTH_FAIL_CRITICAL=0.20

# Epistemic warmup: minimum successful MC inferences before per-city
# stability bands (2σ/3σ) can be computed. City shows "warming_up" until ready.
HEALTH_EPISTEMIC_WARMUP=50
```

---

## File Map

| Action   | File                                                                 | Change |
|----------|----------------------------------------------------------------------|--------|
| Modify   | `backend/app/core/config.py`                                         | Add `HealthCollectorConfig` |
| Modify   | `backend/app/services/city_model_service.py`                         | Add 3 counters + 4 accessor functions + instrumentation in `predict_v2()` |
| Create   | `backend/app/schemas/health.py`                                       | `CityHealthSnapshot`, `SystemHealthSnapshot` Pydantic models |
| Create   | `backend/app/services/health_collector.py`                            | `RuntimeHealthCollector` + `get_health_collector()` singleton |
| Modify   | `backend/app/ml/drift/monitor.py`                                     | Add `_latest_psi` dict; populate in `_check_drift()` |
| Modify   | `backend/app/main.py`                                                 | Start/stop `RuntimeHealthCollector` in lifespan |
| Modify   | `backend/app/services/broadcast_service.py`                           | No signature change; already correct |
| Modify   | `frontend/web_dashboard/admin_dashboard/screens/others.jsx` (worktree)| Add health grid to `MonitoringScreen` |
| Modify   | `frontend/web_dashboard/admin_dashboard/app.jsx` (worktree)           | Add `cityHealth` state + health WS subscription |
| Modify   | `.env.example`                                                        | Document `HealthCollectorConfig` env vars |

---

## Testing Notes

- The 13 regression tests in `tests/test_mc_inference.py` from Group A cover the prediction path. Group D adds no new prediction logic — the counters are append-only side effects.
- The two pre-existing failures (`test_predict_missing_city`, `test_predict_v2_missing_required`) are not regressions from any Group; do not fix them in Group D.
- New tests should cover:
  - `get_mc_success_rate()` returns `None` for <10 observations, correct fraction otherwise
  - `RuntimeHealthCollector._build_snapshot()` returns `"unknown"` global status when all cities have no observations
  - `CityHealthSnapshot` validates correctly via Pydantic
  - The `_tick_inference_health()` correctly maps threshold crossings to `"ok"` / `"degraded"` / `"critical"`
  - Epistemic warmup: `"warming_up"` before `EPISTEMIC_WARMUP_MIN_SAMPLES`, baseline set after

---

## What This Is Not

- Not a persistence layer — no DB table for health snapshots.
- Not an alert system — status strings are for operator awareness; they do not trigger SMS/email. (That is Domain 4, out of scope.)
- Not a performance regression — all counters are `deque.append` (O(1), thread-safe in CPython). Background tasks are asyncio, not threads; they do not compete with the TF thread pool.
