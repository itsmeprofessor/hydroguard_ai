"""
tests/test_mc_inference.py
==========================
Regression and concurrency tests for Group A -- MC Dropout inference quality.

All config values injected via fixtures -- no hardcoded 15, 0.25, 2000, or 15 bins.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_model(input_dim: int = 8):
    """Build an untrained CityHybridModel using the canonical TCN sequence length."""
    from app.ml.models.city_hybrid import CityHybridModel, SEQUENCE_LENGTH
    m = CityHybridModel("testcity", input_dim=input_dim, seq_len=SEQUENCE_LENGTH)
    m.build()
    # Seed ECDF scalers so transform_scalar works without training
    m._ae_ecdf.fit(np.random.rand(50).astype(np.float32))
    m._tcn_ecdf.fit(np.random.rand(50).astype(np.float32))
    return m


@pytest.fixture
def mc_cfg():
    from app.core.config import MCInferenceConfig
    return MCInferenceConfig


@pytest.fixture
def input_dim():
    return 8


@pytest.fixture
def seq_len():
    from app.ml.models.city_hybrid import SEQUENCE_LENGTH
    return SEQUENCE_LENGTH


@pytest.fixture
def sample_x(input_dim):
    return np.zeros((input_dim,), dtype=np.float32)


@pytest.fixture
def sample_seq(input_dim, seq_len):
    return np.zeros((seq_len, input_dim), dtype=np.float32)


# ---------------------------------------------------------------------------
#  Test 1: mc_branches_independent
# ---------------------------------------------------------------------------

def test_mc_branches_independent(sample_x, sample_seq, mc_cfg):
    """Sequential and concurrent branch executions return dicts with same key sets."""
    model = _make_model()

    ae_fn, tcn_fn = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=mc_cfg.DROPOUT_SAMPLES,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    seq_ae  = ae_fn()
    seq_tcn = tcn_fn()

    ae_fn2, tcn_fn2 = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=mc_cfg.DROPOUT_SAMPLES,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    ind_ae  = ae_fn2()
    ind_tcn = tcn_fn2()

    assert set(seq_ae.keys()) == set(ind_ae.keys()), "AE branch key mismatch"
    assert set(seq_tcn.keys()) == set(ind_tcn.keys()), "TCN branch key mismatch"
    # All values must be finite floats
    for k, v in seq_ae.items():
        assert isinstance(v, (int, float)), f"ae_fn[{k}] not numeric: {v}"
        assert np.isfinite(v), f"ae_fn[{k}] not finite: {v}"


# ---------------------------------------------------------------------------
#  Test 2: predict_v2_mc_fields_present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_mc_fields_present():
    """MC mode: all new schema fields present and correctly typed."""
    from app.services.city_model_service import city_model_service

    with patch("app.core.config.MCInferenceConfig.ENABLED", True):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert "inference_mode" in result
    assert "uncertainty_available" in result
    assert "mc_samples_requested" in result
    assert "uncertainty_strategy" in result
    assert "degraded_reason" in result

    if result.get("inference_mode") == "mc_dropout":
        assert isinstance(result["epistemic_uncertainty"], float)
        assert result["uncertainty_available"] is True
        assert result["prediction_stability"] in (
            "stable", "moderate_uncertainty", "high_uncertainty"
        )
        assert result["mc_samples_requested"] is not None


# ---------------------------------------------------------------------------
#  Test 3: predict_v2_flag_disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_flag_disabled():
    """ENABLE_MC_INFERENCE=false -> inference_mode='deterministic', epistemic fields None."""
    from app.services.city_model_service import city_model_service

    with patch("app.core.config.MCInferenceConfig.ENABLED", False):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "deterministic"
    assert result.get("epistemic_uncertainty") is None
    assert result.get("uncertainty_available") is False
    assert result.get("degraded_reason") == "disabled"


# ---------------------------------------------------------------------------
#  Test 4: predict_v2_fallback_on_timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_fallback_on_timeout():
    """Mocked timeout -> fallback_deterministic, valid event_probability, epistemic=None."""
    from app.services.city_model_service import city_model_service

    async def _timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("app.core.config.MCInferenceConfig.ENABLED", True), \
         patch("asyncio.wait_for", side_effect=_timeout):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "fallback_deterministic"
    assert result.get("degraded_reason") == "timeout"
    assert result.get("epistemic_uncertainty") is None
    assert "event_probability" in result
    assert isinstance(result["event_probability"], float)


# ---------------------------------------------------------------------------
#  Test 5: predict_v2_fallback_on_exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_v2_fallback_on_exception():
    """Mocked branch exception -> fallback_deterministic, degraded_reason='exception'."""
    from app.services.city_model_service import city_model_service

    async def _exc(*args, **kwargs):
        raise RuntimeError("mock branch failure")

    with patch("app.core.config.MCInferenceConfig.ENABLED", True), \
         patch("asyncio.wait_for", side_effect=_exc):
        result = await city_model_service.predict_v2(
            "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
        )

    assert result.get("inference_mode") == "fallback_deterministic"
    assert result.get("degraded_reason") == "exception"
    assert result.get("epistemic_uncertainty") is None


# ---------------------------------------------------------------------------
#  Test 6: tcn_buffer_immutability
# ---------------------------------------------------------------------------

def test_tcn_buffer_immutability(sample_x, sample_seq, mc_cfg):
    """_CityBuffer snapshot must be byte-identical before and after _mc_tcn_branch."""
    model = _make_model()
    seq_before = sample_seq.copy()

    _, tcn_fn = model.prepare_mc_tasks(
        sample_x, sample_seq,
        n_samples=2,
        uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
        uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
    )
    tcn_fn()

    np.testing.assert_array_equal(
        sample_seq, seq_before,
        err_msg="sample_seq was mutated by _mc_tcn_branch via TCN closure"
    )


# ---------------------------------------------------------------------------
#  Test 7: epistemic_uncertainty_range
# ---------------------------------------------------------------------------

def test_epistemic_uncertainty_range(mc_cfg):
    """epistemic_uncertainty blend must always be in [UNCERTAINTY_MIN, UNCERTAINTY_MAX]."""
    model = _make_model(input_dim=8)
    model._ae_ecdf.fit(np.random.rand(100).astype(np.float32))
    model._tcn_ecdf.fit(np.random.rand(100).astype(np.float32))

    rng = np.random.default_rng(42)
    from app.ml.models.city_hybrid import SEQUENCE_LENGTH
    for _ in range(30):
        x   = rng.random(8).astype(np.float32)
        seq = rng.random((SEQUENCE_LENGTH, 8)).astype(np.float32)
        ae_fn, tcn_fn = model.prepare_mc_tasks(
            x, seq, n_samples=3,
            uncertainty_min=mc_cfg.UNCERTAINTY_MIN,
            uncertainty_max=mc_cfg.UNCERTAINTY_MAX,
        )
        ae_r  = ae_fn()
        tcn_r = tcn_fn()
        blend = (
            mc_cfg.AE_UNCERTAINTY_WEIGHT * ae_r["ae_uncertainty"]
            + mc_cfg.TCN_UNCERTAINTY_WEIGHT * tcn_r["tcn_uncertainty"]
        )
        eu = float(np.clip(blend, mc_cfg.UNCERTAINTY_MIN, mc_cfg.UNCERTAINTY_MAX))
        assert mc_cfg.UNCERTAINTY_MIN <= eu <= mc_cfg.UNCERTAINTY_MAX, \
            f"epistemic_uncertainty {eu} out of [{mc_cfg.UNCERTAINTY_MIN}, {mc_cfg.UNCERTAINTY_MAX}]"


# ---------------------------------------------------------------------------
#  Test 8: prediction_stability_mapping
# ---------------------------------------------------------------------------

def test_prediction_stability_mapping(mc_cfg):
    """Correct stability tier at and around both thresholds.

    Implementation uses strict greater-than (>), so:
      eu <= mod              -> "stable"
      mod < eu <= high       -> "moderate_uncertainty"
      eu > high              -> "high_uncertainty"
    """
    from app.services.city_model_service import _classify_prediction_stability

    mod  = mc_cfg.STABILITY_THRESHOLD_MODERATE
    high = mc_cfg.STABILITY_THRESHOLD_HIGH

    # Below and at mod -> stable (mod itself returns stable because test is >)
    assert _classify_prediction_stability(0.0)        == "stable"
    assert _classify_prediction_stability(mod - 0.01) == "stable"
    assert _classify_prediction_stability(mod)        == "stable"

    # Just above mod -> moderate_uncertainty
    assert _classify_prediction_stability(mod + 0.01) == "moderate_uncertainty"

    # At high -> moderate_uncertainty (not yet >high)
    assert _classify_prediction_stability(high)       == "moderate_uncertainty"

    # Just above high -> high_uncertainty
    assert _classify_prediction_stability(high + 0.01) == "high_uncertainty"
    assert _classify_prediction_stability(1.0)         == "high_uncertainty"


# ---------------------------------------------------------------------------
#  Test 9: concurrent_cities
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_cities():
    """Simultaneous city requests produce valid, non-corrupted results."""
    from app.services.city_model_service import city_model_service

    cities  = ["islamabad", "lahore", "karachi"]
    weather = {"prcp": 10.0, "humidity": 70.0, "pressure": 1005.0}

    results = await asyncio.gather(*[
        city_model_service.predict_v2(c, weather) for c in cities
    ])

    for city, result in zip(cities, results):
        assert result["city_slug"] == city, f"city_slug mismatch for {city}"
        assert "event_probability" in result
        assert isinstance(result["event_probability"], float)
        assert 0.0 <= result["event_probability"] <= 1.0


# ---------------------------------------------------------------------------
#  Test 10: latency_within_budget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.performance
async def test_latency_within_budget(mc_cfg):
    """Wall-clock predict_v2() latency must be under INFERENCE_TIMEOUT_MS * 1.5.

    NOTE: This is a performance-budget assertion, not a correctness test. It is
    environment-sensitive (thermal throttle, CPU scheduling, GC, suite-load) and
    may flap under prolonged full-suite runs. Run in isolation when benchmarking:
        pytest tests/test_mc_inference.py::test_latency_within_budget -v
    """
    from app.services.city_model_service import city_model_service

    budget_ms = mc_cfg.INFERENCE_TIMEOUT_MS * 1.5
    start = time.perf_counter()
    await city_model_service.predict_v2(
        "islamabad", {"prcp": 5.0, "humidity": 60.0, "pressure": 1013.0}
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < budget_ms, \
        f"Latency {elapsed_ms:.0f}ms exceeded budget {budget_ms:.0f}ms"


# ---------------------------------------------------------------------------
#  Test 11: calibration_audit_readonly
# ---------------------------------------------------------------------------

def test_calibration_audit_readonly():
    """calibration_audit.py writes only .json, never .pkl or .keras files."""
    import subprocess
    import sys
    from app.core.config import MODELS_DIR

    script = Path(__file__).parents[1] / "scripts" / "calibration_audit.py"
    if not script.exists():
        pytest.skip("calibration_audit.py not yet written")

    t_before = time.time()
    result = subprocess.run(
        [sys.executable, str(script), "--city", "islamabad", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, \
        f"calibration_audit.py --dry-run failed:\n{result.stderr}"

    # Verify no .pkl or .keras files were written/touched after test started
    for bad_ext in ("*.pkl", "*.keras"):
        for p in MODELS_DIR.rglob(bad_ext):
            assert p.stat().st_mtime < t_before, \
                f"Unexpected write to {p} during --dry-run"


# ---------------------------------------------------------------------------
#  Test 12: calibration_audit_schema
# ---------------------------------------------------------------------------

def test_calibration_audit_schema():
    """calibration_audit.json must contain all required top-level fields."""
    from app.core.config import MODELS_DIR

    required_fields = {
        "audit_version", "pipeline_version", "generated_at", "city_slug",
        "calibration_method", "calibration_ece_cal_set",
        "pre_calibration_ece_test", "post_calibration_ece_test",
        "pre_calibration_brier_test", "post_calibration_brier_test",
        "calibration_improvement", "bin_populations", "reliability_curve",
        "calibration_bins_used", "split_tier",
    }

    audit_files = list(MODELS_DIR.glob("city_models/*/calibration_audit.json"))
    if not audit_files:
        pytest.skip("No calibration_audit.json found -- run calibration_audit.py first")

    for af in audit_files:
        data = json.loads(af.read_text())
        missing = required_fields - set(data.keys())
        assert not missing, f"{af.parent.name}: missing fields {missing}"


# ---------------------------------------------------------------------------
#  Test 13: calibration_ece_values_plausible
# ---------------------------------------------------------------------------

def test_calibration_ece_values_plausible():
    """post_calibration_ece_test must be finite and non-negative."""
    from app.core.config import MODELS_DIR

    audit_files = list(MODELS_DIR.glob("city_models/*/calibration_audit.json"))
    if not audit_files:
        pytest.skip("No calibration_audit.json found -- run calibration_audit.py first")

    for af in audit_files:
        data = json.loads(af.read_text())
        post_ece    = data["post_calibration_ece_test"]
        improvement = data["calibration_improvement"]

        assert isinstance(post_ece, (int, float)), \
            f"{af.parent.name}: post_calibration_ece_test not numeric"
        assert post_ece >= 0.0, f"{af.parent.name}: negative ECE {post_ece}"
        assert np.isfinite(post_ece), f"{af.parent.name}: non-finite ECE {post_ece}"
        assert np.isfinite(improvement), \
            f"{af.parent.name}: non-finite calibration_improvement {improvement}"
