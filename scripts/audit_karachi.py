"""
HydroGuard-AI — Karachi Model Integrity Audit
==============================================
Evaluates the existing Karachi model on a strict temporal holdout (last 15%
of Karachi rows by date) to detect AUC inflation from near-duplicate
contamination.

Exit code 0 = PASS, exit code 1 = any FAIL variant.

Usage:
    python scripts/audit_karachi.py
    python scripts/audit_karachi.py --data backend/data/pakistan_weather_2000_2024.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import types as _t
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── Path bootstrap ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND   = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND))

_dotenv = _t.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "audit-script-key")

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _audit_helpers import temporal_split, near_duplicate_rate, classify_pass_fail

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("audit_karachi")

DEFAULT_DATA = REPO_ROOT / "backend" / "data" / "pakistan_weather_2000_2024.csv"
KARACHI_DIR  = REPO_ROOT / "backend" / "saved_models" / "city_models" / "karachi"
REPORTED_AUC = 0.9303
HOLDOUT_FRAC = 0.15
KARACHI_VULN = 0.85


def _load_karachi_rows(data_path: Path) -> pd.DataFrame:
    df = pd.read_csv(data_path, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    city_col = next(
        (c for c in df.columns if c in ("city", "location", "city_slug")), None
    )
    if city_col is None:
        raise ValueError("No city column found in CSV")
    mask = df[city_col].str.strip().str.lower() == "karachi"
    df_k = df[mask].copy().reset_index(drop=True)
    if len(df_k) == 0:
        raise ValueError("No Karachi rows found in dataset")
    logger.info("Loaded %d Karachi rows from %s", len(df_k), data_path)
    return df_k


def _prepare_partition(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the same feature engineering as train_city.py per-split step.

    Note: is_monsoon_month and vulnerability are NOT added here because the
    saved preprocessor was fitted WITHOUT is_monsoon_month (it was added after
    fitting in train_city.py). They are added post-transform for labeling and
    fusion matrix building only.
    """
    from train_city import (
        _ensure_month, _ensure_derived, _compute_physics_features,
    )
    df = _ensure_month(df)
    df = _ensure_derived(df)
    df = _compute_physics_features(df)
    if "day" not in df.columns and "date" in df.columns:
        df["day"] = pd.to_datetime(df["date"], errors="coerce").dt.day.fillna(15).astype(int)
    return df


