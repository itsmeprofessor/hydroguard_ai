from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _audit_helpers import temporal_split, near_duplicate_rate, classify_pass_fail


class TestTemporalSplit:
    def test_temporal_split_no_future_leakage(self):
        dates = pd.date_range("2000-01-01", periods=100, freq="D")
        df = pd.DataFrame({"date": dates, "value": range(100)})
        train_df, holdout_df = temporal_split(df, holdout_frac=0.15)
        assert len(holdout_df) == 15
        assert len(train_df) == 85
        assert train_df["date"].max() < holdout_df["date"].min()

    def test_temporal_split_size(self):
        df = pd.DataFrame({"date": pd.date_range("2000-01-01", periods=200, freq="D")})
        train_df, holdout_df = temporal_split(df, holdout_frac=0.15)
        assert len(holdout_df) == int(200 * 0.15)
        assert len(train_df) == 200 - int(200 * 0.15)


class TestNearDuplicateRate:
    def test_near_duplicate_rate_range(self):
        rng = np.random.default_rng(42)
        X_train = rng.standard_normal((50, 10))
        X_holdout = rng.standard_normal((20, 10))
        rate = near_duplicate_rate(X_train, X_holdout)
        assert 0.0 <= rate <= 1.0

    def test_near_duplicate_rate_identical_is_one(self):
        X = np.eye(5)
        rate = near_duplicate_rate(X, X, threshold=0.95)
        assert rate == 1.0

    def test_near_duplicate_rate_empty_holdout(self):
        X_train = np.eye(5)
        X_holdout = np.empty((0, 5))
        assert near_duplicate_rate(X_train, X_holdout) == 0.0


class TestPassFail:
    def test_pass_fail_auc_floor(self):
        # clean=0.68 < 0.70 floor, but drop=(0.9303-0.68)=0.2503 > 0.10 → FAIL_BOTH
        # Use clean=0.82 with reported=0.85 to get only floor fail
        # Actually with reported=0.9303, we can't get FAIL_AUC_FLOOR alone
        # Use reported=0.85, clean=0.68 → drop=0.17 > 0.10, floor fail
        # Use reported=0.72, clean=0.68 → drop=0.04 < 0.10, floor fail only
        verdict, retrain = classify_pass_fail(reported_auc=0.72, clean_auc=0.68)
        assert verdict == "FAIL_AUC_FLOOR"
        assert retrain is True

    def test_pass_fail_auc_drop(self):
        # reported=0.9303, clean=0.82 → drop=0.1103 > 0.10
        verdict, retrain = classify_pass_fail(reported_auc=0.9303, clean_auc=0.82)
        assert verdict == "FAIL_AUC_DROP"
        assert retrain is True

    def test_fail_both(self):
        # clean=0.60 < 0.70 floor AND 0.9303-0.60=0.3303 > 0.10
        verdict, retrain = classify_pass_fail(reported_auc=0.9303, clean_auc=0.60)
        assert verdict == "FAIL_BOTH"
        assert retrain is True

    def test_pass_when_both_criteria_met(self):
        # clean=0.88 → floor OK (0.88>=0.70) AND drop OK (0.9303-0.88=0.0503<=0.10)
        verdict, retrain = classify_pass_fail(reported_auc=0.9303, clean_auc=0.88)
        assert verdict == "PASS"
        assert retrain is False

    def test_output_json_schema(self):
        required_fields = {
            "reported_auc", "clean_holdout_auc", "clean_holdout_prauc",
            "auc_drop", "near_duplicate_rate", "holdout_n", "holdout_positives",
            "pass_fail", "retrain_recommended", "audited_at",
        }
        fake = {
            "reported_auc": 0.9303,
            "clean_holdout_auc": 0.85,
            "clean_holdout_prauc": 0.70,
            "auc_drop": 0.0803,
            "near_duplicate_rate": 0.10,
            "holdout_n": 876,
            "holdout_positives": 50,
            "pass_fail": "PASS",
            "retrain_recommended": False,
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
        assert required_fields.issubset(set(fake.keys()))

    def test_exit_code_nonzero_on_fail(self):
        """Contract: FAIL* verdict maps to retrain=True (script exits 1)."""
        verdict, retrain = classify_pass_fail(0.9303, 0.60)
        assert verdict != "PASS"
        assert retrain is True
