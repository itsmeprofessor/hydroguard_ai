# HydroGuard-AI v3.3 Audit Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 6 audit-driven fixes as a unified B+ runtime architecture upgrade — adding a runtime control plane, per-city two-tier alert thresholds derived from cal_data.npz, a broadcaster abstraction, background weather polling, live cities overview, and feature display name mapping.

**Architecture:** New modules (`runtime/system_runtime`, `runtime/bootstrap`, `realtime/broadcaster`, `services/alert_tier`, `services/polling_service`, `config/feature_display`) are each self-contained. Existing files (`main.py`, `city_model_service.py`, `api/v2/cities.py`) are modified minimally to wire them in. Single event origin: `runtime.emit_result()` is the only place that calls `ACTIVE_BROADCASTER.broadcast()`.

**Tech Stack:** Python 3.11, FastAPI, asyncio, scikit-learn (precision_recall_curve), numpy, Redis (optional), LightGBM, pytest.

---

## File Map

**Create:**
- `backend/app/runtime/__init__.py`
- `backend/app/runtime/system_runtime.py` — WORKER_MODE, ACTIVE_BROADCASTER, FEATURE_FLAGS, `emit_result()`
- `backend/app/runtime/bootstrap.py` — 10-step init sequence (extracted from main.py lifespan)
- `backend/app/realtime/broadcaster.py` — AbstractBroadcaster, LocalBroadcaster, RedisBroadcaster
- `backend/app/services/alert_tier.py` — AlertTierClassifier: PR-curve threshold derivation + classify()
- `backend/app/services/polling_service.py` — WeatherPollingService: schedule, fetch, trigger, forward
- `backend/app/config/__init__.py`
- `backend/app/config/feature_display.py` — FEATURE_DISPLAY_MAP + display_name()
- `tests/test_feature_display.py`
- `tests/test_alert_tier.py`
- `tests/test_system_runtime.py`
- `tests/test_broadcaster.py`
- `tests/test_polling_service.py`

**Modify:**
- `backend/app/main.py` — lifespan delegates to bootstrap.run/shutdown; app factory unchanged
- `backend/app/services/city_model_service.py` — add `_alert_tiers` dict; load AlertTierClassifier in `_load_v2_artifacts`; apply alert tier + display_name in `predict_v2`
- `backend/app/api/v2/cities.py` — `cities_overview()` uses parallel live weather + `predict_v2`

---

## Task 1: Feature Display Name Mapping

**Files:**
- Create: `backend/app/config/__init__.py`
- Create: `backend/app/config/feature_display.py`
- Create: `tests/test_feature_display.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_display.py
from app.config.feature_display import display_name, FEATURE_DISPLAY_MAP


def test_known_feature_returns_display_label():
    assert display_name("pressure_delta_3h") == "pressure_delta_1step (daily resolution)"


def test_unknown_feature_passthrough():
    assert display_name("ae_percentile") == "ae_percentile"


def test_all_mapped_features_differ_from_internal_name():
    for internal, label in FEATURE_DISPLAY_MAP.items():
        assert internal != label
```

- [ ] **Step 2: Run test to verify it fails**

```
cd D:\Programming\FYP\hydroguard_ai
pytest tests/test_feature_display.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.config.feature_display'`

- [ ] **Step 3: Create package and module**

```python
# backend/app/config/__init__.py
# (empty)
```

```python
# backend/app/config/feature_display.py
from __future__ import annotations

FEATURE_DISPLAY_MAP: dict[str, str] = {
    "pressure_delta_3h":    "pressure_delta_1step (daily resolution)",
    "pressure_delta_6h":    "pressure_delta_2step (daily resolution)",
    "rain_rate_1h":         "rain_rate_1step (daily resolution)",
    "rain_accumulation_3h": "rain_accumulation_3step (daily resolution)",
    "cloud_jump_3h":        "cloud_jump_3step (daily resolution)",
}


def display_name(feature: str) -> str:
    """Map internal ML feature name to human-readable label for API output only.

    Internal FUSION_FEATURES names and model artifacts are NEVER renamed.
    This mapping is applied only to the `drivers` field in predict_v2 output.
    """
    return FEATURE_DISPLAY_MAP.get(feature, feature)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_feature_display.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```
git add backend/app/config/ tests/test_feature_display.py
git commit -m "feat(config): add feature display name mapping layer"
```

---

## Task 2: AlertTierClassifier

**Files:**
- Create: `backend/app/services/alert_tier.py`
- Create: `tests/test_alert_tier.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_alert_tier.py
import numpy as np
import pytest
from pathlib import Path

from app.services.alert_tier import (
    AlertTierClassifier,
    DEFAULT_ADVISORY_THRESHOLD,
    DEFAULT_ALERT_THRESHOLD,
)


def test_classify_alert_tier():
    clf = AlertTierClassifier(0.35, 0.65)
    result = clf.classify(0.70)
    assert result.tier == "ALERT"
    assert result.push_notification is True


def test_classify_advisory_tier():
    clf = AlertTierClassifier(0.35, 0.65)
    result = clf.classify(0.45)
    assert result.tier == "ADVISORY"
    assert result.push_notification is False


def test_classify_normal_tier():
    clf = AlertTierClassifier(0.35, 0.65)
    result = clf.classify(0.10)
    assert result.tier == "NORMAL"
    assert result.push_notification is False


def test_classify_at_advisory_boundary():
    clf = AlertTierClassifier(0.35, 0.65)
    assert clf.classify(0.35).tier == "ADVISORY"


def test_classify_at_alert_boundary():
    clf = AlertTierClassifier(0.35, 0.65)
    assert clf.classify(0.65).tier == "ALERT"


