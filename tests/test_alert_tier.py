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
