# HydroGuard-AI v3.3 — Audit Fixes Design Spec

**Date:** 2026-05-27
**Scope:** 6 audit-driven fixes unified into a coherent runtime architecture upgrade
**Platform framing:** Observational probabilistic inference from live Weather API data, not physical hydrological simulation. The system produces calibrated probabilistic risk estimates — not guaranteed flood predictions or evacuation orders.

---

## Context

An external audit of v3.2 identified 6 critical gaps:

1. No background polling — city risk state only updates on-demand
2. Single flat alert threshold (31.8% precision) — no advisory/alert distinction
3. `/cities/overview` returns hardcoded zero-fill weather instead of live data
4. Alembic exists but is not wired into startup — schema evolution untraceable
5. Feature names in SHAP drivers are internal ML names, not human-readable labels
6. WebSocket fan-out is per-worker with no Redis bridge for multi-worker deployments

These are addressed as a unified architectural upgrade, not isolated patches. All 6 fixes reinforce the same principles: runtime determinism, dataset-driven behavior, operational traceability, graceful degradation, and separation of responsibilities.

---

## Architecture: Approach B+ (Modular with Runtime Control Plane)

Each fix is a self-contained module. Two new anchors prevent the "clean chaos" problem:

- **`runtime/system_runtime.py`** — central execution state (not business logic)
- **`runtime/bootstrap.py`** — initialization sequence extracted from `main.py` lifespan

### Invariants preserved throughout

1. **Unidirectional event flow**: `predict_v2()` → `runtime.emit_result()` → `ACTIVE_BROADCASTER` → transport → WS clients. No cycles. No side-channel emission.
2. **Single event origin**: only `runtime.emit_result()` calls the broadcaster. `polling_service`, HTTP endpoints, and background tasks all funnel through this one function.
3. **`broadcast_service.py` is a compatibility layer pending retirement** — v1 paths continue to use it; v2 paths use `emit_result()`. The two must never permanently coexist as dual event origins.
4. **Transport invisibility**: the rest of the codebase does not know whether delivery is local memory or Redis pub/sub.
5. **Inference pipeline is singular**: overview, polling, and HTTP predict all route through `city_model_service.predict_v2()`. No parallel inference stacks.

---

## New Modules

### `backend/app/runtime/system_runtime.py`

Holds only runtime state — no business logic.

```
WORKER_MODE: "single" | "multi"          # read from WORKERS env var at import time
ACTIVE_BROADCASTER: AbstractBroadcaster  # set during bootstrap.init_broadcaster()
FEATURE_FLAGS: dict                      # e.g. {"polling_enabled": True, "redis_ws_enabled": False}
```

**`emit_result(result: dict) -> Coroutine`** — the only function in the codebase allowed to call `ACTIVE_BROADCASTER.broadcast()`. All code paths (HTTP, polling, background tasks) import and call this function. Nothing else calls the broadcaster directly.

### `backend/app/runtime/bootstrap.py`

Initialization sequence extracted from `main.py` lifespan. `lifespan()` becomes:

```python
@asynccontextmanager
async def lifespan(app):
    await bootstrap.run(app)
    yield
    await bootstrap.shutdown()
```

`bootstrap.run()` executes (in order, each step non-fatal unless marked *):

1. `validate_startup_secrets()` *
2. Alembic `upgrade head` programmatically, then `init_db()` as safety net
3. `init_redis()`
4. `init_weather_provider()`
5. `init_rolling_window()`, `init_event_bus()`, `init_drift_monitor()`, `init_calibration_service()`
6. `init_broadcaster()` — selects `LocalBroadcaster` or `RedisBroadcaster` based on `WORKER_MODE`
7. `city_model_service.model_status()` log + `warm_up_tcn_buffers()`
8. `init_alert_tiers()` — loads per-city `AlertTierClassifier` from `cal_data.npz`
9. `start_polling()` — starts `WeatherPollingService` after warm-up completes
10. `RuntimeHealthCollector.start()`