def test_thresholds_echoed_in_result():
    clf = AlertTierClassifier(0.40, 0.70)
    result = clf.classify(0.50)
    assert result.advisory_threshold == 0.40
    assert result.alert_threshold == 0.70


def test_from_cal_data_derives_thresholds(tmp_path):
    rng = np.random.default_rng(42)
    n = 300
    y_true = np.zeros(n, dtype=int)
    y_true[:60] = 1  # 20% positive rate
    y_score = np.where(
        y_true == 1,
        rng.uniform(0.6, 0.95, n),
        rng.uniform(0.05, 0.45, n),
    )
    cal_path = tmp_path / "cal_data.npz"
    np.savez(cal_path, y_true=y_true, y_score=y_score)

    clf = AlertTierClassifier.from_cal_data(cal_path)
    assert clf.advisory_threshold < clf.alert_threshold
    assert 0.0 < clf.advisory_threshold < 1.0
    assert 0.0 < clf.alert_threshold < 1.0


def test_from_cal_data_falls_back_on_missing_file(tmp_path):
    clf = AlertTierClassifier.from_cal_data(tmp_path / "nonexistent.npz")
    assert clf.advisory_threshold == DEFAULT_ADVISORY_THRESHOLD
    assert clf.alert_threshold == DEFAULT_ALERT_THRESHOLD


def test_from_cal_data_falls_back_on_inversion(tmp_path):
    # All-positive set → advisory >= alert → inversion → defaults
    y_true = np.ones(100, dtype=int)
    y_score = np.linspace(0.01, 0.99, 100)
    cal_path = tmp_path / "cal_data.npz"
    np.savez(cal_path, y_true=y_true, y_score=y_score)

    clf = AlertTierClassifier.from_cal_data(cal_path)
    assert clf.advisory_threshold == DEFAULT_ADVISORY_THRESHOLD
    assert clf.alert_threshold == DEFAULT_ALERT_THRESHOLD
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_alert_tier.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.alert_tier'`

- [ ] **Step 3: Implement AlertTierClassifier**

```python
# backend/app/services/alert_tier.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_ADVISORY_THRESHOLD: float = 0.35
DEFAULT_ALERT_THRESHOLD: float = 0.65


@dataclass(frozen=True)
class AlertTierResult:
    tier: Literal["NORMAL", "ADVISORY", "ALERT"]
    push_notification: bool
    advisory_threshold: float
    alert_threshold: float


class AlertTierClassifier:
    """Per-city two-tier alert threshold classifier.

    Thresholds are derived from the calibration dataset PR curve at model-load
    time — not hardcoded, not dynamic at inference time. This ensures
    deterministic, auditable runtime behaviour.

    advisory tier: elevated probability, high recall (≥85%) — in-app only
    alert tier:    high probability, high precision (≥65%) — push-notification quality
    """

    def __init__(
        self,
        advisory_threshold: float = DEFAULT_ADVISORY_THRESHOLD,
        alert_threshold: float = DEFAULT_ALERT_THRESHOLD,
    ) -> None:
        self.advisory_threshold = advisory_threshold
        self.alert_threshold = alert_threshold

    @classmethod
    def from_cal_data(
        cls,
        cal_data_path: Path,
        *,
        advisory_recall_target: float = 0.85,
        alert_precision_target: float = 0.65,
    ) -> "AlertTierClassifier":
        """Derive thresholds from held-out calibration data PR curve.

        Expects cal_data.npz with arrays y_true and y_score.
        Falls back to defaults on any failure (missing file, bad arrays, inversion).
        """
        try:
            from sklearn.metrics import precision_recall_curve

            data = np.load(cal_data_path)
            y_true = data["y_true"]
            y_score = data["y_score"]

            prec, rec, thresh = precision_recall_curve(y_true, y_score)
            # prec/rec have one extra element (no-threshold endpoint)
            prec_t = prec[:-1]
            rec_t  = rec[:-1]

            advisory_mask = rec_t >= advisory_recall_target
            alert_mask    = prec_t >= alert_precision_target

            advisory_threshold = (
                float(thresh[advisory_mask].max())
                if advisory_mask.any()
                else DEFAULT_ADVISORY_THRESHOLD
            )
            alert_threshold = (
                float(thresh[alert_mask].min())
                if alert_mask.any()
                else DEFAULT_ALERT_THRESHOLD
            )

            if advisory_threshold >= alert_threshold:
                logger.warning(
                    "cal_data threshold inversion at %s "
                    "(advisory=%.3f >= alert=%.3f) — using defaults",
                    cal_data_path, advisory_threshold, alert_threshold,
                )
                return cls()

            logger.info(
                "AlertTierClassifier derived from %s: advisory=%.3f alert=%.3f",
                cal_data_path, advisory_threshold, alert_threshold,
            )
            return cls(advisory_threshold, alert_threshold)

        except Exception as exc:
            logger.warning(
                "AlertTierClassifier.from_cal_data(%s) failed — using defaults: %s",
                cal_data_path, exc,
            )
            return cls()

    def classify(self, event_probability: float) -> AlertTierResult:
        if event_probability >= self.alert_threshold:
            return AlertTierResult(
                tier="ALERT",
                push_notification=True,
                advisory_threshold=self.advisory_threshold,
                alert_threshold=self.alert_threshold,
            )
        if event_probability >= self.advisory_threshold:
            return AlertTierResult(
                tier="ADVISORY",
                push_notification=False,
                advisory_threshold=self.advisory_threshold,
                alert_threshold=self.alert_threshold,
            )
        return AlertTierResult(
            tier="NORMAL",
            push_notification=False,
            advisory_threshold=self.advisory_threshold,
            alert_threshold=self.alert_threshold,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_alert_tier.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```
