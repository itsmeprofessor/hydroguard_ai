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