def _add_post_transform_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Add columns needed for labeling and fusion but NOT for preprocessor.transform()."""
    df = df.copy()
    df["is_monsoon_month"] = df["month"].isin({6, 7, 8, 9}).astype(float)
    df["vulnerability"]    = KARACHI_VULN
    return df


def _score_partition(
    model,
    X_arr: np.ndarray,
    context_seed: np.ndarray,
    seq_len: int,
) -> tuple:
    """Sequential scoring — mirrors _score_oof in train_city.py exactly."""
    ae_pcts, tcn_pcts, ae_vars, tcn_vars = [], [], [], []
    ctx = list(context_seed[-seq_len:]) if len(context_seed) >= seq_len else list(context_seed)
    for x_vec in X_arr:
        seq = np.array(ctx[-seq_len:]) if len(ctx) >= seq_len else None
        raw = model.predict(x_vec, seq)
        ae_pcts.append(raw["ae_percentile"])
        tcn_pcts.append(raw["tcn_percentile"])
        ae_vars.append(raw["ae_variance"])
        tcn_vars.append(raw["tcn_variance"])
        ctx.append(x_vec)
    return ae_pcts, tcn_pcts, ae_vars, tcn_vars


def _build_fusion_matrix(df_split: pd.DataFrame, ae_p, tcn_p, ae_v, tcn_v) -> np.ndarray:
    from app.ml.models.fusion import FUSION_FEATURES
    rows = df_split.to_dict("records")
    mat  = []
    for row, ap, tp, av, tv in zip(rows, ae_p, tcn_p, ae_v, tcn_v):
        d = {f: float(row.get(f, 0.0) or 0.0) for f in FUSION_FEATURES
             if f not in ("ae_percentile", "tcn_percentile", "ae_variance", "tcn_variance")}
        d.update({"ae_percentile": ap, "tcn_percentile": tp,
                  "ae_variance":   av, "tcn_variance":   tv})
        mat.append([d.get(f, 0.0) for f in FUSION_FEATURES])
    return np.array(mat, dtype=float)


def run_audit(data_path: Path) -> dict:
    from sklearn.metrics import roc_auc_score, average_precision_score
    import joblib
    from app.ml.models.city_hybrid import CityHybridModel
    from app.ml.models.fusion import FusionModel
    from app.ml.calibration.isotonic import IsotonicCalibrator
    from app.ml.models.tcn import TCN_SEQ_LEN
    from train_city import _label_partition

    df_k = _load_karachi_rows(data_path)
    df_train, df_holdout = temporal_split(df_k, holdout_frac=HOLDOUT_FRAC)
    logger.info("Split: train=%d  holdout=%d", len(df_train), len(df_holdout))

    df_train   = _prepare_partition(df_train)
    df_holdout = _prepare_partition(df_holdout)

    prep       = joblib.load(KARACHI_DIR / "preprocessor_v2.joblib")
    model      = CityHybridModel.load("karachi", KARACHI_DIR)
    fusion     = FusionModel.load(KARACHI_DIR / "lgbm_model.pkl")
    calibrator = IsotonicCalibrator.load(KARACHI_DIR / "calibrator.pkl")

    X_train,   _ = prep.transform(df_train)
    X_holdout, _ = prep.transform(df_holdout)

    # Add is_monsoon_month and vulnerability AFTER transform (not in preprocessor)
    df_train   = _add_post_transform_cols(df_train)
    df_holdout = _add_post_transform_cols(df_holdout)

    df_train_labeled = _label_partition(df_train, "karachi")
    _prcp_q95     = df_train["prcp"].quantile(0.95)
    _pressure_q15 = df_train["pressure"].quantile(0.15)
    _humidity_q85 = df_train["humidity"].quantile(0.85)
    _cloud_q80    = df_train["cloud_cover"].quantile(0.80)
    df_holdout_labeled = _label_partition(
        df_holdout, "karachi",
        _prcp_q95, _pressure_q15, _humidity_q85, _cloud_q80,
    )
    y_train   = df_train_labeled["weak_label"].values.astype(float)
    y_holdout = df_holdout_labeled["weak_label"].values.astype(float)

    ae_p, tcn_p, ae_v, tcn_v = _score_partition(model, X_holdout, X_train, TCN_SEQ_LEN)

    F_holdout  = _build_fusion_matrix(df_holdout_labeled, ae_p, tcn_p, ae_v, tcn_v)
    raw_scores = fusion.predict_proba(F_holdout)  # already returns (N,) P(event)
    cal_scores = calibrator.transform(raw_scores)

    holdout_positives = int(y_holdout.sum())
    if holdout_positives < 2:
        logger.warning("Only %d holdout positives — AUC unreliable", holdout_positives)
        clean_auc   = 0.5
        clean_prauc = 0.0
    else:
        clean_auc   = float(roc_auc_score(y_holdout, cal_scores))
        clean_prauc = float(average_precision_score(y_holdout, cal_scores))

    X_train_pos   = X_train[y_train == 1]
    X_holdout_pos = X_holdout[y_holdout == 1]
    dup_rate = near_duplicate_rate(X_train_pos, X_holdout_pos, threshold=0.95)
    logger.info("Near-duplicate rate: %.4f", dup_rate)

    auc_drop = REPORTED_AUC - clean_auc
    verdict, retrain = classify_pass_fail(REPORTED_AUC, clean_auc)

    return {
        "reported_auc":        round(REPORTED_AUC, 4),
        "clean_holdout_auc":   round(clean_auc, 4),
        "clean_holdout_prauc": round(clean_prauc, 4),
        "auc_drop":            round(auc_drop, 4),
        "near_duplicate_rate": round(dup_rate, 4),
        "holdout_n":           len(df_holdout),
        "holdout_positives":   holdout_positives,
        "pass_fail":           verdict,
        "retrain_recommended": retrain,
        "audited_at":          datetime.now(timezone.utc).isoformat(),
    }


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Karachi model integrity audit")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()

    result = run_audit(args.data)
    out_path = KARACHI_DIR / "integrity_audit.json"
    _write_atomic(out_path, result)

    print("\n=== Karachi Integrity Audit ===")
    for k, v in result.items():
        print(f"  {k:<25} {v}")
    print()

    if result["pass_fail"] == "PASS":
        print("PASS — reported AUC is consistent with clean temporal holdout")
        return 0
    else:
        print(f"FAIL: {result['pass_fail']} — retrain recommended: {result['retrain_recommended']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
