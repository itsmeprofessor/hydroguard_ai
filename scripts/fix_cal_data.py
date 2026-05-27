"""
fix_cal_data.py — migrate cal_data.npz to use calibrated probabilities as y_score.

Background
----------
AlertTierClassifier.from_cal_data() derives advisory/alert thresholds from the
PR curve of (y_true, y_score). At inference, predict_v2() applies those thresholds
to the IsotonicCalibrator output (p_calib). These must be in the same probability
domain, or the recall≥85%/precision≥65% guarantees are meaningless.

Two historical migrations were needed:
  Pass 1 (dab46e6): renamed X_cal/y_cal → y_true/y_score (raw fusion probs)
  Pass 2 (this script): replaces raw y_score with calibrated probabilities

Source of truth: .bak files (created by Pass 1) carry the original X_cal/y_cal.
This script loads X_cal → fusion.predict_proba → calibrator.transform → y_score.
Idempotent: running multiple times produces the same result.

Usage
-----
    python scripts/fix_cal_data.py                  # all cities
    python scripts/fix_cal_data.py --city karachi   # single city
    python scripts/fix_cal_data.py --dry-run        # show what would change
"""
from __future__ import annotations

import argparse
import shutil
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "backend" / "saved_models" / "city_models"
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def fix_city(slug: str, dry_run: bool) -> bool:
    city_dir = MODELS_DIR / slug
    cal_path  = city_dir / "cal_data.npz"
    bak_path  = city_dir / "cal_data.npz.bak"
    lgbm_path = city_dir / "lgbm_model.pkl"
    cal_pkl   = city_dir / "calibrator.pkl"

    if not lgbm_path.exists():
        logger.warning("[%s] lgbm_model.pkl not found — skipping", slug)
        return False
    if not cal_pkl.exists():
        logger.warning("[%s] calibrator.pkl not found — skipping", slug)
        return False

    import numpy as np
    import joblib

    # Locate source data (X_cal feature matrix + y_cal labels).
    # Prefer the .bak file created by Pass 1 (contains original X_cal/y_cal).
    src = None
    if bak_path.exists():
        src_data = np.load(bak_path)
        if "X_cal" in src_data.files and "y_cal" in src_data.files:
            src = ("bak", src_data["X_cal"], src_data["y_cal"])
    if src is None and cal_path.exists():
        src_data = np.load(cal_path)
        if "X_cal" in src_data.files and "y_cal" in src_data.files:
            src = ("cal", src_data["X_cal"], src_data["y_cal"])

    if src is None:
        logger.error("[%s] no usable X_cal/y_cal source found — skipping", slug)
        return False

    source_label, X_cal, y_cal = src

    fusion = joblib.load(lgbm_path)

    from app.ml.calibration.isotonic import IsotonicCalibrator
    calibrator = IsotonicCalibrator.load(cal_pkl)

    p_raw   = fusion.predict_proba(X_cal)       # (N,) uncalibrated
    p_calib = calibrator.transform(p_raw)        # (N,) calibrated — same domain as predict_v2

    logger.info(
        "[%s] source=%s  N=%d  p_calib range [%.4f, %.4f]  mean=%.4f",
        slug, source_label, len(y_cal), p_calib.min(), p_calib.max(), p_calib.mean(),
    )

    if dry_run:
        logger.info("[%s] DRY-RUN: would write calibrated y_true/y_score (not written)", slug)
        return True

    if not bak_path.exists():
        shutil.copy2(cal_path, bak_path)
        logger.info("[%s] backed up → %s", slug, bak_path.name)

    np.savez(cal_path, y_true=y_cal, y_score=p_calib)
    logger.info("[%s] cal_data.npz updated with calibrated y_score", slug)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate cal_data.npz y_score from raw to calibrated probabilities"
    )
    parser.add_argument("--city", help="Single city slug (default: all cities)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.city:
        slugs = [args.city]
    else:
        slugs = sorted(
            p.name for p in MODELS_DIR.iterdir()
            if p.is_dir() and not p.name.endswith(".bak")
        )

    if not slugs:
        logger.error("No city model directories found under %s", MODELS_DIR)
        sys.exit(1)

    ok = fail = 0
    for slug in slugs:
        if fix_city(slug, args.dry_run):
            ok += 1
        else:
            fail += 1

    logger.info("Done: %d ok, %d failed", ok, fail)
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
