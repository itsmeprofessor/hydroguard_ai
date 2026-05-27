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
    # Well-separated scores: positives clearly high, negatives clearly low
    y_score = np.where(
        y_true == 1,
        rng.uniform(0.80, 0.99, n),
        rng.uniform(0.01, 0.18, n),
    )
    cal_path = tmp_path / "cal_data.npz"
    np.savez(cal_path, y_true=y_true, y_score=y_score)

    clf = AlertTierClassifier.from_cal_data(cal_path)
    assert clf.advisory_threshold < clf.alert_threshold
    assert 0.0 < clf.advisory_threshold < 1.0
    assert 0.0 < clf.alert_threshold < 1.0
    # Must derive non-default values — this is the happy path
    assert clf.advisory_threshold != DEFAULT_ADVISORY_THRESHOLD
    assert clf.alert_threshold != DEFAULT_ALERT_THRESHOLD


def test_from_cal_data_falls_back_on_missing_file(tmp_path):
    clf = AlertTierClassifier.from_cal_data(tmp_path / "nonexistent.npz")
    assert clf.advisory_threshold == DEFAULT_ADVISORY_THRESHOLD
    assert clf.alert_threshold == DEFAULT_ALERT_THRESHOLD


def test_from_cal_data_falls_back_on_inversion(tmp_path):
    # All scores are exactly 0.70 with 10% positive rate.
    # Only one threshold in the PR curve (0.70); precision ≈ 0.10 < 0.65 → alert_mask never fires
    # → alert defaults to DEFAULT_ALERT_THRESHOLD=0.65.
    # advisory_mask fires at threshold=0.70 → advisory_min=0.70 > 0.65=alert → inversion → defaults.
    n = 100
    y_true = np.zeros(n, dtype=int)
    y_true[:10] = 1  # 10% positive rate — precision = 0.10 at the one threshold, never ≥ 0.65
    y_score = np.full(n, 0.70)  # single score value → single threshold; advisory_min=0.70 > 0.65
    cal_path = tmp_path / "cal_data.npz"
    np.savez(cal_path, y_true=y_true, y_score=y_score)

    clf = AlertTierClassifier.from_cal_data(cal_path)
    assert clf.advisory_threshold == DEFAULT_ADVISORY_THRESHOLD
    assert clf.alert_threshold == DEFAULT_ALERT_THRESHOLD


def test_init_rejects_inverted_thresholds():
    with pytest.raises(ValueError, match="must be less than"):
        AlertTierClassifier(advisory_threshold=0.70, alert_threshold=0.30)