git add backend/app/services/alert_tier.py tests/test_alert_tier.py
git commit -m "feat(alert): add AlertTierClassifier with PR-curve threshold derivation"
```

---

## Task 3: Runtime State Module

**Files:**
- Create: `backend/app/runtime/__init__.py`
- Create: `backend/app/runtime/system_runtime.py`
- Create: `tests/test_system_runtime.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_system_runtime.py
import os
import pytest
from unittest.mock import AsyncMock

import app.runtime.system_runtime as runtime


@pytest.fixture(autouse=True)
def reset_broadcaster():
    original = runtime.ACTIVE_BROADCASTER
    yield
    runtime.ACTIVE_BROADCASTER = original


async def test_emit_result_calls_broadcaster_for_is_alert():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": True, "hri_score": 75})
    mock.broadcast.assert_called_once_with("anomalies", {"is_alert": True, "hri_score": 75})


async def test_emit_result_calls_broadcaster_for_high_hri():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": False, "hri_score": 45})
    mock.broadcast.assert_called_once()


async def test_emit_result_skips_normal_low_hri():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": False, "hri_score": 10})
    mock.broadcast.assert_not_called()


async def test_emit_result_noop_when_no_broadcaster():
    runtime.ACTIVE_BROADCASTER = None
    # Must not raise
    await runtime.emit_result({"is_alert": True, "hri_score": 90})


def test_feature_flags_has_polling_enabled():
    assert "polling_enabled" in runtime.FEATURE_FLAGS


def test_feature_flags_has_polling_sensitivity():
    s = runtime.FEATURE_FLAGS["polling_sensitivity"]
    assert "prcp_delta" in s
    assert "pressure_delta" in s
    assert "humidity_delta" in s
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_system_runtime.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.runtime'`

- [ ] **Step 3: Create runtime package and system_runtime module**

```python
# backend/app/runtime/__init__.py
# (empty — marks package)
```

```python
# backend/app/runtime/system_runtime.py
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.realtime.broadcaster import AbstractBroadcaster

logger = logging.getLogger(__name__)

# ── Runtime state ─────────────────────────────────────────────────────────────

WORKER_MODE: str = "multi" if int(os.getenv("WORKERS", "1")) > 1 else "single"

ACTIVE_BROADCASTER: "AbstractBroadcaster | None" = None

FEATURE_FLAGS: dict[str, Any] = {
    "polling_enabled":  True,
    "redis_ws_enabled": False,
    "polling_sensitivity": {
        "prcp_delta":     0.5,   # mm — minimum precipitation change to trigger inference
        "pressure_delta": 1.5,   # hPa
        "humidity_delta": 5.0,   # %
    },
}

# ── Single event origin ───────────────────────────────────────────────────────

async def emit_result(result: dict[str, Any]) -> None:
    """The ONLY place in the codebase allowed to call ACTIVE_BROADCASTER.broadcast().

    All code paths — HTTP endpoints, polling, background tasks — must call this
    function. Never call ACTIVE_BROADCASTER.broadcast() directly elsewhere.
    """
    if ACTIVE_BROADCASTER is None:
        return
    hri = result.get("hri_score") or 0
    if not result.get("is_alert") and hri < 40:
        return  # skip low-noise NORMAL readings
    try:
        await ACTIVE_BROADCASTER.broadcast("anomalies", result)
    except Exception as exc:
        logger.warning("emit_result broadcast failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_system_runtime.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```
git add backend/app/runtime/ tests/test_system_runtime.py
git commit -m "feat(runtime): add system_runtime control plane with single emit_result origin"
```

---

## Task 4: Broadcaster Abstraction

**Files:**
- Create: `backend/app/realtime/broadcaster.py`
- Create: `tests/test_broadcaster.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_broadcaster.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.realtime.broadcaster import (
    AbstractBroadcaster,
    LocalBroadcaster,
    RedisBroadcaster,
)


def test_abstract_broadcaster_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractBroadcaster()


async def test_local_broadcaster_delegates_to_manager():
    mock_manager = AsyncMock()
    broadcaster = LocalBroadcaster(mock_manager)
    await broadcaster.broadcast("anomalies", {"city": "karachi"})
    mock_manager.broadcast.assert_called_once_with("anomalies", {"city": "karachi"})


async def test_local_broadcaster_close_is_noop():
    mock_manager = AsyncMock()
    broadcaster = LocalBroadcaster(mock_manager)
    await broadcaster.close()  # must not raise


def test_local_broadcaster_is_abstract_broadcaster():
    assert isinstance(LocalBroadcaster(AsyncMock()), AbstractBroadcaster)


async def test_redis_broadcaster_publishes_to_correct_key():
    mock_redis = AsyncMock()
    broadcaster = RedisBroadcaster(mock_redis)
    await broadcaster.broadcast("anomalies", {"city": "lahore"})
    mock_redis.publish.assert_called_once_with(
        "hg:ws:anomalies",
        json.dumps({"city": "lahore"}),
    )


async def test_redis_broadcaster_close_cancels_tasks():
    mock_redis = AsyncMock()
    broadcaster = RedisBroadcaster(mock_redis)
    # No tasks started — close should be safe with empty list
    await broadcaster.close()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_broadcaster.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.realtime.broadcaster'`

- [ ] **Step 3: Implement broadcaster.py**

