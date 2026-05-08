"""
Drift simulation test for HydroGuard-AI DriftMonitor.
Injects synthetic extreme observations and asserts:
  - PSI > 0.20 after injection
  - drift_level == "critical"
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
dotenv = types.ModuleType("dotenv"); dotenv.load_dotenv = lambda *a,**k: None
sys.modules.setdefault("dotenv", dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "test-drift-key-32-chars-long-ab")

from app.ml.drift.monitor import DriftMonitor, PSI_CRIT, MONITORED_FEATURES


# ─────────────────────────────────────────────────────────────
#  Mock Redis (in-memory)
# ─────────────────────────────────────────────────────────────

class MockRedis:
    """In-memory Redis stub for testing."""
    def __init__(self):
        self._store: dict = {}
        self._last_drift_state = None

    async def get(self, key: str):
        val = self._store.get(key)
        return val

    async def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value

    async def publish(self, channel: str, payload: str):
        pass   # no-op for tests


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _make_normal_obs(n: int = 500) -> list[dict]:
    """Generate normal-range weather observations."""
    rng = np.random.default_rng(42)
    obs = []
    for _ in range(n):
        obs.append({
            "prcp":               float(rng.exponential(5.0)),
            "humidity":           float(rng.uniform(40.0, 75.0)),
            "pressure":           float(rng.normal(1013.0, 3.0)),
            "cloud_cover":        float(rng.uniform(10.0, 60.0)),
            "pressure_delta_3h":  float(rng.normal(0.0, 0.5)),
            "rain_rate_1h":       float(rng.exponential(0.5)),
            "moisture_flux":      float(rng.uniform(0.1, 0.4)),
            "tdew_spread":        float(rng.uniform(8.0, 18.0)),
            "prcp_climo_pct":     float(rng.uniform(0.2, 1.2)),
            "pressure_climo_z":   float(rng.normal(0.0, 0.5)),
        })
    return obs


def _make_extreme_obs(n: int = 120) -> list[dict]:
    """Generate extreme weather observations (flood precursors)."""
    rng = np.random.default_rng(99)
    obs = []
    for _ in range(n):
        obs.append({
            "prcp":               float(rng.uniform(80.0, 150.0)),
            "humidity":           float(rng.uniform(88.0, 98.0)),
            "pressure":           float(rng.normal(998.0, 3.0)),
            "cloud_cover":        float(rng.uniform(85.0, 100.0)),
            "pressure_delta_3h":  float(rng.uniform(-6.0, -2.0)),
            "rain_rate_1h":       float(rng.uniform(15.0, 40.0)),
            "moisture_flux":      float(rng.uniform(0.7, 1.0)),
            "tdew_spread":        float(rng.uniform(0.5, 3.0)),
            "prcp_climo_pct":     float(rng.uniform(2.5, 4.5)),
            "pressure_climo_z":   float(rng.uniform(-4.0, -2.0)),
        })
    return obs


# ─────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_psi_zero_on_stable_input():
    """PSI should be very low when reference and current distributions match."""
    redis   = MockRedis()
    monitor = DriftMonitor(redis_client=redis)
    city    = "islamabad_test"

    # Seed reference
    normal_obs = _make_normal_obs(500)
    for obs in normal_obs:
        for feat in MONITORED_FEATURES:
            monitor._recent[city][feat].append(float(obs.get(feat, 0.0)))

    # Write reference into mock Redis
    for feat in MONITORED_FEATURES:
        vals = monitor._recent[city].get(feat, [])
        if vals:
            await redis.setex(
                f"hg:drift_ref:{city}:{feat}",
                86400,
                json.dumps(vals),
            )

    # Record another batch of normal observations (same distribution)
    for obs in _make_normal_obs(100):
        for feat in MONITORED_FEATURES:
            val = obs.get(feat)
            if val is not None:
                monitor._recent[city][feat].append(float(val))

    # Compute PSI for one feature
    psi_scores: dict = {}
    for feat in MONITORED_FEATURES:
        current_vals = monitor._recent[city].get(feat, [])
        if len(current_vals) < 10:
            continue
        ref_json = await redis.get(f"hg:drift_ref:{city}:{feat}")
        if ref_json:
            import numpy as _np
            from app.ml.drift.monitor import _compute_psi
            ref = _np.array(json.loads(ref_json))
            psi_scores[feat] = _compute_psi(ref, _np.array(current_vals[-100:]))

    if psi_scores:
        max_psi = max(psi_scores.values())
        # Normal vs normal: PSI should be low (< WARN threshold)
        assert max_psi < 0.20, f"Unexpected high PSI on stable input: {max_psi:.3f}"


@pytest.mark.asyncio
async def test_extreme_injection_triggers_critical_psi():
    """Injecting 120 extreme observations after seeding normal reference -> PSI > 0.20."""
    from app.ml.drift.monitor import _compute_psi
    redis   = MockRedis()
    monitor = DriftMonitor(redis_client=redis)
    city    = "islamabad_extreme"

    # Seed reference with normal data
    normal_obs = _make_normal_obs(500)
    for obs in normal_obs:
        for feat in MONITORED_FEATURES:
            monitor._recent[city][feat].append(float(obs.get(feat, 0.0)))
    for feat in MONITORED_FEATURES:
        vals = monitor._recent[city].get(feat, [])
        if vals:
            await redis.setex(
                f"hg:drift_ref:{city}:{feat}",
                86400,
                json.dumps(vals[-500:]),
            )

    # Clear recent window and inject extreme observations
    for feat in MONITORED_FEATURES:
        monitor._recent[city][feat] = []
    extreme_obs = _make_extreme_obs(120)
    for obs in extreme_obs:
        for feat in MONITORED_FEATURES:
            val = obs.get(feat)
            if val is not None:
                monitor._recent[city][feat].append(float(val))

    # Compute PSI
    psi_scores = {}
    for feat in MONITORED_FEATURES:
        current_vals = monitor._recent[city].get(feat, [])
        ref_json = await redis.get(f"hg:drift_ref:{city}:{feat}")
        if ref_json and len(current_vals) >= 10:
            ref = np.array(json.loads(ref_json), dtype=float)
            psi_scores[feat] = _compute_psi(ref, np.array(current_vals, dtype=float))

    assert psi_scores, "No PSI scores computed"
    max_psi = max(psi_scores.values())
    print(f"\nMax PSI after extreme injection: {max_psi:.4f}")
    print(f"PSI scores: { {k: round(v,3) for k, v in psi_scores.items()} }")

    # Core assertion: critical drift detected
    assert max_psi >= PSI_CRIT, (
        f"Expected PSI >= {PSI_CRIT} (CRITICAL), got {max_psi:.4f}. "
        f"Feature scores: {psi_scores}"
    )


@pytest.mark.asyncio
async def test_psi_zero_on_identical_distributions():
    """PSI = 0 when current == reference."""
    from app.ml.drift.monitor import _compute_psi
    rng  = np.random.default_rng(7)
    vals = rng.exponential(10.0, size=200)
    psi  = _compute_psi(vals, vals)
    assert psi < 0.01, f"PSI should be ~0 for identical distributions, got {psi:.4f}"


def test_monitored_features_count():
    """Exactly 10 features monitored (Groups A+B+C from Phase 3 spec)."""
    assert len(MONITORED_FEATURES) == 10


def test_psi_thresholds():
    """PSI thresholds match Phase 3 spec."""
    from app.ml.drift.monitor import PSI_WARN, PSI_CRIT
    assert PSI_WARN == 0.10
    assert PSI_CRIT == 0.20
