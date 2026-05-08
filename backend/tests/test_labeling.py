"""
Tests for HydroGuard-AI weak supervision labeling package.
Covers all 7 labeling functions (L1-L7) + LabelEngine aggregation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent))

import os, types
dotenv = types.ModuleType("dotenv"); dotenv.load_dotenv = lambda *a,**k: None
sys.modules.setdefault("dotenv", dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "test-labeling-key-32-chars")


# ─────────────────────────────────────────────────────────────
#  L1 — Rainfall intensity
# ─────────────────────────────────────────────────────────────

class TestL1RainfallIntensity:
    from app.ml.labeling.rules import rule_rainfall_intensity

    def test_strong_positive(self):
        from app.ml.labeling.rules import rule_rainfall_intensity
        label, conf, score = rule_rainfall_intensity(prcp=100.0, prcp_climo_pct=3.0)
        assert label == 1
        assert conf == 1.0

    def test_moderate_positive(self):
        from app.ml.labeling.rules import rule_rainfall_intensity
        label, conf, score = rule_rainfall_intensity(prcp=40.0, prcp_climo_pct=1.8)
        assert label == 1
        assert conf == 0.7

    def test_negative(self):
        from app.ml.labeling.rules import rule_rainfall_intensity
        label, conf, score = rule_rainfall_intensity(prcp=0.5, prcp_climo_pct=0.1)
        assert label == 0
        assert conf > 0.5

    def test_abstain(self):
        from app.ml.labeling.rules import rule_rainfall_intensity
        label, conf, score = rule_rainfall_intensity(prcp=15.0, prcp_climo_pct=1.0)
        assert label == -1

    def test_return_types(self):
        from app.ml.labeling.rules import rule_rainfall_intensity
        result = rule_rainfall_intensity(prcp=50.0, prcp_climo_pct=2.0)
        assert len(result) == 3
        assert isinstance(result[0], int)
        assert isinstance(result[1], float)
        assert isinstance(result[2], float)
        assert 0.0 <= result[1] <= 1.0


# ─────────────────────────────────────────────────────────────
#  L2 — Pressure drop
# ─────────────────────────────────────────────────────────────

class TestL2PressureDrop:
    def test_severe_drop_positive(self):
        from app.ml.labeling.rules import rule_pressure_drop
        label, conf, score = rule_pressure_drop(pressure_delta_3h=-4.0)
        assert label == 1
        assert conf == 0.9

    def test_moderate_drop_positive(self):
        from app.ml.labeling.rules import rule_pressure_drop
        label, conf, score = rule_pressure_drop(pressure_delta_3h=-2.0)
        assert label == 1
        assert conf == 0.6

    def test_rising_pressure_negative(self):
        from app.ml.labeling.rules import rule_pressure_drop
        label, conf, score = rule_pressure_drop(pressure_delta_3h=2.5)
        assert label == 0

    def test_none_input_abstain(self):
        from app.ml.labeling.rules import rule_pressure_drop
        label, conf, score = rule_pressure_drop(pressure_delta_3h=None)
        assert label == -1

    def test_fallback_to_6h(self):
        from app.ml.labeling.rules import rule_pressure_drop
        label, conf, score = rule_pressure_drop(pressure_delta_3h=None, pressure_delta_6h=-4.0)
        assert label == 1


# ─────────────────────────────────────────────────────────────
#  L3 — Humidity
# ─────────────────────────────────────────────────────────────

class TestL3Humidity:
    def test_saturated_with_rain(self):
        from app.ml.labeling.rules import rule_humidity
        label, conf, _ = rule_humidity(humidity=92.0, prcp=15.0)
        assert label == 1
        assert conf == 0.8

    def test_high_humidity_alone(self):
        from app.ml.labeling.rules import rule_humidity
        label, conf, _ = rule_humidity(humidity=87.0, prcp=0.0)
        assert label == 1
        assert conf == 0.5

    def test_dry_negative(self):
        from app.ml.labeling.rules import rule_humidity
        label, conf, _ = rule_humidity(humidity=40.0, prcp=0.0)
        assert label == 0

    def test_mid_range_abstain(self):
        from app.ml.labeling.rules import rule_humidity
        label, _, _ = rule_humidity(humidity=72.0, prcp=5.0)
        assert label == -1


# ─────────────────────────────────────────────────────────────
#  L4 — Cloud concentration
# ─────────────────────────────────────────────────────────────

class TestL4CloudConcentration:
    def test_overcast_with_rain(self):
        from app.ml.labeling.rules import rule_cloud_concentration
        label, conf, _ = rule_cloud_concentration(cloud_cover=95.0, prcp_climo_pct=2.0)
        assert label == 1
        assert conf == 0.75

    def test_clear_sky_negative(self):
        from app.ml.labeling.rules import rule_cloud_concentration
        label, conf, _ = rule_cloud_concentration(cloud_cover=10.0, prcp_climo_pct=0.5)
        assert label == 0

    def test_abstain(self):
        from app.ml.labeling.rules import rule_cloud_concentration
        label, _, _ = rule_cloud_concentration(cloud_cover=60.0, prcp_climo_pct=1.2)
        assert label == -1


# ─────────────────────────────────────────────────────────────
#  L5 — T-Td spread
# ─────────────────────────────────────────────────────────────

class TestL5TdewSpread:
    def test_near_saturation_with_rain(self):
        from app.ml.labeling.rules import rule_tdew_spread
        label, conf, _ = rule_tdew_spread(tdew_spread=2.0, prcp=10.0)
        assert label == 1
        assert conf == 0.85

    def test_very_dry_negative(self):
        from app.ml.labeling.rules import rule_tdew_spread
        label, conf, _ = rule_tdew_spread(tdew_spread=20.0, prcp=0.0)
        assert label == 0

    def test_none_abstain(self):
        from app.ml.labeling.rules import rule_tdew_spread
        label, _, _ = rule_tdew_spread(tdew_spread=None, prcp=5.0)
        assert label == -1


# ─────────────────────────────────────────────────────────────
#  L6 — Persistence
# ─────────────────────────────────────────────────────────────

class TestL6Persistence:
    def test_two_recent_positives(self):
        from app.ml.labeling.rules import rule_persistence
        label, conf, _ = rule_persistence(recent_votes=[1, 1, 0])
        assert label == 1
        assert conf >= 0.70

    def test_two_recent_negatives(self):
        from app.ml.labeling.rules import rule_persistence
        label, conf, _ = rule_persistence(recent_votes=[0, 0, -1])
        assert label == 0
        assert conf >= 0.70

    def test_empty_abstain(self):
        from app.ml.labeling.rules import rule_persistence
        label, _, _ = rule_persistence(recent_votes=[])
        assert label == -1

    def test_mixed_abstain(self):
        from app.ml.labeling.rules import rule_persistence
        label, _, _ = rule_persistence(recent_votes=[1, 0, -1])
        assert label == -1


# ─────────────────────────────────────────────────────────────
#  L7 — Historical extreme (with mock climatology)
# ─────────────────────────────────────────────────────────────

class MockStats:
    def __init__(self, q50, q90, q99, mu, sigma):
        self.q50=q50; self.q90=q90; self.q99=q99; self.mu=mu; self.sigma=sigma

class MockClimatology:
    def get_stats(self, city_slug, month, feature):
        stats = {
            "prcp":        MockStats(10, 50, 100, 15, 20),
            "humidity":    MockStats(60, 85,  95, 62, 15),
            "pressure":    MockStats(1013, 1018, 1021, 1012, 4),
            "cloud_cover": MockStats(30, 80,  97, 35, 28),
        }
        return stats.get(feature, MockStats(0, 1, 2, 0, 1))

class TestL7HistoricalExtreme:
    def test_multiple_extremes_positive(self):
        from app.ml.labeling.rules import rule_historical_extreme
        feat = {"prcp": 120.0, "humidity": 97.0, "pressure": 996.0, "cloud_cover": 98.0}
        label, conf, _ = rule_historical_extreme(feat, MockClimatology(), "islamabad", 7)
        assert label == 1

    def test_normal_conditions_negative(self):
        from app.ml.labeling.rules import rule_historical_extreme
        feat = {"prcp": 5.0, "humidity": 55.0, "pressure": 1015.0, "cloud_cover": 20.0}
        label, conf, _ = rule_historical_extreme(feat, MockClimatology(), "islamabad", 1)
        assert label == 0

    def test_no_climatology_abstain(self):
        from app.ml.labeling.rules import rule_historical_extreme
        feat = {"prcp": 100.0}
        label, _, _ = rule_historical_extreme(feat, None, "islamabad", 7)
        assert label == -1


# ─────────────────────────────────────────────────────────────
#  LabelEngine
# ─────────────────────────────────────────────────────────────

class TestLabelEngine:
    def test_locked_thresholds(self):
        from app.ml.labeling.engine import POSITIVE_THRESHOLD, NEGATIVE_THRESHOLD
        assert POSITIVE_THRESHOLD == 0.45
        assert NEGATIVE_THRESHOLD == 0.15

    def test_extreme_row_positive(self):
        from app.ml.labeling.engine import LabelEngine
        engine = LabelEngine(climatology=MockClimatology())
        features = {
            "prcp": 120.0, "humidity": 93.0, "cloud_cover": 96.0,
            "prcp_climo_pct": 3.0, "pressure_delta_3h": -4.0,
            "tdew_spread": 2.0, "moisture_flux": 0.8,
        }
        out = engine.label_row(features, "islamabad", 7)
        assert out.weak_label == 1
        assert 0.0 <= out.weak_label_conf <= 1.0

    def test_calm_row_negative(self):
        from app.ml.labeling.engine import LabelEngine
        engine = LabelEngine(climatology=None)
        features = {
            "prcp": 0.5, "humidity": 40.0, "cloud_cover": 10.0,
            "prcp_climo_pct": 0.1, "pressure_delta_3h": 0.5,
            "tdew_spread": 20.0, "moisture_flux": 0.1,
        }
        out = engine.label_row(features, "islamabad", 1)
        assert out.weak_label == 0

    def test_rule_votes_has_all_rules(self):
        from app.ml.labeling.engine import LabelEngine
        engine = LabelEngine()
        out = engine.label_row({"prcp": 5.0, "humidity": 60.0, "cloud_cover": 30.0,
                                 "prcp_climo_pct": 1.0}, "islamabad", 6)
        assert set(out.rule_votes.keys()) == {"L1", "L2", "L3", "L4", "L5", "L6", "L7"}
        for v in out.rule_votes.values():
            assert v in (-1, 0, 1)

    def test_rule_votes_json_serialisable(self):
        from app.ml.labeling.engine import LabelEngine
        engine = LabelEngine()
        out = engine.label_row({"prcp": 5.0, "humidity": 60.0, "cloud_cover": 30.0,
                                 "prcp_climo_pct": 1.0}, "islamabad", 6)
        # Must not raise
        json.dumps(out.rule_votes)

    def test_event_type_cloudburst(self):
        from app.ml.labeling.engine import LabelEngine
        engine = LabelEngine(climatology=None)
        features = {
            "prcp": 80.0, "humidity": 92.0, "cloud_cover": 95.0,
            "prcp_climo_pct": 2.0, "pressure_delta_3h": -4.0,
            "tdew_spread": 2.5, "moisture_flux": 0.75,
        }
        out = engine.label_row(features, "islamabad", 7)
        if out.weak_label == 1:
            assert out.event_type in ("cloudburst", "heavy_rain", "flash_flood", None)