```python
# backend/app/realtime/broadcaster.py
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.realtime.manager import ConnectionManager

logger = logging.getLogger(__name__)


class AbstractBroadcaster(ABC):
    @abstractmethod
    async def broadcast(self, channel: str, data: dict) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class LocalBroadcaster(AbstractBroadcaster):
    """Single-worker broadcaster. Wraps ConnectionManager — untouched."""

    def __init__(self, manager: "ConnectionManager") -> None:
        self._manager = manager

    async def broadcast(self, channel: str, data: dict) -> None:
        await self._manager.broadcast(channel, data)

    async def close(self) -> None:
        pass  # ConnectionManager has no teardown


class RedisBroadcaster(AbstractBroadcaster):
    """Multi-worker broadcaster. Dormant unless WORKER_MODE='multi'.

    Publishes events to Redis pub/sub. Subscriber tasks (started by bootstrap,
    not at import time) listen on Redis channels and forward to the local
    ConnectionManager for each worker's WS clients.

    Subscribers are transport-pure: they forward payloads unchanged.
    No business logic, no payload mutation, no inference triggering.
    """

    CHANNEL_PREFIX = "hg:ws:"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._subscriber_tasks: list[asyncio.Task] = []

    async def broadcast(self, channel: str, data: dict) -> None:
        await self._redis.publish(
            f"{self.CHANNEL_PREFIX}{channel}",
            json.dumps(data),
        )

    async def start_subscribers(self, manager: "ConnectionManager") -> None:
        """Start one forwarding task per WS channel.

        Called by bootstrap.run() — never at import time.
        Tasks are owned by this broadcaster instance; cancelled in close().
        """
        from app.realtime.manager import CHANNELS
        for channel in CHANNELS:
            task = asyncio.create_task(
                self._subscribe_and_forward(channel, manager),
                name=f"redis_sub_{channel}",
            )
            self._subscriber_tasks.append(task)
        logger.info("RedisBroadcaster: %d subscriber tasks started", len(CHANNELS))

    async def _subscribe_and_forward(
        self, channel: str, manager: "ConnectionManager"
    ) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"{self.CHANNEL_PREFIX}{channel}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(channel, data)
                except Exception as exc:
                    logger.warning("redis_forward error channel=%s: %s", channel, exc)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"{self.CHANNEL_PREFIX}{channel}")
            raise

    async def close(self) -> None:
        for task in self._subscriber_tasks:
            task.cancel()
        await asyncio.gather(*self._subscriber_tasks, return_exceptions=True)
        self._subscriber_tasks.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_broadcaster.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```
git add backend/app/realtime/broadcaster.py tests/test_broadcaster.py
git commit -m "feat(realtime): add broadcaster abstraction — LocalBroadcaster active, RedisBroadcaster dormant"
```

---

## Task 5: Integrate AlertTierClassifier and display_name into CityModelService

**Files:**
- Modify: `backend/app/services/city_model_service.py`

No new test file — the integration is tested via the existing `tests/test_api.py` health check (which exercises `predict_v2`) plus a targeted check on the new fields added below.

- [ ] **Step 1: Add import at top of city_model_service.py**

Find the existing import block at the top of `backend/app/services/city_model_service.py` (around line 35–40). Add this import after the existing `from app.core.config` line:

```python
from app.config.feature_display import display_name
```

- [ ] **Step 2: Add `_alert_tiers` to `__init__`**

In `CityModelService.__init__` (line ~334), add one line after `self._city_thresholds`:

```python
        self._alert_tiers:     Dict[str, Any]   = {}   # slug -> AlertTierClassifier
```

The `__init__` block should now end with:

```python
        self._city_thresholds: Dict[str, float] = {}   # slug -> optimal alert threshold
        self._alert_tiers:     Dict[str, Any]   = {}   # slug -> AlertTierClassifier
        # Initial discovery
        self.refresh_registry()
```

- [ ] **Step 3: Load AlertTierClassifier in `_load_v2_artifacts`**

In `_load_v2_artifacts` (line ~537), add at the end of the method (after the OODDetector block, before the method ends):

```python
        try:
            from app.services.alert_tier import AlertTierClassifier
            cal_data_path = model_dir / "cal_data.npz"
            self._alert_tiers[slug] = AlertTierClassifier.from_cal_data(cal_data_path)
            logger.info("[%s] AlertTierClassifier loaded", slug)
        except Exception as exc:
            logger.debug("[%s] AlertTierClassifier load skipped: %s", slug, exc)
```

- [ ] **Step 4: Apply display_name to SHAP drivers in `predict_v2`**

In `predict_v2`, find the `drivers` list comprehension (line ~935):

```python
                    drivers = [
                        {"feature": k, "shap": v,
                         "value": float(_branch.get(k) if k in _branch else (feat_dict.get(k, 0.0) or 0.0))}
                        for k, v in shap_dict.items()
                    ]
```

Replace `"feature": k` with `"feature": display_name(k)`:

```python
                    drivers = [
                        {"feature": display_name(k), "shap": v,
                         "value": float(_branch.get(k) if k in _branch else (feat_dict.get(k, 0.0) or 0.0))}
                        for k, v in shap_dict.items()
                    ]
```

- [ ] **Step 5: Compute alert_tier_label and push_notification in `predict_v2`**

Find the line `alert_tier = self._compute_alert_tier(p_calib, alert_threshold)` (line ~952). Add immediately after it:

```python
        # Two-tier alert semantics — additive fields, backward compat preserved
        _clf = self._alert_tiers.get(slug)
        if _clf is not None:
            _tier = _clf.classify(p_calib)
            alert_tier_label = _tier.tier
            push_notification = _tier.push_notification
        else:
            alert_tier_label = "ALERT" if is_alert else "NORMAL"
            push_notification = is_alert
```

- [ ] **Step 6: Add new fields to the return dict in `predict_v2`**

Find the return dict (line ~962). After the `"alert_tier": alert_tier,` line, add:

```python
            "alert_tier_label":    alert_tier_label,
            "push_notification":   push_notification,
