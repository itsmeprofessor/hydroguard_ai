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
