"""
HydroGuard-AI -- Standalone City Recalibration
================================================
Re-fits IsotonicCalibrator for a city without retraining AE/TCN.
Used when ECE degrades (CalibrationMonitor triggers this).

Usage:
    python scripts/calibrate_city.py --city islamabad
    python scripts/calibrate_city.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def recalibrate_city(slug: str, models_dir: Path) -> dict:
    """
    Load existing FusionModel + prediction history, refit IsotonicCalibrator.
    Returns metrics dict.
    """
    import types, os
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules.setdefault("dotenv", dotenv)
    os.environ.setdefault("JWT_SECRET_KEY", "calibrate-script")

    city_dir = models_dir / slug
    if not city_dir.exists():
        print(f"  SKIP {slug}: no model directory found")
        return {}

    lgbm_path = city_dir / "lgbm_model.pkl"
    if not lgbm_path.exists():
        print(f"  SKIP {slug}: no lgbm_model.pkl found")
        return {}

    try:
        from app.ml.models.fusion import FusionModel
        from app.ml.calibration.isotonic import IsotonicCalibrator
        import numpy as np

        fusion = FusionModel.load(lgbm_path)

        # Load recent labeled predictions from DB for recalibration
        # For now, generate synthetic calibration data from saved history
        cal_path = city_dir / "cal_data.npz"
        if not cal_path.exists():
            print(f"  SKIP {slug}: no calibration data (cal_data.npz) found")
            return {}

        cal_data = np.load(cal_path)
        X_cal    = cal_data["X_cal"]
        y_cal    = cal_data["y_cal"]

        if len(X_cal) < 20:
            print(f"  SKIP {slug}: only {len(X_cal)} calibration samples")
            return {}

        # Re-predict and recalibrate
        p_raw    = fusion.predict_proba(X_cal)
        cal      = IsotonicCalibrator()
        metrics  = cal.fit(p_raw, y_cal)
        cal.save(city_dir / "calibrator.pkl")

        print(f"  {slug}: Brier {metrics.brier_before:.4f} -> {metrics.brier_after:.4f}  "
              f"ECE {metrics.ece_before:.4f} -> {metrics.ece_after:.4f}")
        return {
            "city_slug":      slug,
            "brier_before":   metrics.brier_before,
            "brier_after":    metrics.brier_after,
            "ece_before":     metrics.ece_before,
            "ece_after":      metrics.ece_after,
        }
    except Exception as exc:
        print(f"  ERROR {slug}: {exc}")
        return {"error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalibrate city model(s)")
    parser.add_argument("--city",       default=None)
    parser.add_argument("--all",        action="store_true")
    parser.add_argument("--models-dir", default="backend/saved_models/city_models")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)

    if args.all:
        slugs = [p.name for p in models_dir.iterdir() if p.is_dir()]
    elif args.city:
        slugs = [args.city.strip().lower().replace(" ", "_")]
    else:
        parser.error("Provide --city <slug> or --all")
        return

    print(f"Recalibrating {len(slugs)} city model(s) ...")
    for slug in sorted(slugs):
        recalibrate_city(slug, models_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
