"""
HydroGuard-AI — Calibration Audit Script
==========================================
Measures pre/post-calibration ECE and Brier score on a held-out test split
for each trained city model, writing results to calibration_audit.json.

Usage
-----
  python scripts/calibration_audit.py --all
  python scripts/calibration_audit.py --city islamabad
  python scripts/calibration_audit.py --city islamabad --dry-run

Read-only contract
------------------
- Writes ONLY  <city_dir>/calibration_audit.json
- Appends-only new fields to <city_dir>/training_metrics.json (never overwrites)
- NEVER touches .keras, .pkl model files, or any other artifact

Split-tier hierarchy (first applicable wins)
--------------------------------------------
Tier 1 — year_holdout  : holdout_strategy == "year_2023_plus" AND holdout_rows > 0
         Filter master CSV to date >= 2023-01-01 for this city slug.
Tier 2 — last_15pct    : sort city rows chronologically, take last 15 %.
Tier 3 — stored_test   : take test_n_rows rows from chronological tail.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND   = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND))

# Stub out dotenv / JWT secret so we can import app modules without a .env file
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "calibration-audit-key")

# ── Constants (must match train_city.py) ─────────────────────────────────────
HOLDOUT_YEAR_START = 2023
TEST_FRAC          = 0.10
TRAIN_FRAC         = 0.78
MIN_EVAL_ROWS      = 10
CITIES             = ["islamabad", "lahore", "karachi", "peshawar", "quetta", "gilgit"]
MODELS_DIR         = BACKEND / "saved_models" / "city_models"
DATA_CSV           = BACKEND / "data" / "pakistan_weather_2000_2024.csv"
AUDIT_VERSION      = "1.0"
PIPELINE_VERSION   = "v3.5"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("calibration_audit")


# ─────────────────────────────────────────────────────────────────────────────
# ECE / Brier helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> Tuple[float, List[int], List[dict]]:
    """
    Expected Calibration Error (uniform-width bins).

    Returns
    -------
    ece            : float
    bin_populations: list[int]  — count per bin
    reliability    : list[dict] — {"predicted": float, "actual": float|None}
    """
    bins       = np.linspace(0.0, 1.0, n_bins + 1)
    ece_accum  = 0.0
    populations: List[int]  = []
    reliability: List[dict] = []

    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if hi == 1.0:               # include right edge in last bin
            mask = (probs >= lo) & (probs <= hi)
        n = int(mask.sum())
        populations.append(n)
        if n == 0:
            reliability.append({"predicted": float((lo + hi) / 2), "actual": None})
        else:
            mean_pred   = float(probs[mask].mean())
            mean_actual = float(labels[mask].mean())
            ece_accum  += (n / len(probs)) * abs(mean_pred - mean_actual)
            reliability.append({"predicted": mean_pred, "actual": mean_actual})

    return float(ece_accum), populations, reliability


def _brier(probs: np.ndarray, labels: np.ndarray) -> float:
    return float(np.mean((probs - labels) ** 2))


# ─────────────────────────────────────────────────────────────────────────────
# Physics / label helpers (mirrors train_city.py)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_month(df: pd.DataFrame) -> pd.DataFrame:
    if "month" not in df.columns and "date" in df.columns:
        df = df.copy()
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.month
    return df


def _ensure_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "tavg" in df.columns and "dew_point" in df.columns and "tdew_spread" not in df.columns:
        df["tdew_spread"] = (df["tavg"] - df["dew_point"]).clip(lower=0.0)
    if "tmax" in df.columns and "tmin" in df.columns and "temp_range" not in df.columns:
        df["temp_range"] = df["tmax"] - df["tmin"]
    if "humidity" in df.columns and "wspd" in df.columns and "moisture_flux" not in df.columns:
        df["moisture_flux"] = (df["humidity"] / 100.0) * df["wspd"].clip(lower=0.0)
    for col, default in [("prcp_climo_pct", 1.0), ("humidity_climo_pct", 1.0)]:
        if col not in df.columns:
            df[col] = default
    return df


def _compute_physics_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    df["pressure_delta_3h"]    = df["pressure"].diff(1)
    df["pressure_delta_6h"]    = df["pressure"].diff(2)
    df["humidity_delta_3h"]    = df["humidity"].diff(1)
    df["rain_rate_1h"]         = df["prcp"].diff(1).clip(lower=0.0)
    df["rain_accumulation_3h"] = df["prcp"].rolling(3, min_periods=1).sum()
    df["rain_accumulation_6h"] = df["prcp"].rolling(6, min_periods=1).sum()
    df["cloud_jump_3h"]        = df["cloud_cover"].diff(1)
    for col in ["pressure_delta_3h", "pressure_delta_6h", "humidity_delta_3h",
                "rain_rate_1h", "cloud_jump_3h"]:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)
    return df


def _compute_ewi(g: pd.DataFrame) -> pd.Series:
    rain  = (g["prcp"].clip(0, 80) / 80.0).fillna(0.0)
    pdrop = (-g["pressure_delta_3h"].clip(-10, 0) / 10.0).fillna(0.0)
    hum   = ((g["humidity"].clip(50, 100) - 50) / 50.0).fillna(0.0)
    cld   = (g["cloud_cover"].clip(0, 100) / 100.0).fillna(0.0)
    ewi   = 0.35 * rain + 0.30 * pdrop + 0.20 * hum + 0.15 * cld
    if "is_monsoon_month" in g.columns:
        ewi[g["is_monsoon_month"] == 1] = (
            ewi[g["is_monsoon_month"] == 1] * 1.15
        ).clip(upper=1.0)
    return ewi


HISTORICAL_EVENTS: Dict[str, List[str]] = {
    "islamabad":  ["2010-07-29", "2014-09-05", "2020-08-27", "2022-08-25",
                   "2018-07-24", "2023-07-12"],
    "lahore":     ["2010-07-29", "2020-08-11", "2021-07-01", "2022-07-21",
                   "2015-07-24", "2023-07-10"],
    "karachi":    ["2010-08-01", "2018-06-29", "2020-08-27", "2022-07-11",
                   "2021-07-27", "2023-06-15"],
    "peshawar":   ["2010-07-29", "2022-08-26", "2020-08-28", "2021-07-29"],
    "quetta":     ["2015-05-04", "2020-08-28", "2022-08-09", "2021-08-01"],
    "gilgit":     ["2010-07-29", "2018-07-18", "2022-08-16", "2021-08-04", "2019-07-15"],
}
PRE_EVENT_WINDOW  = 2
POST_EVENT_WINDOW = 1


def _apply_historical_anchors(df: pd.DataFrame, slug: str) -> pd.DataFrame:
    events = HISTORICAL_EVENTS.get(slug, [])
    if not events or "date" not in df.columns:
        return df
    df = df.copy()
    if "weak_label" not in df.columns:
        df["weak_label"]      = 0
        df["weak_label_conf"] = 0.5
    dates = pd.to_datetime(df["date"], errors="coerce")
    for ev in events:
        try:
            edt = pd.Timestamp(ev)
        except Exception:
            continue
        pre  = (dates >= edt - pd.Timedelta(days=PRE_EVENT_WINDOW)) & (dates < edt)
        day  = dates.dt.date == edt.date()
        post = (dates > edt) & (dates <= edt + pd.Timedelta(days=POST_EVENT_WINDOW))
        df.loc[pre,  "weak_label"] = 1
        df.loc[pre,  "weak_label_conf"] = 1.0
        df.loc[day,  "weak_label"] = 1
        df.loc[day,  "weak_label_conf"] = 1.0
        df.loc[post, "weak_label"] = 1
        df.loc[post, "weak_label_conf"] = 0.8
    return df


def _label_partition(
    df: pd.DataFrame,
    slug: str,
    prcp_q95:     Optional[float] = None,
    pressure_q15: Optional[float] = None,
    humidity_q85: Optional[float] = None,
    cloud_q80:    Optional[float] = None,
) -> pd.DataFrame:
    df = df.copy()
    if prcp_q95 is None:
        prcp_q95     = df["prcp"].quantile(0.95)
        pressure_q15 = df["pressure"].quantile(0.15)
        humidity_q85 = df["humidity"].quantile(0.85)
        cloud_q80    = df["cloud_cover"].quantile(0.80)

    pct_pos = (
        (df["prcp"] > prcp_q95)
        | ((df["humidity"] > humidity_q85) & (df["cloud_cover"] > cloud_q80))
        | (df["pressure"] < pressure_q15)
    )
    df["weak_label"]      = pct_pos.astype(np.int8)
    df["weak_label_conf"] = np.where(pct_pos, 0.75, 0.65)

    ewi = _compute_ewi(df)
    df.loc[ewi >= 0.55, "weak_label"]      = 1
    df.loc[ewi >= 0.55, "weak_label_conf"] = ewi[ewi >= 0.55].clip(0.75, 0.95)
    df.loc[(ewi <= 0.20) & (df["weak_label"] == 1), "weak_label"] = 0
    df.loc[(ewi <= 0.20) & (df["weak_label"] != 1), "weak_label_conf"] = 0.80

    df = _apply_historical_anchors(df, slug)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# OOF scoring (mirrors train_city.py _score_oof)
# ─────────────────────────────────────────────────────────────────────────────

def _score_oof(
    model,
    X_arr: np.ndarray,
    context_seed: np.ndarray,
    seq_len: int,
) -> Tuple[List, List, List, List]:
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


def _safe_float(v) -> float:
    try:
        f = float(v)
        return f if not np.isnan(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fusion_matrix(
    df_split: pd.DataFrame,
    ae_p, tcn_p, ae_v, tcn_v,
    features: List[str],
) -> np.ndarray:
    rows = df_split.to_dict("records")
    mat  = []
    for row, ap, tp, av, tv in zip(rows, ae_p, tcn_p, ae_v, tcn_v):
        d = {f: _safe_float(row.get(f)) for f in features
             if f not in ("ae_percentile", "tcn_percentile", "ae_variance", "tcn_variance")}
        d.update({"ae_percentile": ap, "tcn_percentile": tp,
                  "ae_variance":   av, "tcn_variance":   tv})
        mat.append([d.get(f, 0.0) for f in features])
    return np.array(mat, dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# Split reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def _reconstruct_splits(
    df_city: pd.DataFrame,
    slug: str,
    metrics: dict,
) -> Tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray]:
    """
    Reproduce the exact 4-way chronological split from the training pipeline.

    Returns
    -------
    split_tier : "year_holdout" | "last_15pct" | "stored_test"
    df_train   : TRAIN partition (for context seed)
    df_cal     : CAL partition  (for context seed)
    df_test    : TEST/HOLDOUT partition to evaluate
    y_test     : weak labels for the eval partition
    """
    df_city = _ensure_month(df_city)
    df_city = _ensure_derived(df_city)
    df_city["date"] = pd.to_datetime(df_city["date"], errors="coerce")
    df_city = df_city.sort_values("date").reset_index(drop=True)

    holdout_strategy = metrics.get("holdout_strategy", "")
    holdout_rows     = int(metrics.get("holdout_rows", 0))

    # ── Tier 1: year holdout ──────────────────────────────────────────────────
    if holdout_strategy == "year_2023_plus" and holdout_rows > 0:
        hm         = df_city["date"].dt.year >= HOLDOUT_YEAR_START
        df_holdout = df_city[hm].copy().reset_index(drop=True)
        df_work    = df_city[~hm].copy().reset_index(drop=True)

        if len(df_holdout) >= MIN_EVAL_ROWS:
            # Rebuild TRAIN | CAL from work split (same fractions as training)
            n_work    = len(df_work)
            test_start = int(n_work * (1.0 - TEST_FRAC))
            df_nt      = df_work.iloc[:test_start].copy().reset_index(drop=True)
            n_nt       = len(df_nt)
            cal_start  = int(n_nt * TRAIN_FRAC)
            df_train   = df_nt.iloc[:cal_start].copy().reset_index(drop=True)
            df_cal     = df_nt.iloc[cal_start:].copy().reset_index(drop=True)

            df_train = _compute_physics_features(df_train)
            df_cal   = _compute_physics_features(df_cal)
            df_eval  = _compute_physics_features(df_holdout)

            # Labels: derive TRAIN thresholds then apply to holdout
            df_train = _label_partition(df_train, slug)
            _prcp_q95     = df_train["prcp"].quantile(0.95)
            _pressure_q15 = df_train["pressure"].quantile(0.15)
            _humidity_q85 = df_train["humidity"].quantile(0.85)
            _cloud_q80    = df_train["cloud_cover"].quantile(0.80)
            df_eval = _label_partition(df_eval, slug, _prcp_q95, _pressure_q15,
                                       _humidity_q85, _cloud_q80)
            y_eval  = df_eval["weak_label"].values.astype(float)
            return "year_holdout", df_train, df_cal, df_eval, y_eval

    # ── Tier 2: last 15 % ─────────────────────────────────────────────────────
    # Use non-holdout work set; take last 15 % as eval
    hm2     = df_city["date"].dt.year >= HOLDOUT_YEAR_START
    df_work = df_city[~hm2].copy().reset_index(drop=True)
    n_last15 = max(int(len(df_work) * 0.15), 0)

    if n_last15 >= MIN_EVAL_ROWS:
        df_eval  = df_work.iloc[-n_last15:].copy().reset_index(drop=True)
        df_prior = df_work.iloc[:-n_last15].copy().reset_index(drop=True)

        n_prior   = len(df_prior)
        cal_start = int(n_prior * TRAIN_FRAC)
        df_train  = df_prior.iloc[:cal_start].copy().reset_index(drop=True)
        df_cal    = df_prior.iloc[cal_start:].copy().reset_index(drop=True)

        df_train = _compute_physics_features(df_train)
        df_cal   = _compute_physics_features(df_cal)
        df_eval  = _compute_physics_features(df_eval)

        df_train = _label_partition(df_train, slug)
        _prcp_q95     = df_train["prcp"].quantile(0.95)
        _pressure_q15 = df_train["pressure"].quantile(0.15)
        _humidity_q85 = df_train["humidity"].quantile(0.85)
        _cloud_q80    = df_train["cloud_cover"].quantile(0.80)
        df_eval = _label_partition(df_eval, slug, _prcp_q95, _pressure_q15,
                                   _humidity_q85, _cloud_q80)
        y_eval  = df_eval["weak_label"].values.astype(float)
        return "last_15pct", df_train, df_cal, df_eval, y_eval

    # ── Tier 3: stored_test (tail rows from training_metrics.test_n_rows) ─────
    test_n = int(metrics.get("test_n_rows", 0))
    if test_n < MIN_EVAL_ROWS:
        raise ValueError(
            f"[{slug}] All 3 split tiers failed: "
            f"n_last15={n_last15}, test_n_rows={test_n}, holdout_rows={holdout_rows}"
        )

    df_all  = df_city.copy().reset_index(drop=True)
    df_eval  = df_all.iloc[-test_n:].copy().reset_index(drop=True)
    df_prior = df_all.iloc[:-test_n].copy().reset_index(drop=True)

    n_prior   = len(df_prior)
    cal_start = int(n_prior * TRAIN_FRAC)
    df_train  = df_prior.iloc[:cal_start].copy().reset_index(drop=True)
    df_cal    = df_prior.iloc[cal_start:].copy().reset_index(drop=True)

    df_train = _compute_physics_features(df_train)
    df_cal   = _compute_physics_features(df_cal)
    df_eval  = _compute_physics_features(df_eval)

    df_train = _label_partition(df_train, slug)
    _prcp_q95     = df_train["prcp"].quantile(0.95)
    _pressure_q15 = df_train["pressure"].quantile(0.15)
    _humidity_q85 = df_train["humidity"].quantile(0.85)
    _cloud_q80    = df_train["cloud_cover"].quantile(0.80)
    df_eval = _label_partition(df_eval, slug, _prcp_q95, _pressure_q15,
                               _humidity_q85, _cloud_q80)
    y_eval  = df_eval["weak_label"].values.astype(float)
    return "stored_test", df_train, df_cal, df_eval, y_eval


# ─────────────────────────────────────────────────────────────────────────────
# Per-city audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_city(slug: str, dry_run: bool = False) -> dict:
    """Run the calibration audit for one city and return the result dict."""
    city_dir = MODELS_DIR / slug
    if not city_dir.exists():
        raise FileNotFoundError(f"City model directory not found: {city_dir}")

    # ── Load training metrics ─────────────────────────────────────────────────
    metrics_path = city_dir / "training_metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"training_metrics.json not found for {slug}")
    with open(metrics_path) as fh:
        metrics = json.load(fh)

    logger.info("[%s] Loaded training_metrics.json", slug)

    # ── Load artefacts ────────────────────────────────────────────────────────
    import joblib
    from app.core.config import MCInferenceConfig
    from app.ml.models.city_hybrid import CityHybridModel
    from app.ml.models.fusion import FUSION_FEATURES
    from app.ml.models.tcn import TCN_SEQ_LEN

    n_ece_bins = MCInferenceConfig.CALIBRATION_ECE_BINS  # default 15

    logger.info("[%s] Loading CityHybridModel from %s …", slug, city_dir)
    model      = CityHybridModel.load(slug, city_dir)
    fusion     = joblib.load(city_dir / "lgbm_model.pkl")
    calibrator = joblib.load(city_dir / "calibrator.pkl")

    # ── Load preprocessor (v2 preferred) ─────────────────────────────────────
    prep_path_v2 = city_dir / "preprocessor_v2.joblib"
    prep_path    = city_dir / "preprocessor.joblib"
    if prep_path_v2.exists():
        prep = joblib.load(prep_path_v2)
        logger.info("[%s] Loaded preprocessor_v2.joblib", slug)
    elif prep_path.exists():
        prep = joblib.load(prep_path)
        logger.info("[%s] Loaded preprocessor.joblib (fallback)", slug)
    else:
        raise FileNotFoundError(f"No preprocessor found for {slug}")

    # ── Load master CSV ───────────────────────────────────────────────────────
    logger.info("[%s] Loading master CSV …", slug)
    df_full = pd.read_csv(DATA_CSV)
    df_full["date"] = pd.to_datetime(df_full["date"], errors="coerce")

    # Filter to this city (match by lowercase)
    city_col = df_full["city"].str.strip().str.lower() if "city" in df_full.columns else None
    if city_col is None:
        raise ValueError(f"[{slug}] CSV has no 'city' column")

    # Try exact slug match, then human name mapping
    _name_map = {
        "islamabad": ["islamabad"],
        "lahore":    ["lahore"],
        "karachi":   ["karachi"],
        "peshawar":  ["peshawar"],
        "quetta":    ["quetta"],
        "gilgit":    ["gilgit", "gilgit-baltistan"],
    }
    city_variants = _name_map.get(slug, [slug])
    df_city = df_full[city_col.isin(city_variants)].copy()

    if len(df_city) < MIN_EVAL_ROWS * 3:
        raise ValueError(
            f"[{slug}] Only {len(df_city)} rows in CSV — cannot audit."
        )
    logger.info("[%s] CSV rows for city: %d", slug, len(df_city))

    # ── Reconstruct train / cal / eval splits ─────────────────────────────────
    split_tier, df_train, df_cal, df_eval, y_eval = _reconstruct_splits(
        df_city, slug, metrics
    )
    logger.info("[%s] Split tier=%s  eval_rows=%d  positives=%d",
                slug, split_tier, len(df_eval), int((y_eval == 1).sum()))

    # Filter to labelled rows (weak_label != -1)
    mask_eval = y_eval != -1
    if mask_eval.sum() < MIN_EVAL_ROWS:
        raise ValueError(
            f"[{slug}] Only {mask_eval.sum()} labelled eval rows after masking"
        )

    # ── Transform splits with preprocessor ───────────────────────────────────
    X_train, _ = prep.transform(df_train)
    X_cal,   _ = prep.transform(df_cal)
    X_eval,  _ = prep.transform(df_eval)

    # ── Score eval OOF (AE + TCN) ─────────────────────────────────────────────
    logger.info("[%s] Scoring AE/TCN OOF on %d eval rows …", slug, len(X_eval))
    context_seed = np.vstack([X_train, X_cal]) if len(X_cal) > 0 else X_train
    ae_p, tcn_p, ae_v, tcn_v = _score_oof(model, X_eval, context_seed, TCN_SEQ_LEN)

    # ── Build FUSION_FEATURES matrix ──────────────────────────────────────────
    X_fus = _fusion_matrix(df_eval, ae_p, tcn_p, ae_v, tcn_v, FUSION_FEATURES)
    X_fus_masked = X_fus[mask_eval]
    y_masked     = y_eval[mask_eval]

    # Convert to DataFrame for FusionModel (expects feature-named columns)
    X_fus_df = pd.DataFrame(X_fus_masked, columns=FUSION_FEATURES)

    # ── Raw (pre-calibration) probabilities ───────────────────────────────────
    logger.info("[%s] Getting pre-calibration probabilities …", slug)
    p_raw = fusion.predict_proba(X_fus_df)
    if not isinstance(p_raw, np.ndarray):
        p_raw = np.asarray(p_raw, dtype=float)

    # ── Calibrated (post-calibration) probabilities ───────────────────────────
    logger.info("[%s] Applying IsotonicCalibrator …", slug)
    p_cal = calibrator.transform(p_raw)
    if not isinstance(p_cal, np.ndarray):
        p_cal = np.asarray(p_cal, dtype=float)

    # ── Compute metrics ───────────────────────────────────────────────────────
    pre_ece,  _,  _               = _ece(p_raw, y_masked, n_ece_bins)
    post_ece, bin_pops_post, reliability     = _ece(p_cal, y_masked, n_ece_bins)
    pre_brier  = _brier(p_raw, y_masked)
    post_brier = _brier(p_cal, y_masked)
    improvement = pre_ece - post_ece

    logger.info(
        "[%s] ECE: %.4f -> %.4f (improvement %.4f)  Brier: %.4f -> %.4f",
        slug, pre_ece, post_ece, improvement, pre_brier, post_brier,
    )

    # ── Build audit dict ──────────────────────────────────────────────────────
    cal_ece_calset = metrics.get("calibration_ece_after", None)

    audit: dict = {
        "audit_version":               AUDIT_VERSION,
        "pipeline_version":            PIPELINE_VERSION,
        "generated_at":                datetime.now(timezone.utc).isoformat(),
        "city_slug":                   slug,
        "calibration_method":          "isotonic",
        "calibration_ece_cal_set":     cal_ece_calset,
        "pre_calibration_ece_test":    round(pre_ece,  6),
        "post_calibration_ece_test":   round(post_ece, 6),
        "pre_calibration_brier_test":  round(pre_brier,  6),
        "post_calibration_brier_test": round(post_brier, 6),
        "calibration_improvement":     round(improvement, 6),
        "bin_populations":             bin_pops_post,
        "reliability_curve":           reliability,
        "calibration_bins_used":       n_ece_bins,
        "split_tier":                  split_tier,
        "eval_rows":                   int(mask_eval.sum()),
        "notes":                       "",
    }

    if dry_run:
        logger.info("[%s] DRY RUN — not writing any files", slug)
        return audit

    # ── Write calibration_audit.json ──────────────────────────────────────────
    audit_path = city_dir / "calibration_audit.json"
    with open(audit_path, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, indent=2)
    logger.info("[%s] Written: %s", slug, audit_path)

    # ── Append new fields to training_metrics.json (never overwrite) ──────────
    new_fields = {
        "calibration_ece_cal_set":      cal_ece_calset,
        "calibration_ece_test_set":     round(post_ece,    6),
        "calibration_brier_test_after": round(post_brier,  6),
        "calibration_bins_used":        n_ece_bins,
        "calibration_audit_path":
            f"backend/saved_models/city_models/{slug}/calibration_audit.json",
    }
    updated = False
    for key, val in new_fields.items():
        if key not in metrics:
            metrics[key] = val
            updated = True
    if updated:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=city_dir, suffix=".json.tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(metrics, fh, indent=2)
            Path(tmp_path).replace(metrics_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info("[%s] Appended new fields to training_metrics.json", slug)
    else:
        logger.info("[%s] training_metrics.json already has all audit fields — skipped", slug)

    return audit


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HydroGuard-AI calibration audit — measure ECE/Brier on held-out test splits"
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--all",  action="store_true", help="Audit all 6 trained cities")
    group.add_argument("--city", metavar="SLUG",      help="Audit a single city (e.g. islamabad)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute metrics but do NOT write any files")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    slugs = CITIES if args.all else [args.city.strip().lower()]

    results: dict = {}
    for slug in slugs:
        logger.info("=" * 60)
        logger.info("Auditing city: %s", slug)
        logger.info("=" * 60)
        try:
            result = audit_city(slug, dry_run=args.dry_run)
            results[slug] = {
                "status":  "ok",
                "pre_ece": result["pre_calibration_ece_test"],
                "post_ece": result["post_calibration_ece_test"],
                "improvement": result["calibration_improvement"],
                "eval_rows":   result["eval_rows"],
                "split_tier":  result["split_tier"],
            }
        except Exception as exc:
            logger.error("[%s] FAILED: %s", slug, exc, exc_info=True)
            results[slug] = {"status": "error", "error": str(exc)}

    # ── Summary table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(f"{'City':<12} {'Tier':<14} {'Rows':>6} {'Pre-ECE':>9} {'Post-ECE':>9} {'Improve':>9}")
    print("-" * 72)
    for slug, r in results.items():
        if r["status"] == "ok":
            print(f"{slug:<12} {r['split_tier']:<14} {r['eval_rows']:>6} "
                  f"{r['pre_ece']:>9.4f} {r['post_ece']:>9.4f} {r['improvement']:>+9.4f}")
        else:
            print(f"{slug:<12} {'ERROR':<14} {'':>6} {'':>9} {'':>9}  {r['error']}")
    print("=" * 72)

    if args.dry_run:
        print("\n[DRY RUN] No files were written.")


if __name__ == "__main__":
    main()
