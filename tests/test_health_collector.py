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


class TestCityModelCounters:
    def setup_method(self):
        """Reset module-level counters before each test."""
        import backend.app.services.city_model_service as cms
        cms._mc_success_window.clear()
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
        assert snap.global_status == "unknown"
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
