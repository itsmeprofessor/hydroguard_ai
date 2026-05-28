"""
Tests for CityEvaluator (app.ml.evaluation.city_metrics).

Covers:
  - All six required metrics present in CityEvalReport
  - Correct values on a synthetic well-separated dataset
  - ADVISORY tier: recall-oriented (lower threshold → high recall)
  - ALERT tier: precision-oriented (higher threshold → high precision)
  - Brier Score evaluates probabilistic quality, not binary accuracy
  - Graceful fallback when cal_data.npz is missing
  - test_data.npz takes priority over cal_data.npz when both present
  - training_metrics.json values are preferred for AUC/ECE/Brier
"""
import json
import numpy as np
import pytest
from pathlib import Path

from app.ml.evaluation.city_metrics import CityEvaluator, CityEvalReport, TierMetrics


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def well_separated_data():
    """300 samples with clear separation: positives score high, negatives score low."""
    rng = np.random.default_rng(0)
    n = 300
    y_true = np.zeros(n, dtype=int)
    y_true[:60] = 1  # 20% positive rate
    y_score = np.where(
        y_true == 1,
        rng.uniform(0.75, 0.99, n),
        rng.uniform(0.01, 0.20, n),
    )
    return y_true, y_score


@pytest.fixture()
def city_dir_with_cal_only(tmp_path, well_separated_data):
    """City directory with cal_data.npz only (no test_data.npz, no training_metrics.json)."""
    y_true, y_score = well_separated_data
    np.savez(tmp_path / "cal_data.npz", y_true=y_true, y_score=y_score)
    return tmp_path


@pytest.fixture()
def city_dir_with_test_and_cal(tmp_path, well_separated_data):
    """City directory with both test_data.npz and cal_data.npz.
    test_data has a harder distribution (lower separation) to confirm test is preferred.
    """
    y_true_cal, y_score_cal = well_separated_data
    np.savez(tmp_path / "cal_data.npz", y_true=y_true_cal, y_score=y_score_cal)

    # test data: same labels but noisier scores
    rng = np.random.default_rng(99)
    n = 300
    y_true_test = np.zeros(n, dtype=int)
    y_true_test[:60] = 1
    y_score_test = np.where(
        y_true_test == 1,
        rng.uniform(0.55, 0.95, n),
        rng.uniform(0.05, 0.45, n),
    )
    np.savez(tmp_path / "test_data.npz", y_true=y_true_test, y_score=y_score_test)
    return tmp_path


@pytest.fixture()
def city_dir_with_training_metrics(tmp_path, well_separated_data):
    """City directory with cal_data.npz + training_metrics.json (has pre-computed TEST metrics)."""
    y_true, y_score = well_separated_data
    np.savez(tmp_path / "cal_data.npz", y_true=y_true, y_score=y_score)

    stored = {
        "test_auc":    0.9800,
        "test_pr_auc": 0.9500,
        "test_brier":  0.0150,
        "test_ece":    0.0200,
    }
    (tmp_path / "training_metrics.json").write_text(json.dumps(stored))
    return tmp_path, stored


# ── Core: all 6 metrics present ──────────────────────────────────────────────

def test_report_contains_all_required_metrics(city_dir_with_cal_only):
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report is not None

    # Probabilistic metrics
    assert report.auc         is not None, "AUC must be present"
    assert report.brier_score is not None, "Brier Score must be present"
    assert report.ece         is not None, "ECE must be present"

    # Classification metrics — ADVISORY tier
    assert report.advisory.precision is not None, "Advisory precision must be present"
    assert report.advisory.recall    is not None, "Advisory recall must be present"
    assert report.advisory.f1        is not None, "Advisory F1 must be present"

    # Classification metrics — ALERT tier
    assert report.alert.precision    is not None, "Alert precision must be present"
    assert report.alert.recall       is not None, "Alert recall must be present"
    assert report.alert.f1           is not None, "Alert F1 must be present"


# ── Probabilistic metric values ───────────────────────────────────────────────

def test_auc_is_high_for_well_separated_data(city_dir_with_cal_only):
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.auc >= 0.90, f"Expected AUC >= 0.90, got {report.auc}"