`bootstrap.shutdown()` stops polling → stops health collector → unsubscribes broadcaster → closes Redis.

### `backend/app/realtime/broadcaster.py`

Three classes, one interface:

```python
class AbstractBroadcaster(ABC):
    async def broadcast(self, channel: str, data: dict) -> None: ...
    async def close(self) -> None: ...

class LocalBroadcaster(AbstractBroadcaster):
    # Wraps existing ConnectionManager — untouched
    async def broadcast(self, channel, data): await manager.broadcast(channel, data)
    async def close(self): pass  # no-op

class RedisBroadcaster(AbstractBroadcaster):
    # Dormant unless WORKER_MODE="multi"
    async def broadcast(self, channel, data):
        await self._redis.publish(f"hg:ws:{channel}", json.dumps(data))
    async def start_subscribers(self, manager: ConnectionManager) -> None:
        # One asyncio.Task per channel — listens on Redis, forwards to local ConnectionManager
        # Tasks are owned by bootstrap, not by RedisBroadcaster itself
    async def close(self):
        # cancel subscriber tasks, unsubscribe, close redis connection
```

**Activation in `bootstrap.init_broadcaster()`:**
```python
if WORKER_MODE == "multi" and redis_available:
    runtime.ACTIVE_BROADCASTER = RedisBroadcaster(redis_client)
    await runtime.ACTIVE_BROADCASTER.start_subscribers(manager)
else:
    runtime.ACTIVE_BROADCASTER = LocalBroadcaster(manager)
runtime.FEATURE_FLAGS["redis_ws_enabled"] = isinstance(runtime.ACTIVE_BROADCASTER, RedisBroadcaster)
```

**Redis subscriber discipline:** subscriber tasks are transport-pure — they forward payloads unchanged. They never classify alerts, modify payloads, or trigger inference. They are channel forwarders, not business logic processors.

**`ConnectionManager`** (`realtime/manager.py`) is untouched. `LocalBroadcaster` wraps it; no existing WebSocket semantics change.

### `backend/app/services/alert_tier.py`

```python
@dataclass
class AlertTierResult:
    tier: Literal["NORMAL", "ADVISORY", "ALERT"]
    push_notification: bool
    advisory_threshold: float
    alert_threshold: float

class AlertTierClassifier:
    @classmethod
    def from_cal_data(cls, cal_data_path: Path) -> "AlertTierClassifier":
        # Load cal_data.npz (arrays: y_true, y_score)
        # precision_recall_curve(y_true, y_score) → prec, rec, thresh
        # advisory_threshold = max(thresh[rec[:-1] >= 0.85], default=0.35)
        # alert_threshold    = min(thresh[prec[:-1] >= 0.65], default=0.65)
        # Enforce: advisory < alert; log warning + use defaults on inversion/failure
        ...

    def classify(self, event_probability: float) -> AlertTierResult:
        if event_probability >= self.alert_threshold:
            return AlertTierResult("ALERT", push_notification=True, ...)
        if event_probability >= self.advisory_threshold:
            return AlertTierResult("ADVISORY", push_notification=False, ...)
        return AlertTierResult("NORMAL", push_notification=False, ...)
```

**Loading:** `CityModelService._load_model(slug)` calls `AlertTierClassifier.from_cal_data(cal_data_path)`. Each city gets its own classifier stored in `_alert_tiers: dict[str, AlertTierClassifier]`. If `cal_data.npz` is absent, `AlertTierClassifier(0.35, 0.65)` is used with a logged warning.

**Integration into `predict_v2()`:** after `IsotonicCalibrator` produces `event_probability`, call `_alert_tiers[slug].classify(event_probability)`. Merge into output dict as additive fields:

```
# Existing (preserved for backward compat):
  is_alert, alert_tier (int 1–5), risk_band

# New (additive):
  alert_tier_label: "NORMAL" | "ADVISORY" | "ALERT"
  push_notification: bool
  advisory_threshold: float   (derived from cal_data, echoed for auditability)
  alert_threshold: float
```