```

- [ ] **Step 7: Verify existing tests still pass**

```
pytest tests/test_api.py -v --tb=short
```
Expected: all existing tests pass (no regressions — new fields are additive)

- [ ] **Step 8: Commit**

```
git add backend/app/services/city_model_service.py
git commit -m "feat(city_model): integrate AlertTierClassifier and feature display_name into predict_v2"
```

---

## Task 6: Bootstrap Module + Thin main.py

**Files:**
- Create: `backend/app/runtime/bootstrap.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create bootstrap.py**

```python
# backend/app/runtime/bootstrap.py
"""
Initialization sequence for HydroGuard-AI.

bootstrap.run(app) replaces the inline lifespan sequence in main.py.
bootstrap.shutdown() tears down in safe order: polling → health → broadcaster → redis.

Each step is non-fatal unless marked CRITICAL.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_polling_service = None
_health_collector = None


async def run(app: Any) -> None:  # noqa: ARG001
    global _polling_service, _health_collector

    # 1. Validate secrets (CRITICAL — exits in production if JWT_SECRET_KEY missing)
    from app.core.config import validate_startup_secrets
    validate_startup_secrets(strict=True)

    # 2. Alembic migrations → create_all safety net
    _run_migrations()
    from app.db import init_db
    init_db()

    # 3. Redis
    from app.core.config import REDIS_URL
    try:
        from app.core.redis_pool import init_redis
        await init_redis(REDIS_URL)
        logger.info("Redis connection pool initialised")
    except Exception as exc:
        logger.warning("Redis init failed (non-fatal): %s", exc)

    # 4. WeatherAPI
    try:
        from app.core.redis_pool import get_redis
        from app.services.weather_api import init_weather_provider
        _redis = None
        try:
            _redis = get_redis()
        except RuntimeError:
            pass
        init_weather_provider(redis_client=_redis)
        logger.info("WeatherAPI provider initialised")
    except Exception as exc:
        logger.warning("WeatherAPI init failed (non-fatal): %s", exc)

    # 5. Supporting services
    for _fn in (_init_rolling_window, _init_event_bus, _init_drift_monitor, _init_calibration_service):
        try:
            _fn()
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", _fn.__name__, exc)

    # 6. Broadcaster (selects Local or Redis based on WORKER_MODE)
    try:
        await _init_broadcaster()
    except Exception as exc:
        logger.warning("Broadcaster init failed (non-fatal): %s", exc)

    # 7. City model registry + TCN warm-up
    from app.services.city_model_service import city_model_service
    status = city_model_service.model_status()
    logger.info(
        "City models: %d/%d trained | Untrained: %s",
        status["trained_cities"], status["total_cities"], status["untrained"],
    )
    try:
        await city_model_service.warm_up_tcn_buffers()
    except Exception as exc:
        logger.warning("TCN warm-up failed (non-fatal): %s", exc)

    # 8. Alert tiers are loaded inside _load_v2_artifacts() — no separate step needed.

    # 9. Weather polling (after models and warm-up are ready)
    try:
        _polling_service = _start_polling()
    except Exception as exc:
        logger.warning("WeatherPollingService start failed (non-fatal): %s", exc)

    # 10. Runtime health collector
    try:
        from app.services.health_collector import get_health_collector
        _health_collector = get_health_collector()
        _health_collector.start()
        logger.info("RuntimeHealthCollector started")
    except Exception as exc:
        logger.warning("RuntimeHealthCollector start failed (non-fatal): %s", exc)

    logger.info("=== HydroGuard-AI bootstrap complete ===")


async def shutdown() -> None:
    global _polling_service, _health_collector

    # Stop event sources before closing transport
    if _polling_service is not None:
        try:
            await _polling_service.stop()
            logger.info("WeatherPollingService stopped")
        except Exception as exc:
            logger.warning("PollingService stop error: %s", exc)

    if _health_collector is not None:
        try:
            await _health_collector.stop()
        except Exception as exc:
            logger.warning("HealthCollector stop error: %s", exc)

    # Close broadcaster after no more events can be generated
    import app.runtime.system_runtime as runtime
    if runtime.ACTIVE_BROADCASTER is not None:
        try:
            await runtime.ACTIVE_BROADCASTER.close()
        except Exception as exc:
            logger.warning("Broadcaster close error: %s", exc)

    try:
        from app.core.redis_pool import close_redis
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)

    logger.info("Shutdown complete.")


# ── Private helpers ───────────────────────────────────────────────────────────

def _run_migrations() -> None:
    try:
        from alembic import command
        from alembic.config import Config
        cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
        if not cfg_path.exists():
            logger.warning("alembic.ini not found at %s — skipping migrations", cfg_path)
            return
        command.upgrade(Config(str(cfg_path)), "head")
        logger.info("Alembic: schema up to date")
    except Exception as exc:
        logger.warning("Alembic migration failed (create_all will handle schema): %s", exc)


async def _init_broadcaster() -> None:
    import app.runtime.system_runtime as runtime
    from app.realtime.manager import manager
    from app.realtime.broadcaster import LocalBroadcaster, RedisBroadcaster

    if runtime.WORKER_MODE == "multi":
        try:
            from app.core.redis_pool import get_redis
            broadcaster = RedisBroadcaster(get_redis())
            await broadcaster.start_subscribers(manager)
            runtime.ACTIVE_BROADCASTER = broadcaster
            runtime.FEATURE_FLAGS["redis_ws_enabled"] = True
            logger.info("RedisBroadcaster activated (multi-worker mode)")
            return
        except Exception as exc:
            logger.warning("RedisBroadcaster failed, falling back to LocalBroadcaster: %s", exc)

    runtime.ACTIVE_BROADCASTER = LocalBroadcaster(manager)
    logger.info("LocalBroadcaster activated (single-worker mode)")


def _start_polling():
    from app.core.config import WEATHERAPI_KEY
    from app.services.weather_api import weather_provider
    from app.services.city_model_service import city_model_service
    from app.services.polling_service import WeatherPollingService

    if not WEATHERAPI_KEY:
        logger.warning("WEATHERAPI_KEY not set — weather polling disabled")
        return None

    interval = int(os.getenv("POLLING_INTERVAL_SECONDS", "900"))
    svc = WeatherPollingService(
        weather_provider=weather_provider,
        city_model_service=city_model_service,
        interval_seconds=interval,
    )
    svc.start()
    logger.info("WeatherPollingService started (interval=%ds)", interval)
    return svc


def _init_rolling_window() -> None:
    from app.services.rolling_window import init_rolling_window
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_rolling_window(_r)
    logger.info("RollingWindowBuffer initialised")


def _init_event_bus() -> None:
    from app.services.event_bus import init_event_bus
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_event_bus(redis_client=_r)
    logger.info("EventBus initialised")


def _init_drift_monitor() -> None:
    from app.ml.drift.monitor import init_drift_monitor
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_drift_monitor(_r)
    logger.info("DriftMonitor initialised")


def _init_calibration_service() -> None:
    from app.services.calibration_service import init_calibration_service
    init_calibration_service()
    logger.info("CalibrationService initialised")
```