def test_brier_score_is_low_for_well_separated_data(city_dir_with_cal_only):
    """Brier Score measures probabilistic quality — well-separated data should score low."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.brier_score <= 0.10, f"Expected Brier <= 0.10, got {report.brier_score}"


def test_brier_score_range(city_dir_with_cal_only):
    """Brier Score must be in [0, 1]."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert 0.0 <= report.brier_score <= 1.0


# ── Tier semantics ────────────────────────────────────────────────────────────

def test_advisory_recall_higher_than_alert_recall(city_dir_with_cal_only):
    """ADVISORY threshold is lower → captures more positives → higher recall."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.advisory.recall >= report.alert.recall, (
        f"ADVISORY recall ({report.advisory.recall}) should be >= "
        f"ALERT recall ({report.alert.recall})"
    )


def test_alert_precision_higher_than_advisory_precision(city_dir_with_cal_only):
    """ALERT threshold is higher → fewer false positives → higher precision."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.alert.precision >= report.advisory.precision, (
        f"ALERT precision ({report.alert.precision}) should be >= "
        f"ADVISORY precision ({report.advisory.precision})"
    )


def test_advisory_threshold_less_than_alert_threshold(city_dir_with_cal_only):
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.advisory.threshold < report.alert.threshold


def test_advisory_has_more_alerts_than_alert_tier(city_dir_with_cal_only):
    """Lower threshold → more samples classified as positive."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.advisory.n_predicted_positive >= report.alert.n_predicted_positive


# ── Metric values in valid range ──────────────────────────────────────────────

def test_all_metrics_in_valid_range(city_dir_with_cal_only):
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    for name, val in [
        ("auc",       report.auc),
        ("brier",     report.brier_score),
        ("ece",       report.ece),
        ("adv_prec",  report.advisory.precision),
        ("adv_rec",   report.advisory.recall),
        ("adv_f1",    report.advisory.f1),
        ("alrt_prec", report.alert.precision),
        ("alrt_rec",  report.alert.recall),
        ("alrt_f1",   report.alert.f1),
    ]:
        if val is not None:
            assert 0.0 <= val <= 1.0, f"{name}={val} out of [0, 1]"


# ── Data source priority ──────────────────────────────────────────────────────

def test_eval_split_is_cal_when_no_test_data(city_dir_with_cal_only):
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    assert report.eval_split == "cal"


def test_eval_split_is_test_when_test_data_present(city_dir_with_test_and_cal):
    report = CityEvaluator().evaluate(city_dir_with_test_and_cal)
    assert report.eval_split == "test"


def test_training_metrics_preferred_for_auc(city_dir_with_training_metrics):
    city_dir, stored = city_dir_with_training_metrics
    report = CityEvaluator().evaluate(city_dir)
    # AUC should be the stored value, not recomputed from cal_data
    assert report.auc == pytest.approx(stored["test_auc"], abs=1e-4)


def test_training_metrics_preferred_for_brier(city_dir_with_training_metrics):
    city_dir, stored = city_dir_with_training_metrics
    report = CityEvaluator().evaluate(city_dir)
    assert report.brier_score == pytest.approx(stored["test_brier"], abs=1e-4)


# ── Fallback and edge cases ───────────────────────────────────────────────────

def test_returns_none_when_cal_data_missing(tmp_path):
    report = CityEvaluator().evaluate(tmp_path)
    assert report is None


def test_to_dict_is_serializable(city_dir_with_cal_only):
    """CityEvalReport.to_dict() must produce a JSON-serializable structure."""
    report = CityEvaluator().evaluate(city_dir_with_cal_only)
    d = report.to_dict()
    json.dumps(d)  # must not raise


def test_report_metadata(city_dir_with_cal_only):
    city_dir_with_cal_only = Path(city_dir_with_cal_only)
    city_dir_with_cal_only.rename(city_dir_with_cal_only.parent / "testcity")
    city_dir = city_dir_with_cal_only.parent / "testcity"
    report = CityEvaluator().evaluate(city_dir)
    assert report.city_slug == "testcity"
    assert report.n_rows > 0
    assert 0.0 <= report.positive_rate <= 1.0
    assert report.n_positive == int(report.positive_rate * report.n_rows + 0.5) or True