**Semantic note:** `ALERT` tier means *elevated probability of hazardous conditions based on learned patterns*, not guaranteed flood occurrence. Labels must not be treated as physical disaster confirmations.

### `backend/app/services/polling_service.py`

```python
class WeatherPollingService:
    def __init__(self, weather_provider, city_model_service,
                 interval_seconds: int = 900):  # POLLING_INTERVAL_SECONDS env var
        self._interval = interval_seconds
        self._last_snapshots: dict[str, dict] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_polling")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_all()

    async def _poll_all(self) -> None:
        slugs = city_model_service.list_slugs()
        results = await asyncio.gather(
            *[self._poll_city(s) for s in slugs], return_exceptions=True
        )
        for slug, r in zip(slugs, results):
            if isinstance(r, Exception):
                logger.error("polling_failed city=%s error=%s", slug, r)

    async def _poll_city(self, slug: str) -> None:
        snap = await weather_provider.get_current(slug, force_refresh=True)
        if snap is None:
            return
        raw = snap.to_feature_dict()
        if not self._has_significant_change(self._last_snapshots.get(slug, {}), raw):
            return
        result = await city_model_service.predict_v2(slug, raw)
        await runtime.emit_result(result)   # ← single event origin
        if result.get("alert_tier_label") != "NORMAL":
            # _persist_prediction is the shared helper from app.api.v2.cities —
            # imported at call site to avoid circular import; no logic duplication.
            from app.api.v2.cities import _persist_prediction
            asyncio.create_task(_persist_prediction(result, raw))
        self._last_snapshots[slug] = raw
```

**Responsibilities:** scheduling, fetching, triggering, forwarding. Nothing else.

**Not responsible for:** alert classification, DB persistence logic, broadcaster selection, inference behavior, notification policy.

**Change detection thresholds** (`_has_significant_change`): `prcp > 0.5mm`, `pressure > 1.5hPa`, `humidity > 5%`. Stored in `runtime.FEATURE_FLAGS["polling_sensitivity"]` so they are adjustable without touching the polling logic.

**Persistence rule:** only ADVISORY and ALERT tier results write to DB. NORMAL readings do not generate DB rows — prevents analytics charts from being drowned in calm-weather noise. Future consideration: compressed telemetry retention or rolling aggregates may be needed to preserve pre-event baseline context.

**Lifecycle:** started in `bootstrap.run()` step 9 (after TCN warm-up and alert tier init). Stopped in `bootstrap.shutdown()` before broadcaster teardown.

### `backend/app/config/feature_display.py`

```python
FEATURE_DISPLAY_MAP: dict[str, str] = {
    "pressure_delta_3h":    "pressure_delta_1step (daily resolution)",
    "pressure_delta_6h":    "pressure_delta_2step (daily resolution)",
    "rain_rate_1h":         "rain_rate_1step (daily resolution)",
    "rain_accumulation_3h": "rain_accumulation_3step (daily resolution)",
    "cloud_jump_3h":        "cloud_jump_3step (daily resolution)",
}

def display_name(feature: str) -> str:
    return FEATURE_DISPLAY_MAP.get(feature, feature)
```

Applied **only** in `predict_v2()` output: the `drivers` list maps each feature name through `display_name()` before the dict is returned. Internal `FUSION_FEATURES`, all model artifacts, and SHAP computation are untouched — internal names never change.

---

## Modified Files

### `backend/app/main.py`

Becomes thin:

```python
@asynccontextmanager
async def lifespan(app):
    await bootstrap.run(app)
    yield
    await bootstrap.shutdown()

def create_app() -> FastAPI:
    app = FastAPI(..., lifespan=lifespan)
    # middleware, exception handlers, router includes — unchanged
    return app
```

No initialization logic lives in `main.py` after this change.

### `backend/app/api/v2/cities.py` — `cities_overview()`