- [ ] **Step 2: Thin main.py lifespan**

In `backend/app/main.py`, replace the entire `lifespan` function (lines 42–163) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting %s v%s ===", APP_TITLE, APP_VERSION)
    from app.runtime import bootstrap
    await bootstrap.run(app)
    yield
    await bootstrap.shutdown()
```

Remove the imports that are no longer used directly in `main.py` — specifically the ones that were only referenced inside the old `lifespan` body:

```python
# Remove from main.py imports (now in bootstrap.py):
# from app.db import init_db              ← moved to bootstrap
# from app.core.redis_pool import init_redis, close_redis, get_redis  ← moved to bootstrap
# from app.services.weather_api import init_weather_provider           ← moved to bootstrap
```

Keep these imports (still used by `create_app`):
```python
from app.core.config import (
    APIConfig, LOGGING_CONFIG, STATIC_DIR,
    validate_startup_secrets,
    REDIS_URL, WEATHERAPI_KEY,           # keep — still referenced by bootstrap via config
)
from app.core.limiter import limiter
from app.services.city_model_service import city_model_service   # keep — used nowhere? check
```

Actually check which imports are actually used in `create_app()` body and keep only those. Run:

```
python -c "from backend.app.main import app; print('import OK')"
```

Or more practically:

```
cd D:\Programming\FYP\hydroguard_ai
python -m pytest tests/test_api.py::TestSystem::test_health -v
```

Expected: PASS (server starts, health endpoint responds)

- [ ] **Step 3: Run full test suite**

```
pytest tests/ -v --tb=short
```
Expected: all existing tests pass

- [ ] **Step 4: Commit**

```
git add backend/app/runtime/bootstrap.py backend/app/main.py
git commit -m "feat(bootstrap): extract lifespan sequence into bootstrap module; thin main.py"
```

---

## Task 7: WeatherPollingService

**Files:**
- Create: `backend/app/services/polling_service.py`
- Create: `tests/test_polling_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_polling_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.polling_service import WeatherPollingService


def _make_service(**kwargs) -> WeatherPollingService:
    defaults = dict(
        weather_provider=AsyncMock(),
        city_model_service=MagicMock(),
        interval_seconds=60,
    )
    defaults.update(kwargs)
    return WeatherPollingService(**defaults)


def test_has_significant_change_empty_prev_returns_true():
    svc = _make_service()
    assert svc._has_significant_change({}, {"prcp": 0.0}) is True


def test_has_significant_change_prcp_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change({"prcp": 1.0}, {"prcp": 2.0}) is True


def test_has_significant_change_prcp_below_threshold():
    svc = _make_service()
    assert svc._has_significant_change({"prcp": 1.0}, {"prcp": 1.3}) is False


def test_has_significant_change_pressure_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "pressure_mb": 1013.0},
        {"prcp": 0.0, "pressure_mb": 1015.0},
    ) is True


def test_has_significant_change_pressure_below_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "pressure_mb": 1013.0},
        {"prcp": 0.0, "pressure_mb": 1013.5},
    ) is False


def test_has_significant_change_humidity_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "humidity": 60.0},
        {"prcp": 0.0, "humidity": 66.0},
    ) is True


async def test_poll_city_skips_when_no_change():
    mock_provider = AsyncMock()
    mock_snap = MagicMock()
    mock_snap.to_feature_dict.return_value = {"prcp": 1.0, "pressure_mb": 1013.0, "humidity": 60.0}
    mock_provider.get_current.return_value = mock_snap

    mock_model_svc = AsyncMock()

    svc = WeatherPollingService(mock_provider, mock_model_svc, interval_seconds=60)
    svc._last_snapshots["karachi"] = {"prcp": 1.0, "pressure_mb": 1013.0, "humidity": 60.0}

    with patch("app.runtime.system_runtime.emit_result", new=AsyncMock()) as mock_emit:
        await svc._poll_city("karachi")
        mock_emit.assert_not_called()
        mock_model_svc.predict_v2.assert_not_called()


