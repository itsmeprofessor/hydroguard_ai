"""
HydroGuard-AI -- City-Specific Model Training Pipeline v3.2
=============================================================
Trains: AE (fair-weather filter) + TCN (next-step MSE) + LightGBM FusionModel
        + IsotonicCalibrator + OODDetector

All architecture constants are LOCKED -- do not change:
  TCN: seq_len=24, dilations=[1,2,4,8], kernel=3, filters=64
  AE:  encoder [64,32,16], latent 8, Dropout 0.20
  Fusion: LightGBM, 16 features, scale_pos_weight auto

Usage:
    python scripts/train_city.py --city Islamabad --data backend/data/pakistan_weather_labeled.csv
    python scripts/train_city.py --all --data backend/data/pakistan_weather_labeled.csv
    python scripts/train_city.py --city Islamabad --epochs 5 --force   # CI quick run
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
from typing import Optional

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

# ---- Constants ----
METRICS_GATE_AUC = 0.70
METRICS_GATE_ECE = 0.10


def _slug(city: str) -> str:
    return city.strip().lower().replace(" ", "_").replace("-", "_")


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=3, cwd=str(REPO_ROOT))
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _data_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _ensure_month(df: pd.DataFrame) -> pd.DataFrame:
    if "month" not in df.columns and "date" in df.columns:
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.month
    return df


def _ensure_derived(df: pd.DataFrame) -> pd.DataFrame:
    if "tavg" in df.columns and "dew_point" in df.columns and "tdew_spread" not in df.columns:
        df["tdew_spread"] = df["tavg"] - df["dew_point"]
    if "humidity" in df.columns and "wspd" in df.columns and "moisture_flux" not in df.columns:
        df["moisture_flux"] = (df["humidity"] / 100.0) * df["wspd"]
    for col in ["pressure_delta_3h", "pressure_delta_6h", "rain_rate_1h",
                "rain_accumulation_3h", "prcp_climo_pct", "humidity_climo_pct",
                "cloud_jump_3h"]:
        if col not in df.columns:
            df[col] = 0.0 if "climo" not in col else 1.0
    return df


def train_one_city(
    slug:          str,
    df_city:       pd.DataFrame,
    models_dir:    Path,
    epochs:        int  = 150,
    batch_size:    int  = 64,
    use_tcn:       bool = True,
    force:         bool = False,
    seed:          int  = 42,
) -> dict:
    """Full training pipeline for one city. Returns metrics dict."""
    from app.ml.models.city_hybrid   import CityHybridModel
    from app.ml.models.fusion        import FusionModel, FUSION_FEATURES
    from app.ml.calibration.isotonic import IsotonicCalibrator
    from app.ml.ood.detector         import OODDetector, OOD_FEATURES
    from app.ml.models.tcn           import make_sequences, TCN_SEQ_LEN
    from app.ml.preprocessing_v2     import WeatherDataPreprocessorV2

    np.random.seed(seed)
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
    except Exception:
        pass

    city_dir = models_dir / slug
    tmp_dir  = models_dir / f"{slug}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    logger.info("[%s] Starting training: %d rows", slug, len(df_city))
    t0 = time.time()

    # ---- Ensure required columns ----
    df_city = _ensure_month(df_city)
    df_city = _ensure_derived(df_city)
    df_city = df_city.sort_values("date") if "date" in df_city.columns else df_city
    df_city = df_city.reset_index(drop=True)
    n       = len(df_city)

    # ---- Temporal splits (no leakage) ----
    train_end = int(n * 0.80)
    val_end   = int(n * 0.90)
    # cal_set   = [val_end:]

    df_train = df_city.iloc[:train_end]
    df_val   = df_city.iloc[train_end:val_end]
    df_cal   = df_city.iloc[val_end:]

    logger.info("[%s] Splits: train=%d  val=%d  cal=%d", slug, len(df_train), len(df_val), len(df_cal))

    # ---- Weak labels ----
    y_train = df_train["weak_label"].values.astype(float) if "weak_label" in df_train.columns else None
    y_cal   = df_cal["weak_label"].values.astype(float)   if "weak_label" in df_cal.columns   else None

    # ---- Fit preprocessor on train only ----
    prep = WeatherDataPreprocessorV2()
    prep.fit(df_train)

    X_train_arr, feat_names = prep.transform(df_train)
    X_val_arr,   _          = prep.transform(df_val)
    X_cal_arr,   _          = prep.transform(df_cal)
    input_dim = X_train_arr.shape[1]
    logger.info("[%s] input_dim=%d  feature_names=%s...", slug, input_dim, feat_names[:4])

    # ---- AE + TCN training ----
    model = CityHybridModel(city=slug, input_dim=input_dim)
    model.build()
    ae_hist, tcn_hist = model.train(
        X_train     = X_train_arr,
        X_val       = X_val_arr,
        weak_labels = y_train,
        epochs      = epochs,
        batch_size  = batch_size,
    )

    ae_val_loss  = min(ae_hist.history["val_loss"])  if ae_hist  else None
    tcn_val_loss = min(tcn_hist.history["val_loss"]) if tcn_hist else None

    # ---- AE/TCN scores on calibration set ----
    ae_pcts, tcn_pcts, ae_vars, tcn_vars = [], [], [], []
    seq_len = TCN_SEQ_LEN

    for i in range(len(X_cal_arr)):
        x_vec = X_cal_arr[i]
        # Get last seq_len rows from X_train + X_val for context
        context_pool = np.vstack([X_train_arr, X_val_arr])
        if len(context_pool) >= seq_len:
            seq = context_pool[-seq_len:]
            if i > 0:
                seq = np.vstack([context_pool[-(seq_len-i):], X_cal_arr[:i]])[-seq_len:]
        else:
            seq = None
        raw = model.predict(x_vec, seq)
        ae_pcts.append(raw["ae_percentile"])
        tcn_pcts.append(raw["tcn_percentile"])
        ae_vars.append(raw["ae_variance"])
        tcn_vars.append(raw["tcn_variance"])

    # ---- Build fusion feature matrix from cal set ----
    cal_feats = []
    for i, (row_dict, ae_p, tcn_p, ae_v, tcn_v) in enumerate(
        zip(df_cal.to_dict("records"), ae_pcts, tcn_pcts, ae_vars, tcn_vars)
    ):
        d = {f: float(row_dict.get(f, 0.0) or 0.0) for f in FUSION_FEATURES
             if f not in ("ae_percentile","tcn_percentile","ae_variance","tcn_variance")}
        d["ae_percentile"]  = ae_p
        d["tcn_percentile"] = tcn_p
        d["ae_variance"]    = ae_v
        d["tcn_variance"]   = tcn_v
        cal_feats.append([d.get(f, 0.0) for f in FUSION_FEATURES])

    X_cal_fusion = np.array(cal_feats, dtype=float)

    # ---- FusionModel training (on cal set, non-abstained rows) ----
    lgbm_val_auc  = 0.5
    lgbm_val_brier = 0.25
    fusion         = FusionModel()
    metrics_dict   = {}

    if y_cal is not None:
        mask_non_abs = (y_cal != -1)
        if mask_non_abs.sum() >= 30:
            X_fus = X_cal_fusion[mask_non_abs]
            y_fus = y_cal[mask_non_abs]
            conf  = df_cal["weak_label_conf"].values[mask_non_abs] \
                    if "weak_label_conf" in df_cal.columns else None
            metrics_dict = fusion.train(X_fus, y_fus, sample_weight=conf)
            lgbm_val_auc   = metrics_dict.get("val_auc",   0.5)
            lgbm_val_brier = metrics_dict.get("val_brier", 0.25)
            logger.info("[%s] FusionModel AUC=%.3f Brier=%.4f", slug, lgbm_val_auc, lgbm_val_brier)
        else:
            logger.warning("[%s] Not enough non-abstained cal rows (%d) for FusionModel",
                           slug, mask_non_abs.sum())
    else:
        logger.warning("[%s] No weak_label column -- FusionModel not trained", slug)

    # ---- Metrics gate ----
    if not force and fusion.is_fitted:
        if lgbm_val_auc < METRICS_GATE_AUC:
            raise ValueError(
                f"[{slug}] METRICS GATE FAILED: val_auc={lgbm_val_auc:.3f} < {METRICS_GATE_AUC}. "
                "Use --force to skip."
            )

    # ---- IsotonicCalibrator ----
    cal = IsotonicCalibrator()
    cal_metrics = None
    if fusion.is_fitted and y_cal is not None and mask_non_abs.sum() >= 20:
        p_raw      = fusion.predict_proba(X_cal_fusion[mask_non_abs])
        cal_metrics = cal.fit(p_raw, y_cal[mask_non_abs])
        if not force and cal_metrics.ece_after > METRICS_GATE_ECE:
            logger.warning("[%s] ECE=%.4f > %.2f after calibration", slug,
                           cal_metrics.ece_after, METRICS_GATE_ECE)

        # Save cal data for future recalibration
        np.savez(tmp_dir / "cal_data.npz",
                 X_cal=X_cal_fusion[mask_non_abs],
                 y_cal=y_cal[mask_non_abs])

    # ---- OOD Detector ----
    ood = OODDetector()
    X_ood = np.array([
        [float(row.get(f, 0.0) or 0.0) for f in OOD_FEATURES]
        for row in df_train.to_dict("records")
    ], dtype=float)
    ood.fit(X_ood)

    # ---- Atomic save ----
    model.save(tmp_dir)
    fusion.save(tmp_dir / "lgbm_model.pkl")
    cal.save(tmp_dir / "calibrator.pkl")
    ood.save(tmp_dir / "ood_detector.pkl")
    prep.save(tmp_dir / "preprocessor_v2.joblib")

    # Write training metrics JSON
    elapsed     = time.time() - t0
    model_version = f"{slug}-v{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    summary = {
        "city_slug":           slug,
        "model_version":       model_version,
        "git_commit":          _git_commit(),
        "trained_at":          datetime.now(timezone.utc).isoformat(),
        "training_rows":       len(df_train),
        "val_rows":            len(df_val),
        "cal_rows":            len(df_cal),
        "input_dim":           input_dim,
        "ae_val_loss":         ae_val_loss,
        "tcn_val_loss":        tcn_val_loss,
        "lgbm_val_auc":        lgbm_val_auc,
        "lgbm_val_brier":      lgbm_val_brier,
        "calibration_ece":     cal_metrics.ece_after    if cal_metrics else None,
        "calibration_brier":   cal_metrics.brier_after  if cal_metrics else None,
        "duration_seconds":    round(elapsed, 1),
    }
    if "weak_label" in df_cal.columns:
        summary["positive_label_rate"] = float((y_cal == 1).mean()) if y_cal is not None else None

    (tmp_dir / "training_metrics.json").write_text(json.dumps(summary, indent=2))

    # Atomic swap: tmp -> final
    if city_dir.exists():
        archive = models_dir / f"{slug}.bak"
        if archive.exists():
            shutil.rmtree(archive)
        shutil.move(str(city_dir), str(archive))
    shutil.move(str(tmp_dir), str(city_dir))

    logger.info("[%s] Done in %.1fs | AUC=%.3f | ECE=%.4f | saved to %s",
                slug, elapsed,
                lgbm_val_auc,
                cal_metrics.ece_after if cal_metrics else float("nan"),
                city_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train HydroGuard-AI city model v3.2")
    parser.add_argument("--city",       default=None)
    parser.add_argument("--all",        action="store_true")
    parser.add_argument("--data",       required=True)
    parser.add_argument("--epochs",     type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--no-tcn",     action="store_true")
    parser.add_argument("--force",      action="store_true", help="Skip metrics gate")
    parser.add_argument("--seed",       type=int, default=42)
    parser.add_argument("--models-dir", default="backend/saved_models/city_models")
    parser.add_argument("--min-records",type=int, default=500)
    args = parser.parse_args()

    data_path  = Path(args.data)
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(data_path, low_memory=False)
    df = _ensure_month(df)
    df = _ensure_derived(df)

    # -------------------------------
    # Weak label generation (CRITICAL FIX)
    # -------------------------------
    import numpy as np

    def add_weak_labels(df):
        def label_city(g):
            prcp_q = g["prcp"].quantile(0.95)
            pressure_q = g["pressure"].quantile(0.15)
            humidity_q = g["humidity"].quantile(0.85)
            cloud_q = g["cloud_cover"].quantile(0.80)

            g["weak_label"] = (
                (g["prcp"] > prcp_q) |
                ((g["humidity"] > humidity_q) & (g["cloud_cover"] > cloud_q)) |
                (g["pressure"] < pressure_q)
            ).astype(np.int8)

            return g

        return df.groupby("city", group_keys=False).apply(label_city)

    df = add_weak_labels(df)

    print("Weak label distribution:")
    print(df["weak_label"].value_counts(normalize=True))

    if args.all:
        slugs = [_slug(c) for c in df["city"].dropna().unique()] if "city" in df.columns else []
    elif args.city:
        slugs = [_slug(args.city)]
    else:
        parser.error("Provide --city <name> or --all")
        return

    results = []
    for slug in sorted(slugs):
        if "city" in df.columns:
            df_city = df[df["city"].apply(_slug) == slug].copy()
        else:
            df_city = df.copy()

        if len(df_city) < args.min_records:
            print(f"SKIP {slug}: only {len(df_city)} rows (min={args.min_records})")
            continue

        try:
            summary = train_one_city(
                slug       = slug,
                df_city    = df_city,
                models_dir = models_dir,
                epochs     = args.epochs,
                batch_size = args.batch_size,
                use_tcn    = not args.no_tcn,
                force      = args.force,
                seed       = args.seed,
            )
            results.append({"city": slug, "status": "success", **summary})
        except Exception as exc:
            logger.error("[%s] Training failed: %s", slug, exc, exc_info=True)
            results.append({"city": slug, "status": "failed", "error": str(exc)})

    print("\n=== Training Summary ===")
    for r in results:
        status = r["status"]
        auc    = r.get("lgbm_val_auc", "N/A")
        ece    = r.get("calibration_ece", "N/A")
        print(f"  {r['city']}: {status}  AUC={auc}  ECE={ece}")


if __name__ == "__main__":
    main()