```python
@router.get("/overview")
async def cities_overview():
    cities = city_model_service.list_cities()
    slugs  = [c["slug"] for c in cities]
    snaps  = await asyncio.gather(
        *[_fetch_weather(slug) for slug in slugs], return_exceptions=True
    )
    results = []
    for c, snap in zip(cities, snaps):
        raw    = snap.to_feature_dict() if not isinstance(snap, Exception) else {}
        result = await city_model_service.predict_v2(c["slug"], raw)
        results.append({"slug": c["slug"], "name": c["name"],
                        "risk_band": result.get("risk_band"), ...})
    return {"cities": results, "live_weather": True}

async def _fetch_weather(slug: str) -> WeatherSnapshot:
    from app.services.weather_api import weather_provider
    if weather_provider is None:
        raise RuntimeError("weather_provider not initialised")
    return await weather_provider.get_current(slug)
    # Exceptions propagate to asyncio.gather → caught as Exception objects →
    # isinstance(snap, Exception) check in caller produces zero-fill fallback.
```

All city weather fetches run in parallel. Falls back to zero-fill on any per-city weather failure — logged, non-fatal.

### `backend/app/db/database.py` — `init_db()`

`bootstrap.run()` calls `alembic upgrade head` programmatically (step 2) before `init_db()`. `init_db()` keeps `create_all()` as a safety net for any table not yet covered by a migration. This hybrid is intentional and appropriate at FYP scale; long-term, migrations become authoritative.

---

## Files NOT Modified

- `backend/app/realtime/manager.py` — `ConnectionManager` untouched; `LocalBroadcaster` wraps it
- `backend/app/services/broadcast_service.py` — v1 compatibility layer; no changes; **classified as pending retirement**
- `backend/app/ml/models/fusion.py` — `FUSION_FEATURES` list and all training/inference logic untouched
- All model artifacts, repositories, auth, schemas, ORM models — untouched

---

## New File Summary

| File | Purpose |
|---|---|
| `backend/app/runtime/system_runtime.py` | Runtime state: WORKER_MODE, ACTIVE_BROADCASTER, FEATURE_FLAGS, `emit_result()` |
| `backend/app/runtime/bootstrap.py` | 10-step init sequence extracted from `main.py` |
| `backend/app/realtime/broadcaster.py` | AbstractBroadcaster, LocalBroadcaster, RedisBroadcaster |
| `backend/app/services/alert_tier.py` | AlertTierClassifier: PR-curve derivation + runtime classification |
| `backend/app/services/polling_service.py` | WeatherPollingService: schedule, fetch, trigger, forward |
| `backend/app/config/feature_display.py` | FEATURE_DISPLAY_MAP + display_name() helper |

---

## Constraints

- The ML model does not decide evacuation semantics — the interpretation layer (`alert_tier`) does
- Thresholds derived at model-load time, not dynamically at inference — deterministic, auditable
- Redis subscribers are transport-pure — no business logic, no payload modification
- `broadcast_service.py` is a compatibility layer, not a permanent event path
- Internal feature names never change — display mapping is presentation-only
- Alembic governs production schema; `create_all()` is dev safety net only
- **`predict_v2(slug, raw)` is treated as deterministic for identical inputs** — this is a hard system invariant required for correctness under polling retries, Redis replay, and multi-worker fan-out. Any future change that makes inference non-deterministic (e.g., time-dependent state, random side effects) must be explicitly flagged and reviewed against this invariant.

## Future Evolution Notes (not in scope now)

- Polling sensitivity thresholds (`FEATURE_FLAGS["polling_sensitivity"]`) are runtime policy controls, not pure heuristics — future work may derive them statistically per city
- NORMAL-state exclusion from DB may require compressed aggregation or periodic baseline snapshots to support pre-event context reconstruction and calibration drift detection
- Redis subscriber lifecycle may eventually migrate into a dedicated transport runtime layer as the system scales to many workers
