"""
fix_cal_data.py — one-time migration to correct cal_data.npz key names.

Background
----------
train_city.py previously saved cal_data.npz with keys X_cal / y_cal.
AlertTierClassifier.from_cal_data() expects y_true / y_score (raw probabilities).
This script regenerates the files in-place using the already-saved FusionModel
(lgbm_model.pkl) to recompute raw probabilities from the saved feature matrix.

Usage
-----
    python scripts/fix_cal_data.py                  # all cities
    python scripts/fix_cal_data.py --city karachi   # single city
    python scripts/fix_cal_data.py --dry-run        # show what would change, don't write
"""
from __future__ import annotations

import argparse
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "backend" / "saved_models" / "city_models"

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def fix_city(slug: str, dry_run: bool) -> bool:
    city_dir = MODELS_DIR / slug
    cal_path = city_dir / "cal_data.npz"
    lgbm_path = city_dir / "lgbm_model.pkl"

    if not cal_path.exists():
        logger.warning("[%s] cal_data.npz not found — skipping", slug)
        return False
    if not lgbm_path.exists():
        logger.warning("[%s] lgbm_model.pkl not found — skipping", slug)
        return False

    import numpy as np
    import joblib

    data = np.load(cal_path)
    keys = list(data.files)

    if "y_true" in keys and "y_score" in keys:
        logger.info("[%s] already has correct keys (y_true, y_score) — no action needed", slug)
        return True

    if "X_cal" not in keys or "y_cal" not in keys:
        logger.error("[%s] unexpected keys %s — skipping", slug, keys)
        return False

    X_cal = data["X_cal"]   # (N, 16) fusion feature matrix
    y_cal = data["y_cal"]   # (N,) binary labels

    fusion = joblib.load(lgbm_path)

    p_raw = fusion.predict_proba(X_cal)   # (N,) uncalibrated P(event)

    logger.info("[%s] X_cal %s → p_raw %s, y_cal %s", slug, X_cal.shape, p_raw.shape, y_cal.shape)

    if dry_run:
        logger.info("[%s] DRY-RUN: would save y_true/y_score (not written)", slug)
        return True

    bak_path = cal_path.with_suffix(".npz.bak")
    import shutil
    shutil.copy2(cal_path, bak_path)
    logger.info("[%s] backed up original → %s", slug, bak_path.name)

    np.savez(cal_path, y_true=y_cal, y_score=p_raw)
    logger.info("[%s] cal_data.npz updated with y_true / y_score keys", slug)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix cal_data.npz key names for AlertTierClassifier")
    parser.add_argument("--city", help="Single city slug (default: all cities)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    if args.city:
        slugs = [args.city]
    else:
        slugs = sorted(p.name for p in MODELS_DIR.iterdir() if p.is_dir() and not p.name.endswith(".bak"))

    if not slugs:
        logger.error("No city model directories found under %s", MODELS_DIR)
        sys.exit(1)

    ok = 0
    fail = 0
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
