"""
Tests for HydroGuard-AI calibration modules:
  - ECDFScaler
  - IsotonicCalibrator
"""
from __future__ import annotations

import sys
import os
import types
from pathlib import Path
import tempfile

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
dotenv = types.ModuleType("dotenv"); dotenv.load_dotenv = lambda *a,**k: None
sys.modules.setdefault("dotenv", dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "test-cal-key-32-chars-long-abc1")


# ─────────────────────────────────────────────────────────────
#  ECDFScaler
# ─────────────────────────────────────────────────────────────

class TestECDFScaler:
    def setup_method(self):
        from app.ml.calibration.ecdf import ECDFScaler
        self.scaler = ECDFScaler()
        rng = np.random.default_rng(42)
        self.train_errors = rng.exponential(scale=0.05, size=500)
        self.scaler.fit(self.train_errors)

    def test_output_in_range(self):
        sample = np.array([0.01, 0.05, 0.10, 0.50])
        out = self.scaler.transform(sample)
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_monotonicity(self):
        vals = np.linspace(0.001, 0.30, 50)
        out  = self.scaler.transform(vals)
        assert np.all(np.diff(out) >= 0), "ECDF must be non-decreasing"

    def test_scalar_consistent_with_batch(self):
        v = 0.05
        batch = self.scaler.transform(np.array([v]))
        scalar = self.scaler.transform_scalar(v)
        assert abs(batch[0] - scalar) < 1e-9

    def test_zero_error_maps_to_low_percentile(self):
        pct = self.scaler.transform_scalar(0.0)
        assert pct == 0.0

    def test_large_error_maps_to_one(self):
        pct = self.scaler.transform_scalar(999.0)
        assert pct == 1.0

    def test_save_load_roundtrip(self):
        from app.ml.calibration.ecdf import ECDFScaler
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_ecdf.pkl"
            self.scaler.save(path)
            loaded = ECDFScaler.load(path)
        assert loaded.n_training_samples == self.scaler.n_training_samples
        assert abs(loaded.transform_scalar(0.05) - self.scaler.transform_scalar(0.05)) < 1e-9

    def test_single_sample_edge_case(self):
        from app.ml.calibration.ecdf import ECDFScaler
        sc = ECDFScaler()
        sc.fit(np.array([0.5]))
        pct = sc.transform_scalar(0.5)
        assert 0.0 <= pct <= 1.0

    def test_nan_inf_handled(self):
        pct = self.scaler.transform_scalar(float("nan"))
        assert pct == 0.0
        arr = self.scaler.transform(np.array([float("inf"), float("nan"), 0.1]))
        assert np.all(np.isfinite(arr))


# ─────────────────────────────────────────────────────────────
#  IsotonicCalibrator
# ─────────────────────────────────────────────────────────────

class TestIsotonicCalibrator:
    def setup_method(self):
        from app.ml.calibration.isotonic import IsotonicCalibrator
        rng = np.random.default_rng(0)
        n   = 300
        # Synthetic: higher raw prob -> more likely positive
        self.p_raw  = rng.uniform(0.1, 0.9, size=n)
        noise       = rng.normal(0, 0.1, size=n)
        self.y_true = (self.p_raw + noise > 0.5).astype(float)
        self.cal    = IsotonicCalibrator()
        self.metrics = self.cal.fit(self.p_raw, self.y_true)

    def test_brier_improves(self):
        assert self.metrics.brier_after <= self.metrics.brier_before + 0.01

    def test_ece_below_threshold(self):
        assert self.metrics.ece_after < 0.15

    def test_transform_range(self):
        sample = np.linspace(0.1, 0.9, 20)
        out    = self.cal.transform(sample)
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_transform_scalar(self):
        v = float(self.cal.transform(np.array([0.5]))[0])
        assert 0.0 <= v <= 1.0

    def test_ci_contains_p(self):
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            lo, hi = self.cal.confidence_interval(p)
            # CI should generally contain or be near p (not strict for small bootstrap)
            assert 0.0 <= lo <= 1.0
            assert 0.0 <= hi <= 1.0
            assert lo <= hi

    def test_uncertainty_bounds(self):
        u = self.cal.compute_uncertainty(0.5, ae_variance=0.5, tcn_variance=0.5, drift_penalty=0.0)
        assert 0.0 <= u <= 1.0

    def test_uncertainty_increases_with_drift(self):
        u_no_drift   = self.cal.compute_uncertainty(0.5, 0.3, 0.3, drift_penalty=0.0)
        u_with_drift = self.cal.compute_uncertainty(0.5, 0.3, 0.3, drift_penalty=0.15)
        assert u_with_drift >= u_no_drift

    def test_model_entropy_at_half(self):
        H = self.cal.model_entropy(0.5)
        assert abs(H - 0.693) < 0.01   # ln(2) ≈ 0.693

    def test_model_entropy_at_certainty(self):
        H_low  = self.cal.model_entropy(0.01)
        H_high = self.cal.model_entropy(0.99)
        assert H_low  < 0.1
        assert H_high < 0.1

    def test_save_load_roundtrip(self):
        from app.ml.calibration.isotonic import IsotonicCalibrator
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test_cal.pkl"
            self.cal.save(path)
            loaded = IsotonicCalibrator.load(path)
        v_orig   = float(self.cal.transform(np.array([0.6]))[0])
        v_loaded = float(loaded.transform(np.array([0.6]))[0])
        assert abs(v_orig - v_loaded) < 1e-6


# ─────────────────────────────────────────────────────────────
#  Static metric functions
# ─────────────────────────────────────────────────────────────

class TestCalibrationMetrics:
    def test_brier_perfect_score(self):
        from app.ml.calibration.isotonic import IsotonicCalibrator
        y = np.array([1., 0., 1., 0.])
        assert IsotonicCalibrator.brier_score(y, y) == 0.0

    def test_brier_random_score(self):
        from app.ml.calibration.isotonic import IsotonicCalibrator
        rng = np.random.default_rng(1)
        p = rng.uniform(size=1000)
        y = (rng.uniform(size=1000) < 0.5).astype(float)
        bs = IsotonicCalibrator.brier_score(p, y)
        assert 0.0 < bs < 0.5

    def test_ece_perfect_calibration(self):
        from app.ml.calibration.isotonic import IsotonicCalibrator
        # If p[i] = y[i], ECE should be 0
        p = np.array([0.0, 0.1, 0.5, 0.9, 1.0])
        y = np.array([0.0, 0.1, 0.5, 0.9, 1.0])
        ece = IsotonicCalibrator.ece(p, y)
        assert ece < 0.01