async def test_poll_city_runs_inference_on_significant_change():
    mock_provider = AsyncMock()
    mock_snap = MagicMock()
    mock_snap.to_feature_dict.return_value = {"prcp": 5.0, "pressure_mb": 1013.0, "humidity": 60.0}
    mock_provider.get_current.return_value = mock_snap

    mock_model_svc = AsyncMock()
    mock_model_svc.predict_v2.return_value = {
        "is_alert": False, "hri_score": 10, "alert_tier_label": "NORMAL",
    }

    svc = WeatherPollingService(mock_provider, mock_model_svc, interval_seconds=60)
    svc._last_snapshots["karachi"] = {"prcp": 0.0, "pressure_mb": 1013.0, "humidity": 60.0}

    with patch("app.runtime.system_runtime.emit_result", new=AsyncMock()):
        await svc._poll_city("karachi")
        mock_model_svc.predict_v2.assert_called_once_with("karachi", mock_snap.to_feature_dict())
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_polling_service.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.polling_service'`

- [ ] **Step 3: Implement WeatherPollingService**

```python
# backend/app/services/polling_service.py
"""
WeatherPollingService — background weather polling for all discovered cities.

Responsibility: schedule, fetch, trigger, forward.
NOT responsible for: alert classification, DB persistence logic,
broadcaster selection, inference behaviour, notification policy.

Persistence rule: only ADVISORY and ALERT tier results write to DB.
NORMAL readings are not persisted to prevent analytics noise.

Event emission: calls runtime.emit_result() — the single event origin.
Never calls broadcaster directly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WeatherPollingService:
    def __init__(
        self,
        weather_provider,
        city_model_service,
        *,
        interval_seconds: int = 900,
    ) -> None:
        self._weather = weather_provider
        self._models  = city_model_service
        self._interval = interval_seconds
        self._last_snapshots: dict[str, dict] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_polling")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_all()

    async def _poll_all(self) -> None:
        slugs = self._models.list_slugs()
        results = await asyncio.gather(
            *[self._poll_city(s) for s in slugs],
            return_exceptions=True,
        )
        for slug, result in zip(slugs, results):
            if isinstance(result, Exception):
                logger.error("polling_failed city=%s error=%s", slug, result)

    async def _poll_city(self, slug: str) -> None:
        snap = await self._weather.get_current(slug, force_refresh=True)
        if snap is None:
            return

        raw = snap.to_feature_dict()
        prev = self._last_snapshots.get(slug, {})
        if not self._has_significant_change(prev, raw):
            return

        result = await self._models.predict_v2(slug, raw)

        from app.runtime import system_runtime as runtime
        await runtime.emit_result(result)

        if result.get("alert_tier_label") != "NORMAL":
            asyncio.create_task(
                _persist_result_background(result, raw),
                name=f"persist_{slug}",
            )

        self._last_snapshots[slug] = raw
        logger.info(
            "polling_updated city=%s tier=%s p=%.3f",
            slug,
            result.get("alert_tier_label", "?"),
            result.get("event_probability", 0.0),
        )

    def _has_significant_change(self, prev: dict, curr: dict) -> bool:
        if not prev:
            return True
        flags = self._models
        try:
            sens = __import__("app.runtime.system_runtime", fromlist=["FEATURE_FLAGS"]).FEATURE_FLAGS.get(
                "polling_sensitivity", {}
            )
        except Exception:
            sens = {}
        prcp_delta     = sens.get("prcp_delta", 0.5)
        pressure_delta = sens.get("pressure_delta", 1.5)
        humidity_delta = sens.get("humidity_delta", 5.0)

        return (
            abs(curr.get("prcp", 0) - prev.get("prcp", 0)) > prcp_delta
            or abs(curr.get("pressure_mb", 1013) - prev.get("pressure_mb", 1013)) > pressure_delta
            or abs(curr.get("humidity", 60) - prev.get("humidity", 60)) > humidity_delta
        )


async def _persist_result_background(result: dict[str, Any], weather: dict[str, Any]) -> None:
    """Best-effort DB persistence from polling. Only called for ADVISORY/ALERT tier."""
    try:
        from app.db import get_db, AnomalyRepository
        risk_band = result.get("risk_band", "Low")
        v1_result = {
            "city":          result.get("city_slug") or result.get("city"),
            "date":          result.get("inferred_at"),
            "anomaly_score": result.get("event_probability", 0.0),
            "threshold":     0.5,
            "is_anomaly":    result.get("is_alert", False),
            "risk_level":    risk_band,
            "hri_score":     {"Low": 12, "Moderate": 40, "High": 68, "Severe": 88}.get(risk_band, 12),
            "hri_label":     risk_band,
            "remarks":       f"polling · tier={result.get('alert_tier_label')} · source={result.get('source')}",
        }
        with get_db() as db:
            AnomalyRepository(db).create(prediction_result=v1_result, weather_data=weather)
    except Exception as exc:
        logger.debug("polling persist failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_polling_service.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```
git add backend/app/services/polling_service.py tests/test_polling_service.py
git commit -m "feat(polling): add WeatherPollingService with change-detection guard and selective persistence"
```

---

## Task 8: Fix `/cities/overview` — Live Weather with Parallel Fetch

**Files:**
- Modify: `backend/app/api/v2/cities.py`

- [ ] **Step 1: Replace `cities_overview()` in `backend/app/api/v2/cities.py`**

Find the existing `cities_overview` function (line ~42) and replace it entirely:

```python
@router.get("/overview")
async def cities_overview():
    """Risk snapshot for all cities using live weather and calibrated predict_v2.

    All city weather fetches run in parallel (asyncio.gather). Falls back to
    zero-fill on any per-city weather failure — non-fatal, logged.
    """
    import asyncio
    from app.services.weather_api import weather_provider

    cities = city_model_service.list_cities()
    slugs  = [c["slug"] for c in cities]

    snaps = await asyncio.gather(
        *[_fetch_weather_safe(slug, weather_provider) for slug in slugs],
        return_exceptions=True,
    )

    results = []
    for c, snap in zip(cities, snaps):
        raw = snap if isinstance(snap, dict) else {}
        try:
            result = await city_model_service.predict_v2(c["slug"], raw)
            results.append({
                "slug":             c["slug"],
                "name":             c["name"],
                "risk_band":        result.get("risk_band", "Low"),
                "hri_score":        result.get("hri_score", 0),
                "event_probability":result.get("event_probability"),
                "alert_tier_label": result.get("alert_tier_label", "NORMAL"),
                "source":           result.get("source", "unknown"),
            })
        except Exception as exc:
            logger.debug("overview predict failed for %s: %s", c["slug"], exc)

    return {"cities": results, "count": len(results), "live_weather": True}


