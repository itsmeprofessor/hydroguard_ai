#!/usr/bin/env python3
"""
HydroGuard-AI — Threshold Tuning Script

Analyzes reconstruction error distribution and lets you interactively
set a new threshold multiplier (k) without retraining.

Usage:
    python scripts/tune_threshold.py
    python scripts/tune_threshold.py --k 2.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune anomaly detection threshold")
    parser.add_argument("--k",    type=float, default=None,
                        help="New k (threshold = mean + k * std)")
    parser.add_argument("--data", type=str,
                        default=str(BACKEND / "data/pakistan_weather_2000_2024.csv"))
    args = parser.parse_args()

    from app.services.anomaly_service import anomaly_service
    from utils.preprocessing import load_and_prepare_data

    if not anomaly_service.is_trained:
        print("ERROR: Model not trained. Run: python scripts/train.py first.")
        sys.exit(1)

    print("Loading data...")
    df      = load_and_prepare_data(args.data)
    X, _    = anomaly_service.preprocessor.transform(df)
    errors  = anomaly_service.autoencoder.get_reconstruction_error(X)

    mean_e  = anomaly_service.autoencoder.mean_error
    std_e   = anomaly_service.autoencoder.std_error
    cur_thr = anomaly_service.autoencoder.threshold
    cur_k   = (cur_thr - mean_e) / std_e

    print("\n" + "=" * 60)
    print("THRESHOLD TUNING ANALYSIS")
    print("=" * 60)
    print(f"  Mean error : {mean_e:.6f}")
    print(f"  Std error  : {std_e:.6f}")
    print(f"  Min / Max  : {np.min(errors):.6f} / {np.max(errors):.6f}")
    print(f"\n  Current threshold : {cur_thr:.6f}  (k={cur_k:.2f})")
    print(f"  Current anomaly % : {np.mean(errors > cur_thr) * 100:.2f}%")

    # Show a table for candidate k values
    print("\n  k       threshold    anomaly %")
    print("  " + "-" * 35)
    for k in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        thr = mean_e + k * std_e
        pct = np.mean(errors > thr) * 100
        marker = " ◄ current" if abs(k - cur_k) < 0.05 else ""
        print(f"  {k:.1f}    {thr:.6f}    {pct:.2f}%{marker}")

    if args.k is not None:
        new_thr = mean_e + args.k * std_e
        anomaly_service.autoencoder.threshold = new_thr
        anomaly_service.autoencoder.save(BACKEND / "saved_models" / "autoencoder_model")
        new_pct = np.mean(errors > new_thr) * 100
        print(f"\n✓ Threshold updated → {new_thr:.6f}  (k={args.k}, anomaly%={new_pct:.2f}%)")
        print("  Model re-saved with new threshold.")
    else:
        print("\nTo apply a new threshold without retraining, run:")
        print("  python scripts/tune_threshold.py --k <value>")


if __name__ == "__main__":
    main()
