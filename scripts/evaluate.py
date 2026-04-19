#!/usr/bin/env python3
"""
HydroGuard-AI — Model Evaluation Script

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --data backend/data/pakistan_weather_2000_2024.csv --output backend/evaluation_results
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trained anomaly detection model")
    parser.add_argument("--data",   "-d", type=str, default=str(BACKEND / "data/pakistan_weather_2000_2024.csv"))
    parser.add_argument("--output", "-o", type=str, default=str(BACKEND / "evaluation_results"))
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    from app.services.anomaly_service import anomaly_service
    from utils.preprocessing import load_and_prepare_data

    if not anomaly_service.is_trained:
        logger.error("Model not trained. Run: python scripts/train.py --data <csv>")
        sys.exit(1)

    logger.info(f"Loading data from {args.data}")
    df = load_and_prepare_data(args.data)
    X, df_processed = anomaly_service.preprocessor.transform(df)

    logger.info("Running inference on full dataset...")
    errors     = anomaly_service.autoencoder.get_reconstruction_error(X)
    is_anomaly = errors > anomaly_service.autoencoder.threshold
    risk_levels = [anomaly_service.autoencoder.get_risk_level(e) for e in errors]

    df["reconstruction_error"] = errors
    df["is_anomaly"]           = is_anomaly
    df["risk_level"]           = risk_levels

    # ── Basic stats ──────────────────────────────────────────
    basic_stats = {
        "total_samples":      int(len(df)),
        "total_anomalies":    int(np.sum(is_anomaly)),
        "anomaly_percentage": round(float(np.mean(is_anomaly) * 100), 2),
        "threshold":          float(anomaly_service.autoencoder.threshold),
        "mean_error":         float(np.mean(errors)),
        "std_error":          float(np.std(errors)),
        "min_error":          float(np.min(errors)),
        "max_error":          float(np.max(errors)),
        "median_error":       float(np.median(errors)),
    }
    logger.info(f"Anomaly rate: {basic_stats['anomaly_percentage']:.2f}%  ({basic_stats['total_anomalies']}/{basic_stats['total_samples']})")

    # ── By city ──────────────────────────────────────────────
    city_analysis: dict = {}
    if "city" in df.columns:
        for city, group in df.groupby("city"):
            mask = group["is_anomaly"]
            city_analysis[city] = {
                "total":    len(group),
                "anomalies":int(mask.sum()),
                "rate":     round(float(mask.mean() * 100), 2),
                "mean_error": round(float(group["reconstruction_error"].mean()), 6),
            }

    # ── By risk level ────────────────────────────────────────
    risk_dist = df[is_anomaly]["risk_level"].value_counts().to_dict()

    # ── Monthly trend ────────────────────────────────────────
    monthly: dict = {}
    if "month" in df.columns:
        for month, group in df.groupby("month"):
            monthly[int(month)] = round(float(group["is_anomaly"].mean() * 100), 2)

    # ── Export anomaly CSV ───────────────────────────────────
    anomaly_df = df[is_anomaly].copy()
    out_csv    = output_dir / "detected_anomalies.csv"
    anomaly_df.to_csv(out_csv, index=False)

    # ── Export JSON report ───────────────────────────────────
    report = {
        "timestamp":    datetime.now().isoformat(),
        "data_file":    args.data,
        "model_info":   anomaly_service.get_model_info(),
        "basic_stats":  basic_stats,
        "city_analysis": city_analysis,
        "risk_distribution": risk_dist,
        "monthly_anomaly_rate": monthly,
    }
    out_json = output_dir / "evaluation_report.json"
    out_json.write_text(json.dumps(report, indent=2, default=str))

    logger.info(f"Anomaly CSV   → {out_csv}")
    logger.info(f"Eval report   → {out_json}")
    logger.info("Evaluation complete.")


if __name__ == "__main__":
    main()
