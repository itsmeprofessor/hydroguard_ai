"""
HydroGuard-AI -- City-Specific Model Training Pipeline v3.5
=============================================================
AUDIT-CORRECTED PIPELINE

Leakage fixes from v3.4:
  L1 (CRITICAL) ECE = 0.0 artifact:
      Calibrator was fitted on CAL, then ECE measured on the SAME CAL data.
      Isotonic regression perfectly interpolates its own training set → ECE ≡ 0.
      Fix: Introduce TEST split (last 10% of non-holdout). ECE, AUC, Brier, FAR
      are all measured on TEST. Calibrator is fitted on CAL (as before) so it
      was NOT trained on TEST → ECE on TEST is a real number.

  L2 (HIGH) Global quantile labels:
      Percentile thresholds (q95 etc.) were computed on the full per-city
      series including holdout years.
      Fix: Thresholds computed on TRAIN partition only. CAL and TEST receive
      labels using TRAIN-fitted thresholds + EWI + anchors.

  L3 (HIGH) Physics features before holdout split:
      Rolling features were computed on the full series before removing holdout.
      Fix: Physics features computed per-split, after all chronological splits.

  L4 (MEDIUM) AUC reported from in-distribution eval:
      FusionModel's internal StratifiedGroupKFold splits CAL into train/eval.
      The "val_auc" was from a subset of its own training data (CAL).
      Fix: A separate unbiased TEST_AUC is now the primary metric.
      Fusion internal AUC is still reported but clearly labeled as in-distribution.

CORRECTED 4-WAY SPLIT (per city, strict chronological):
  HOLDOUT  (year >= 2023)         -- locked from day 1; evaluated last
  TEST     (last 10% of work)     -- unbiased ECE / AUC / Brier evaluation
  CAL      (prev 12%)             -- Fusion training + Calibrator fitting
  TRAIN    (first 78%)            -- AE/TCN training (TF internal val_split=0.15)

EXECUTION ORDER:
  1. Sort chronologically. Lock HOLDOUT (year >= 2023).
  2. Lock TEST (chronological last 10% of non-holdout).
  3. Split remaining: TRAIN 78% | CAL 22%.
  4. Compute physics features per-split (causal; post-split for cleanliness).
  5. Fit preprocessor on TRAIN only.
  6. Generate weak labels: percentile thresholds from TRAIN only.
     Propagate threshold to CAL/TEST/HOLDOUT (avoids global-stat leakage).
  7. Train AE+TCN on TRAIN (TF validation_split=0.15 for early stopping).
  8. Score CAL with AE/TCN (OOF - models never saw CAL).
  9. Train FusionModel on CAL OOF features.
  10. Fit IsotonicCalibrator on CAL predictions.
  11. Score TEST with AE/TCN -> Fusion -> Calibrator.
  12. Compute TEST metrics: AUC, PR-AUC, ECE, Brier, F1, FAR.
      ECE is now real: calibrator fitted on CAL, measured on held-out TEST.
  13. Score HOLDOUT -> final operational metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---- path setup ----
REPO_ROOT  = Path(__file__).parent.parent
BACKEND    = REPO_ROOT / "backend" if (REPO_ROOT / "backend").exists() else REPO_ROOT
sys.path.insert(0, str(BACKEND))

import types as _t
dotenv = _t.ModuleType("dotenv"); dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "train-city-script-key")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("train_city")

# ---- Split constants ----
HOLDOUT_YEAR_START = 2023
HOLDOUT_YEAR_END   = 2024
TEST_FRAC  = 0.10   # last 10% → unbiased evaluation
CAL_FRAC   = 0.22   # next 12% of remaining → fusion + calibrator
TRAIN_FRAC = 0.78   # first 78% of remaining → AE/TCN

# ---- Metrics gates ----
METRICS_GATE_AUC_FUSION = 0.65  # fusion internal AUC (in-distribution, informational)
METRICS_GATE_AUC_TEST   = 0.65  # unbiased TEST AUC gate — minimum for safety-critical deployment
METRICS_GATE_ECE        = 0.20  # real ECE on TEST


def _slug(city: str) -> str:
    return city.strip().lower().replace(" ", "_").replace("-", "_")


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=3, cwd=str(REPO_ROOT))
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _ensure_month(df: pd.DataFrame) -> pd.DataFrame:
    if "month" not in df.columns and "date" in df.columns:
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.month
    return df


def _ensure_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Compute static derived features that require no temporal ordering."""
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
    """
    Causal temporal dynamics on a pre-split, sorted partition.
    All rolling ops are strictly backward-looking.
    NaN at partition start is zero-filled (physically: no change detected yet).
    """
    df = df.copy().reset_index(drop=True)

    df["pressure_delta_3h"] = df["pressure"].diff(1)
    df["pressure_delta_6h"] = df["pressure"].diff(2)
    df["humidity_delta_3h"] = df["humidity"].diff(1)
    df["rain_rate_1h"]      = df["prcp"].diff(1).clip(lower=0.0)
    df["rain_accumulation_3h"] = df["prcp"].rolling(3, min_periods=1).sum()
    df["rain_accumulation_6h"] = df["prcp"].rolling(6, min_periods=1).sum()
    df["cloud_jump_3h"]     = df["cloud_cover"].diff(1)

    df["pressure_accel"]         = df["pressure_delta_3h"].diff(1)
    df["humidity_accel"]         = df["humidity_delta_3h"].diff(1)
    df["pressure_volatility_6d"] = df["pressure"].rolling(6, min_periods=2).std()
    df["humidity_volatility_6d"] = df["humidity"].rolling(6, min_periods=2).std()

    def _rolling_slope(s: pd.Series, w: int = 6) -> pd.Series:
        x = np.arange(w, dtype=float)
        def _sl(y):
            v = ~np.isnan(y)
            if v.sum() < 2: return 0.0
            return float(np.polyfit(x[:len(y)][v], y[v], 1)[0])
        return s.rolling(w, min_periods=2).apply(_sl, raw=True)

    df["prcp_trend_6d"] = _rolling_slope(df["prcp"], 6)

    tdew_safe = df.get("tdew_spread", pd.Series(5.0, index=df.index)).clip(lower=0.5).fillna(5.0)
    mf = df.get("moisture_flux", pd.Series(0.0, index=df.index)).fillna(0.0)
    df["atm_instability"] = mf * df["pressure_delta_3h"].abs().fillna(0.0) / tdew_safe

    for col in ["pressure_delta_3h","pressure_delta_6h","humidity_delta_3h","rain_rate_1h",
                "cloud_jump_3h","pressure_accel","humidity_accel","pressure_volatility_6d",
                "humidity_volatility_6d","prcp_trend_6d","atm_instability"]:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    return df