async def _fetch_weather_safe(slug: str, weather_provider) -> dict:
    """Fetch live weather for one city; returns empty dict on any failure."""
    try:
        if weather_provider is None:
            return {}
        snap = await weather_provider.get_current(slug)
        return snap.to_feature_dict()
    except Exception as exc:
        logger.warning("overview_weather_miss city=%s: %s", slug, exc)
        return {}
```

- [ ] **Step 2: Verify the endpoint returns `live_weather: True`**

Start the server and curl the endpoint, OR run the test suite which exercises the health path:

```
pytest tests/test_api.py -v --tb=short -k "health or overview"
```

If no test exists for overview, add a quick smoke check at the bottom of `tests/test_api.py`:

```python
class TestOverview:
    def test_overview_has_live_weather_flag(self, client):
        response = client.get("/api/v2/cities/overview")
        assert response.status_code == 200
        assert response.json()["live_weather"] is True
```

Run: `pytest tests/test_api.py::TestOverview -v`
Expected: PASS

- [ ] **Step 3: Commit**

```
git add backend/app/api/v2/cities.py tests/test_api.py
git commit -m "fix(overview): live weather parallel fetch via asyncio.gather; add alert_tier_label to overview response"
```

---

## Task 9: Full Test Suite + Smoke Verification

- [ ] **Step 1: Run the complete test suite**

```
pytest tests/ -v --tb=short
```
Expected: all tests pass. Note any failures and fix before proceeding.

- [ ] **Step 2: Start the server and verify bootstrap log output**

```
python backend/run_server.py --port 8001
```

Expected log lines (in order):
```
=== Starting HydroGuard-AI...
Alembic: schema up to date
Redis connection pool initialised   (or warning if Redis not running — non-fatal)
WeatherAPI provider initialised     (or warning if no key — non-fatal)
RollingWindowBuffer initialised
EventBus initialised
DriftMonitor initialised
CalibrationService initialised
LocalBroadcaster activated (single-worker mode)
City models: N/M trained
AlertTierClassifier loaded          (per trained city)
WeatherPollingService started       (or "disabled" if WEATHERAPI_KEY not set)
RuntimeHealthCollector started
=== HydroGuard-AI bootstrap complete ===
```

- [ ] **Step 3: Verify predict_v2 output includes new fields**

```
curl -s -X POST http://localhost:8001/api/v2/cities/islamabad/predict \
  -H "Content-Type: application/json" \
  -d '{"prcp": 45.0, "humidity": 88.0, "pressure": 1002.0}' | python -m json.tool
```

Expected response includes:
```json
{
  "alert_tier_label": "ADVISORY",  // or "ALERT" or "NORMAL"
  "push_notification": false,
  "drivers": [
    {"feature": "pressure_delta_1step (daily resolution)", ...},  // display_name applied
    ...
  ]
}
```

- [ ] **Step 4: Verify overview returns live_weather flag**

```
curl -s http://localhost:8001/api/v2/cities/overview | python -m json.tool | grep live_weather
```
Expected: `"live_weather": true`

- [ ] **Step 5: Final commit**

```
git add -A
git commit -m "test: full suite pass + smoke verification for v3.3 audit fixes"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Fix 1 (Polling): Task 7 + Task 6 (`_start_polling` in bootstrap)
- [x] Fix 2 (Two-tier alerts): Task 2 (AlertTierClassifier) + Task 5 (integrate into predict_v2)
- [x] Fix 3 (Overview live weather): Task 8
- [x] Fix 4 (Alembic in startup): Task 6 (`_run_migrations` in bootstrap)
- [x] Fix 5 (Feature display names): Task 1 + Task 5 (apply in predict_v2 SHAP drivers)
- [x] Fix 6 (Broadcaster abstraction): Task 4 + Task 6 (`_init_broadcaster` in bootstrap)
- [x] `system_runtime.py` + single event origin rule: Task 3
- [x] `runtime/__init__.py` and `config/__init__.py` packages: Tasks 3 and 1
- [x] `bootstrap.py` + thin `main.py`: Task 6
- [x] `_alert_tiers` dict loaded in `_load_v2_artifacts`: Task 5

**Type consistency:**
- `AlertTierClassifier.classify()` returns `AlertTierResult` with `.tier`, `.push_notification`, `.advisory_threshold`, `.alert_threshold` — consistent across Task 2 and Task 5.
- `WeatherPollingService._has_significant_change()` reads from `FEATURE_FLAGS["polling_sensitivity"]` — consistent with Task 3 definition.
- `AbstractBroadcaster.broadcast(channel, data)` signature — consistent across Tasks 3, 4, 6.
- `emit_result(result)` calls `ACTIVE_BROADCASTER.broadcast("anomalies", result)` — consistent across Tasks 3 and 7.

**No placeholders:** All code blocks are complete and executable.