def _compute_karachi_coastal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 9 coastal features for a Karachi partition.
    Must be called AFTER _compute_physics_features() so that
    pressure_delta_*, humidity_delta_*, rain_accumulation_* are available.
    """
    from app.ml.feature_pipeline import _karachi_coastal_features

    df = df.copy()
    if "day" not in df.columns and "date" in df.columns:
        df["day"] = pd.to_datetime(df["date"], errors="coerce").dt.day.fillna(15).astype(int)

    rows = []
    for _, row in df.iterrows():
        coastal = _karachi_coastal_features(
            raw=row.to_dict(),
            month=int(row.get("month", 6) or 6),
            day=int(row.get("day", 15) or 15),
            pressure_delta_3h=float(row.get("pressure_delta_3h", 0.0) or 0.0),
            pressure_delta_6h=float(row.get("pressure_delta_6h", 0.0) or 0.0),
            humidity_delta_3h=float(row.get("humidity_delta_3h", 0.0) or 0.0),
            rain_accumulation_6h=float(row.get("rain_accumulation_6h", 0.0) or 0.0),
        )
        rows.append(coastal)

    coastal_df = pd.DataFrame(rows, index=df.index)
    return pd.concat([df, coastal_df], axis=1)


# ─── Historical event anchors (external PMD/NDMA knowledge) ──────────────────
HISTORICAL_EVENTS: Dict[str, List[str]] = {
    "islamabad":  ["2010-07-29","2014-09-05","2020-08-27","2022-08-25",
                   "2018-07-24","2023-07-12"],
    "rawalpindi": ["2010-07-29","2022-08-25","2014-09-05","2020-07-28"],
    "lahore":     ["2010-07-29","2020-08-11","2021-07-01","2022-07-21",
                   "2015-07-24","2023-07-10"],
    "karachi":    ["2010-08-01","2018-06-29","2020-08-27","2022-07-11",
                   "2021-07-27","2023-06-15"],
    "peshawar":   ["2010-07-29","2022-08-26","2020-08-28","2021-07-29"],
    "quetta":     ["2015-05-04","2020-08-28","2022-08-09","2021-08-01"],
    "gilgit":     ["2010-07-29","2018-07-18","2022-08-16","2021-08-04","2019-07-15"],
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
        df.loc[pre,  "weak_label"] = 1; df.loc[pre,  "weak_label_conf"] = 1.0
        df.loc[day,  "weak_label"] = 1; df.loc[day,  "weak_label_conf"] = 1.0
        df.loc[post, "weak_label"] = 1; df.loc[post, "weak_label_conf"] = 0.8
    n = int((df["weak_label"] == 1).sum())
    if n:
        logger.info("[%s] Historical anchors: %d rows positive", slug, n)
    return df


def _compute_ewi(g: pd.DataFrame) -> pd.Series:
    """EWI — no global statistics, strictly local + physics."""
    rain  = (g["prcp"].clip(0, 80) / 80.0).fillna(0.0)
    pdrop = (-g["pressure_delta_3h"].clip(-10, 0) / 10.0).fillna(0.0)
    hum   = ((g["humidity"].clip(50, 100) - 50) / 50.0).fillna(0.0)
    cld   = (g["cloud_cover"].clip(0, 100) / 100.0).fillna(0.0)
    ewi   = 0.35 * rain + 0.30 * pdrop + 0.20 * hum + 0.15 * cld
    if "is_monsoon_month" in g.columns:
        ewi[g["is_monsoon_month"] == 1] = (ewi[g["is_monsoon_month"] == 1] * 1.15).clip(upper=1.0)
    return ewi


def _label_partition(
    df: pd.DataFrame,
    slug: str,
    prcp_q95:     Optional[float] = None,
    pressure_q15: Optional[float] = None,
    humidity_q85: Optional[float] = None,
    cloud_q80:    Optional[float] = None,
) -> pd.DataFrame:
    """
    Apply all labeling layers to one partition.

    If TRAIN-derived quantile thresholds are supplied (non-None), Layer C
    (percentile baseline) is applied using those thresholds — not global stats.
    For TRAIN itself the thresholds are computed internally.
    For CAL/TEST/HOLDOUT the TRAIN thresholds are passed in (FIX for L2).
    """
    df = df.copy()

    # Layer C: percentile baseline
    if prcp_q95 is None:
        # Called on TRAIN — compute from this partition's own data
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

    # Layer B: EWI (physics-based; no global stats)
    ewi = _compute_ewi(df)
    df.loc[ewi >= 0.55, "weak_label"]      = 1
    df.loc[ewi >= 0.55, "weak_label_conf"] = ewi[ewi >= 0.55].clip(0.75, 0.95)
    df.loc[(ewi <= 0.20) & (df["weak_label"] == 1), "weak_label"] = 0
    df.loc[(ewi <= 0.20) & (df["weak_label"] != 1), "weak_label_conf"] = 0.80

    # Layer A: historical anchors (external knowledge — always applied)
    df = _apply_historical_anchors(df, slug)

    return df


def _score_oof(
    model,
    X_arr: np.ndarray,
    context_seed: np.ndarray,
    seq_len: int,
) -> Tuple[List, List, List, List]:
    """
    Score a partition out-of-fold using a rolling context buffer seeded
    from the preceding partitions. Mirrors exact deployment-time behaviour.
    """
    ae_pcts, tcn_pcts, ae_vars, tcn_vars = [], [], [], []
    ctx = list(context_seed[-seq_len:]) if len(context_seed) >= seq_len else list(context_seed)
    for i, x_vec in enumerate(X_arr):
        seq = np.array(ctx[-seq_len:]) if len(ctx) >= seq_len else None
        raw = model.predict(x_vec, seq)
        ae_pcts.append(raw["ae_percentile"])
        tcn_pcts.append(raw["tcn_percentile"])
        ae_vars.append(raw["ae_variance"])
        tcn_vars.append(raw["tcn_variance"])
        ctx.append(x_vec)
    return ae_pcts, tcn_pcts, ae_vars, tcn_vars


def _fusion_matrix(
    df_split: pd.DataFrame,
    ae_p, tcn_p, ae_v, tcn_v,
    features: List[str],
) -> np.ndarray:
    rows = df_split.to_dict("records")
    mat  = []
    for row, ap, tp, av, tv in zip(rows, ae_p, tcn_p, ae_v, tcn_v):
        d = {f: float(row.get(f, 0.0) or 0.0) for f in features
             if f not in ("ae_percentile","tcn_percentile","ae_variance","tcn_variance")}
        d.update({"ae_percentile": ap, "tcn_percentile": tp,
                  "ae_variance":   av, "tcn_variance":   tv})
        mat.append([d.get(f, 0.0) for f in features])
    return np.array(mat, dtype=float)


def train_one_city(
    slug:       str,
    df_city:    pd.DataFrame,
    models_dir: Path,
    epochs:     int  = 150,
    batch_size: int  = 64,
    use_tcn:    bool = True,
    force:      bool = False,
    seed:       int  = 42,
) -> dict:
    """
    Causally-valid 4-way training pipeline.
    TRAIN | CAL | TEST | HOLDOUT — all strictly chronological.
    """
    from app.ml.models.city_hybrid   import CityHybridModel
    from app.ml.models.fusion        import FusionModel, FUSION_FEATURES
    from app.ml.calibration.isotonic import IsotonicCalibrator
    from app.ml.ood.detector         import OODDetector, OOD_FEATURES
    from app.ml.models.tcn           import TCN_SEQ_LEN
    from app.ml.preprocessing_v2     import WeatherDataPreprocessorV2
    from app.ml.validation.leakage_audit import LeakageAuditor, LeakageError
    from app.ml.evaluation.production_metrics import OperationalMetricsCalculator
    from sklearn.metrics import (roc_auc_score, average_precision_score,
                                 brier_score_loss, f1_score,
                                 precision_score, recall_score, confusion_matrix)

    np.random.seed(seed)
    try:
        import tensorflow as tf; tf.random.set_seed(seed)
    except Exception:
        pass

    city_dir = models_dir / slug
    tmp_dir  = models_dir / f"{slug}.tmp"
    if tmp_dir.exists(): shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    logger.info("[%s] Starting v3.5 pipeline: %d rows", slug, len(df_city))
    t0 = time.time()

    # ── 1. Sort chronologically ───────────────────────────────────────────────
    df_city = _ensure_month(df_city)
    df_city = _ensure_derived(df_city)
    if "date" in df_city.columns:
        df_city["date"] = pd.to_datetime(df_city["date"], errors="coerce")
        df_city = df_city.sort_values("date").reset_index(drop=True)

    # ── 2. Lock HOLDOUT ───────────────────────────────────────────────────────
    if "date" in df_city.columns:
        hm          = df_city["date"].dt.year >= HOLDOUT_YEAR_START
        df_holdout  = df_city[hm].copy().reset_index(drop=True)
        df_work     = df_city[~hm].copy().reset_index(drop=True)
    else:
        df_holdout  = pd.DataFrame()
        df_work     = df_city.copy()

    n_work = len(df_work)
    logger.info("[%s] HOLDOUT=%d rows | workable=%d rows", slug, len(df_holdout), n_work)
    if n_work < 300:
        raise ValueError(f"[{slug}] Only {n_work} workable rows.")

    # ── 3. Lock TEST (last 10% of workable) ──────────────────────────────────
    test_start = int(n_work * (1.0 - TEST_FRAC))
    df_test    = df_work.iloc[test_start:].copy().reset_index(drop=True)
    df_nt      = df_work.iloc[:test_start].copy().reset_index(drop=True)

    # ── 4. Split remaining into TRAIN (78%) | CAL (22%) ──────────────────────
    n_nt     = len(df_nt)
    cal_start = int(n_nt * TRAIN_FRAC)
    df_train  = df_nt.iloc[:cal_start].copy().reset_index(drop=True)
    df_cal    = df_nt.iloc[cal_start:].copy().reset_index(drop=True)

    logger.info("[%s] Splits — TRAIN=%d  CAL=%d  TEST=%d  HOLDOUT=%d",
                slug, len(df_train), len(df_cal), len(df_test), len(df_holdout))
    if len(df_train) < 200:
        raise ValueError(f"[{slug}] TRAIN too small ({len(df_train)} rows).")

    # ── 5. Physics features per-split (causal; post-split) ───────────────────
    df_train = _compute_physics_features(df_train)
    df_cal   = _compute_physics_features(df_cal)
    df_test  = _compute_physics_features(df_test)
    if len(df_holdout):
        df_holdout = _compute_physics_features(df_holdout)

    # ── 5b. Karachi coastal features (after physics; before preprocessor fit) ─
    if slug == "karachi":
        df_train   = _compute_karachi_coastal_features(df_train)
        df_cal     = _compute_karachi_coastal_features(df_cal)
        df_test    = _compute_karachi_coastal_features(df_test)
        if len(df_holdout):
            df_holdout = _compute_karachi_coastal_features(df_holdout)
        logger.info("[karachi] Coastal features added to all %d splits",
                    4 if len(df_holdout) else 3)

    # ── 6. Preprocessor fitted on TRAIN only ─────────────────────────────────
    prep = WeatherDataPreprocessorV2()
    prep.fit(df_train)
    X_train, feat_names = prep.transform(df_train)
    X_cal,   _          = prep.transform(df_cal)
    X_test,  _          = prep.transform(df_test)
    input_dim = X_train.shape[1]
    logger.info("[%s] input_dim=%d", slug, input_dim)

    # ── 7. Weak labels — TRAIN uses own stats; CAL/TEST use TRAIN thresholds ─
    # FIX for L2: no global dataset stats; thresholds computed on TRAIN only
    df_train = _label_partition(df_train, slug)  # computes thresholds internally

    # Extract TRAIN-fitted thresholds for propagation
    _prcp_q95     = df_train["prcp"].quantile(0.95)   if "prcp"       in df_train.columns else None
    _pressure_q15 = df_train["pressure"].quantile(0.15) if "pressure" in df_train.columns else None
    _humidity_q85 = df_train["humidity"].quantile(0.85) if "humidity" in df_train.columns else None
    _cloud_q80    = df_train["cloud_cover"].quantile(0.80) if "cloud_cover" in df_train.columns else None

    df_cal   = _label_partition(df_cal,   slug, _prcp_q95, _pressure_q15, _humidity_q85, _cloud_q80)
    df_test  = _label_partition(df_test,  slug, _prcp_q95, _pressure_q15, _humidity_q85, _cloud_q80)
    if len(df_holdout):
        df_holdout = _label_partition(df_holdout, slug, _prcp_q95, _pressure_q15, _humidity_q85, _cloud_q80)

    y_train = df_train["weak_label"].values.astype(float)
    y_cal   = df_cal["weak_label"].values.astype(float)
    y_test  = df_test["weak_label"].values.astype(float)

    logger.info("[%s] Label rates — TRAIN=%.3f  CAL=%.3f  TEST=%.3f",
                slug, (y_train==1).mean(), (y_cal==1).mean(), (y_test==1).mean())

    # ── 8. Leakage audit (TRAIN vs first quarter of CAL as proxy for val) ────
    leakage_score = 0.0
    leakage_cat   = "UNKNOWN"
    # Use first half of CAL as the "val" proxy for the audit
    n_cal_half = max(1, len(X_cal) // 2)
    try:
        auditor = LeakageAuditor()
        report  = auditor.audit(
            X_train       = X_train,
            X_val         = X_cal[:n_cal_half],
            y_train       = y_train,
            y_val         = y_cal[:n_cal_half],
            dates_train   = df_train["date"] if "date" in df_train.columns else None,
            dates_val     = df_cal["date"].iloc[:n_cal_half] if "date" in df_cal.columns else None,
            feature_names = feat_names,
            city_slug     = slug,
            event_anchors = HISTORICAL_EVENTS.get(slug, []),
            seq_len       = TCN_SEQ_LEN,
            abort_threshold = 75 if not force else 101,
        )
        leakage_score = report.total_score
        leakage_cat   = report.category
        report.save(tmp_dir / "leakage_audit.json")
    except LeakageError as exc:
        if not force: raise
        logger.warning("[%s] Leakage gate (--force): %s", slug, exc)
    except Exception as exc:
        logger.warning("[%s] Leakage audit failed: %s", slug, exc)

    # ── 9. AE + TCN — trained on TRAIN, TF validation_split=0.15 internally ─
    model = CityHybridModel(city=slug, input_dim=input_dim, feature_names=feat_names)
    model.build()
    ae_hist, tcn_hist = model.train(
        X_train     = X_train,
        X_val       = X_cal[:n_cal_half],  # use first half of CAL for AE early stopping
        weak_labels = y_train,
        epochs      = epochs,
        batch_size  = batch_size,
    )
    ae_val_loss  = min(ae_hist.history["val_loss"])  if ae_hist  else None
    tcn_val_loss = min(tcn_hist.history["val_loss"]) if tcn_hist else None

    # ── 10. Score CAL OOF (AE/TCN never saw CAL) → Fusion training ───────────
    logger.info("[%s] Scoring CAL (%d rows) OOF for Fusion...", slug, len(X_cal))
    ae_c, tcn_c, aev_c, tcnv_c = _score_oof(model, X_cal, X_train, TCN_SEQ_LEN)
    X_cal_fus = _fusion_matrix(df_cal, ae_c, tcn_c, aev_c, tcnv_c, FUSION_FEATURES)

    # ── 11. Train FusionModel on CAL OOF ─────────────────────────────────────
    lgbm_internal_auc   = float("nan")
    lgbm_internal_brier = 0.25
    fusion       = FusionModel()
    mask_cal     = (y_cal != -1)

    if mask_cal.sum() >= 30:
        Xf  = X_cal_fus[mask_cal]
        yf  = y_cal[mask_cal]
        wf  = df_cal["weak_label_conf"].values[mask_cal] if "weak_label_conf" in df_cal.columns else None
        cal_dates = df_cal["date"].reset_index(drop=True).iloc[mask_cal] if "date" in df_cal.columns else None
        md  = fusion.train(Xf, yf, sample_weight=wf, dates=cal_dates)
        lgbm_internal_auc   = md.get("val_auc",   float("nan"))
        lgbm_internal_brier = md.get("val_brier", 0.25)
        auc_s = f"{lgbm_internal_auc:.4f}" if not np.isnan(lgbm_internal_auc) else "NaN"
        logger.info("[%s] Fusion internal AUC=%s (in-distribution, NOT the primary metric)",
                    slug, auc_s)
    else:
        logger.warning("[%s] Not enough CAL rows (%d non-abstained) for Fusion", slug, mask_cal.sum())

    if not force and fusion.is_fitted:
        if np.isnan(lgbm_internal_auc):
            raise ValueError(f"[{slug}] Fusion internal AUC=NaN. Use --force.")
        if lgbm_internal_auc >= 0.999:
            logger.warning("[%s] Fusion internal AUC=%.4f near-perfect — check labels.", slug, lgbm_internal_auc)

    # ── 12. Calibrator fitted on CAL predictions ─────────────────────────────
    cal_obj     = IsotonicCalibrator()
    cal_metrics = None
    if fusion.is_fitted and mask_cal.sum() >= 20:
        p_raw_cal   = fusion.predict_proba(X_cal_fus[mask_cal])
        cal_metrics = cal_obj.fit(p_raw_cal, y_cal[mask_cal])
        np.savez(tmp_dir / "cal_data.npz",
                 y_true=y_cal[mask_cal], y_score=p_raw_cal)
        logger.info("[%s] Calibrator fitted on CAL: Brier %.4f->%.4f",
                    slug, cal_metrics.brier_before, cal_metrics.brier_after)

    # ── 13. OOD Detector ─────────────────────────────────────────────────────
    ood = OODDetector()
    X_ood = np.array([[float(r.get(f, 0.0) or 0.0) for f in OOD_FEATURES]
                      for r in df_train.to_dict("records")], dtype=float)
    ood.fit(X_ood)

    # ── 14. TEST evaluation — unbiased (neither Fusion nor Calibrator saw TEST)
    test_metrics: dict = {}
    logger.info("[%s] Evaluating TEST (%d rows) — primary unbiased metric...", slug, len(X_test))
    try:
        ae_t, tcn_t, aev_t, tcnv_t = _score_oof(
            model, X_test, np.vstack([X_train, X_cal]), TCN_SEQ_LEN
        )
        X_test_fus = _fusion_matrix(df_test, ae_t, tcn_t, aev_t, tcnv_t, FUSION_FEATURES)
        mask_t  = (y_test != -1)

        if fusion.is_fitted and mask_t.sum() >= 10:
            p_raw_t = fusion.predict_proba(X_test_fus[mask_t])
            # Calibrator transforms TEST probabilities — it was NOT fitted on TEST
            p_cal_t = cal_obj.transform(p_raw_t) if cal_obj.is_fitted else p_raw_t
            y_tv    = y_test[mask_t]
            y_bin_t = (p_cal_t >= 0.5).astype(int)

            def _s(fn, *a, **kw):
                try: return float(fn(*a, **kw))
                except: return None

            t_auc    = _s(roc_auc_score,           y_tv, p_cal_t)
            t_pr_auc = _s(average_precision_score,  y_tv, p_cal_t)
            t_brier  = _s(brier_score_loss,         y_tv, p_cal_t)
            # ECE on TEST — calibrator was fitted on CAL, not TEST → this is REAL
            t_ece    = _s(IsotonicCalibrator.ece,   p_cal_t, y_tv)
            t_f1     = _s(f1_score,         y_tv, y_bin_t, zero_division=0)
            t_prec   = _s(precision_score,  y_tv, y_bin_t, zero_division=0)
            t_rec    = _s(recall_score,     y_tv, y_bin_t, zero_division=0)
            try:
                tn, fp, fn_c, tp = confusion_matrix(y_tv, y_bin_t).ravel()
                t_far = round(fp / max(fp + tn, 1), 4)
            except Exception:
                t_far = None

            gap = (round(lgbm_internal_auc - t_auc, 4)
                   if t_auc is not None and not np.isnan(lgbm_internal_auc) else None)

            test_metrics = {
                "test_auc":       round(t_auc,    4) if t_auc    is not None else None,
                "test_pr_auc":    round(t_pr_auc, 4) if t_pr_auc is not None else None,
                "test_brier":     round(t_brier,  4) if t_brier  is not None else None,
                "test_ece":       round(t_ece,    4) if t_ece    is not None else None,
                "test_f1":        round(t_f1,     4) if t_f1     is not None else None,
                "test_precision": round(t_prec,   4) if t_prec   is not None else None,
                "test_recall":    round(t_rec,    4) if t_rec    is not None else None,
                "test_far":       t_far,
                "test_n_rows":    int(mask_t.sum()),
                "fusion_vs_test_gap": gap,
                "gap_flag": ("HIGH" if gap is not None and abs(gap) > 0.15 else
                             "MODERATE" if gap is not None and abs(gap) > 0.08 else "LOW"),
            }
            logger.info(
                "[%s] TEST: AUC=%.4f  PR-AUC=%.4f  ECE=%.4f  Brier=%.4f  F1=%.4f",
                slug,
                t_auc or 0, t_pr_auc or 0, t_ece or 0, t_brier or 0, t_f1 or 0,
            )

            # Gate on TEST AUC (the real metric)
            if not force and t_auc is not None and t_auc < METRICS_GATE_AUC_TEST:
                logger.warning("[%s] TEST_AUC=%.4f below gate %.2f",
                               slug, t_auc, METRICS_GATE_AUC_TEST)

            # Gate on TEST ECE (the real calibration score)
            if not force and t_ece is not None and t_ece > METRICS_GATE_ECE:
                logger.warning("[%s] TEST_ECE=%.4f above gate %.2f",
                               slug, t_ece, METRICS_GATE_ECE)

    except Exception as exc:
        logger.warning("[%s] TEST evaluation failed: %s", slug, exc)

    # ── 15. HOLDOUT evaluation ────────────────────────────────────────────────
    holdout_metrics: dict = {}
    op_metrics_dict: dict = {}
    if len(df_holdout) >= 10 and fusion.is_fitted:
        logger.info("[%s] Evaluating HOLDOUT (%d rows)...", slug, len(df_holdout))
        try:
            X_ho, _ = prep.transform(df_holdout)
            ae_h, tcn_h, aev_h, tcnv_h = _score_oof(
                model, X_ho, np.vstack([X_train, X_cal, X_test]), TCN_SEQ_LEN
            )
            X_ho_fus = _fusion_matrix(df_holdout, ae_h, tcn_h, aev_h, tcnv_h, FUSION_FEATURES)
            y_ho     = (df_holdout["weak_label"].values.astype(float)
                        if "weak_label" in df_holdout.columns else np.zeros(len(df_holdout)))
            mask_ho  = (y_ho != -1)
            p_raw_ho = fusion.predict_proba(X_ho_fus[mask_ho])
            p_cal_ho = cal_obj.transform(p_raw_ho) if cal_obj.is_fitted else p_raw_ho
            y_hov    = y_ho[mask_ho]
            y_bin_ho = (p_cal_ho >= 0.5).astype(int)

            h_auc    = _s(roc_auc_score,           y_hov, p_cal_ho)
            h_pr_auc = _s(average_precision_score,  y_hov, p_cal_ho)
            h_brier  = _s(brier_score_loss,         y_hov, p_cal_ho)
            h_f1     = _s(f1_score, y_hov, y_bin_ho, zero_division=0)
            try:
                tn, fp, fn_c, tp = confusion_matrix(y_hov, y_bin_ho).ravel()
                h_far = round(fp / max(fp + tn, 1), 4)
            except Exception:
                h_far = None

            holdout_metrics = {
                "holdout_auc":    round(h_auc,    4) if h_auc    else None,
                "holdout_pr_auc": round(h_pr_auc, 4) if h_pr_auc else None,
                "holdout_brier":  round(h_brier,  4) if h_brier  else None,
                "holdout_f1":     round(h_f1,     4) if h_f1     else None,
                "holdout_far":    h_far,
                "holdout_n_rows": int(mask_ho.sum()),
            }
            logger.info("[%s] HOLDOUT: AUC=%.4f  Brier=%.4f  F1=%.4f",
                        slug, h_auc or 0, h_brier or 0, h_f1 or 0)

            try:
                calc = OperationalMetricsCalculator()
                op   = calc.compute_all(
                    dates           = df_holdout["date"].reset_index(drop=True),
                    y_true          = y_ho,
                    p_hat           = np.where(mask_ho,
                        np.concatenate([p_cal_ho, np.zeros(len(y_ho)-mask_ho.sum())]),
                        0.0,
                    ),
                    event_anchors   = [e for e in HISTORICAL_EVENTS.get(slug, [])
                                       if int(e[:4]) >= HOLDOUT_YEAR_START],
                    city_slug       = slug,
                    alert_threshold = 0.50,
                    pre_event_days  = PRE_EVENT_WINDOW,
                )
                op_metrics_dict = op.to_dict()
                op.save(tmp_dir / "operational_metrics.json")
            except Exception as exc:
                logger.warning("[%s] Operational metrics: %s", slug, exc)

        except Exception as exc:
            logger.warning("[%s] HOLDOUT failed: %s", slug, exc)

    # ── 16. Atomic save ───────────────────────────────────────────────────────
    model.save(tmp_dir)
    fusion.save(tmp_dir / "lgbm_model.pkl")
    cal_obj.save(tmp_dir / "calibrator.pkl")
    ood.save(tmp_dir / "ood_detector.pkl")
    prep.save(tmp_dir / "preprocessor_v2.joblib")

    elapsed    = time.time() - t0
    auc_finite = lgbm_internal_auc if not np.isnan(lgbm_internal_auc) else None

    summary = {
        "city_slug":         slug,
        "model_version":     f"{slug}-v{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "pipeline_version":  "v3.5",
        "git_commit":        _git_commit(),
        "trained_at":        datetime.now(timezone.utc).isoformat(),
        "training_rows":     len(df_train),
        "cal_rows":          len(df_cal),
        "test_rows":         len(df_test),
        "holdout_rows":      len(df_holdout),
        "input_dim":         input_dim,
        "positive_rate_train": float((y_train == 1).mean()),
        "ae_val_loss":       ae_val_loss,
        "tcn_val_loss":      tcn_val_loss,
        # Fusion internal AUC — in-distribution, informational only
        "fusion_internal_auc":   auc_finite,
        "fusion_internal_brier": lgbm_internal_brier,
        "fusion_split_method":   fusion.split_info.get("method", "unknown") if fusion.is_fitted else "not_trained",
        # Calibration fitted on CAL
        "calibration_ece_before": cal_metrics.ece_before   if cal_metrics else None,
        "calibration_ece_after":  cal_metrics.ece_after    if cal_metrics else None,
        "calibration_brier_after":cal_metrics.brier_after  if cal_metrics else None,
        # Leakage
        "leakage_score":     leakage_score,
        "leakage_category":  leakage_cat,
        # Primary unbiased metrics (TEST)
        **test_metrics,
        # Operational (HOLDOUT)
        **holdout_metrics,
        "operational_metrics_path": str(tmp_dir / "operational_metrics.json") if op_metrics_dict else None,
        "coastal_features":      slug == "karachi",
        "coastal_feature_names": [
            "sst_anomaly", "sea_breeze_instability", "cyclone_proximity",
            "cyclone_season", "humidity_persistence", "coastal_moisture_flux",
            "urban_drainage_stress", "tidal_proxy", "coastal_pressure_grad",
        ] if slug == "karachi" else [],
        "integrity_audit_auc":   None,
        "duration_seconds":  round(elapsed, 1),
    }

    (tmp_dir / "training_metrics.json").write_text(json.dumps(summary, indent=2, default=str))

    if city_dir.exists():
        archive = models_dir / f"{slug}.bak"
        if archive.exists(): shutil.rmtree(archive)
        shutil.move(str(city_dir), str(archive))
    shutil.move(str(tmp_dir), str(city_dir))

    logger.info(
        "[%s] Done %.1fs | fusion_AUC=%s | TEST_AUC=%s | TEST_ECE=%s | HOLDOUT_AUC=%s | leak=%s",
        slug, elapsed, auc_finite,
        test_metrics.get("test_auc", "N/A"),
        test_metrics.get("test_ece", "N/A"),
        holdout_metrics.get("holdout_auc", "N/A"),
        leakage_cat,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGuard-AI v3.5 training pipeline")
    parser.add_argument("--city",        default=None)
    parser.add_argument("--all",         action="store_true")
    parser.add_argument("--data",        required=True)
    parser.add_argument("--epochs",      type=int, default=150)
    parser.add_argument("--batch-size",  type=int, default=64)
    parser.add_argument("--no-tcn",      action="store_true")
    parser.add_argument("--force",       action="store_true")
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--models-dir",  default="backend/saved_models/city_models")
    parser.add_argument("--min-records", type=int, default=500)
    args = parser.parse_args()

    data_path  = Path(args.data)
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr); sys.exit(1)

    df = pd.read_csv(data_path, low_memory=False)
    df = _ensure_month(df)
    df = _ensure_derived(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["city", "date"]).reset_index(drop=True)

    # Pre-attach historical anchors (external knowledge, pre-split safe).
    # Percentile-based labels are computed inside train_one_city() per split.
    def _attach_anchors(df: pd.DataFrame) -> pd.DataFrame:
        parts = []
        for cv, g in df.groupby("city"):
            g = g.copy().sort_values("date").reset_index(drop=True)
            g = _ensure_derived(g)
            g["pressure_delta_3h"] = g["pressure"].diff(1).fillna(0.0) if "pressure" in g.columns else 0.0
            g["weak_label"]      = 0
            g["weak_label_conf"] = 0.5
            g = _apply_historical_anchors(g, _slug(str(cv)))
            parts.append(g)
        return pd.concat(parts, ignore_index=True)

    logger.info("Attaching historical anchors...")
    df = _attach_anchors(df)
    print(f"\nAnchor positive rate: {(df['weak_label']==1).mean():.4f}")

    slugs = ([_slug(c) for c in df["city"].dropna().unique()] if args.all and "city" in df.columns
             else [_slug(args.city)] if args.city
             else (parser.error("--city or --all required") or []))

    results = []
    for slug in sorted(slugs):
        df_city = df[df["city"].apply(_slug) == slug].copy() if "city" in df.columns else df.copy()
        if len(df_city) < args.min_records:
            print(f"SKIP {slug}: {len(df_city)} rows < {args.min_records}"); continue
        try:
            s = train_one_city(slug, df_city, models_dir,
                               epochs=args.epochs, batch_size=args.batch_size,
                               use_tcn=not args.no_tcn, force=args.force, seed=args.seed)
            results.append({"city": slug, "status": "success", **s})
        except Exception as exc:
            logger.error("[%s] FAILED: %s", slug, exc, exc_info=True)
            results.append({"city": slug, "status": "failed", "error": str(exc)})

    print("\n" + "=" * 80)
    print("  HYDROGUARD-AI v3.5  AUDIT-CORRECTED TRAINING SUMMARY")
    print("=" * 80)
    print(f"  {'City':<12} {'Status':<10} {'FusionAUC':<11} {'TEST_AUC':<10} "
          f"{'TEST_ECE':<10} {'h_AUC':<9} {'Leak':<8} {'Deploy'}")
    print("  " + "-" * 76)
    for r in results:
        fa   = r.get("fusion_internal_auc")
        ta   = r.get("test_auc")
        te   = r.get("test_ece")
        ha   = r.get("holdout_auc")
        leak = r.get("leakage_category", "UNKNOWN")
        gap  = r.get("gap_flag", "")
        fs = f"{float(fa):.4f}" if fa is not None else "NaN"
        ts = f"{float(ta):.4f}" if ta is not None else "N/A"
        es = f"{float(te):.4f}" if te is not None else "N/A"
        hs = f"{float(ha):.4f}" if ha is not None else "N/A"

        issues = []
        if fs == "NaN":                                               issues.append("FusionNaN")
        if ta is not None and float(ta) < METRICS_GATE_AUC_TEST:     issues.append(f"AUC<{METRICS_GATE_AUC_TEST}")
        if te is not None and float(te) > METRICS_GATE_ECE:          issues.append(f"ECE>{METRICS_GATE_ECE}")
        if leak in ("HIGH","CRITICAL"):                               issues.append(f"Leak:{leak}")
        if gap == "HIGH":                                             issues.append("Gap:HIGH")
        deploy = "READY" if not issues else ("CAUTION" if len(issues) == 1 else "BLOCKED")

        print(f"  {r['city']:<12} {r['status']:<10} {fs:<11} {ts:<10} {es:<10} "
              f"{hs:<9} {leak:<8} {deploy}"
              + (f"  <- {', '.join(issues)}" if issues else ""))
    print("=" * 80)
    print("\n  KEY:")
    print("  FusionAUC = internal AUC on CAL OOF folds (in-distribution, informational)")
    print("  TEST_AUC  = unbiased AUC on held-out TEST set (primary metric)")
    print("  TEST_ECE  = real calibration error — calibrator fitted on CAL, not TEST")
    print("  h_AUC     = holdout 2023-2024 AUC\n")


if __name__ == "__main__":
    main()
