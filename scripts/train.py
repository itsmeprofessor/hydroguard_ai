#!/usr/bin/env python3
"""
HydroGuard-AI — Offline Model Training Script

Usage:
    python scripts/train.py --data backend/data/pakistan_weather_2000_2024.csv
    python scripts/train.py --data backend/data/... --use-lstm --visualize
    python scripts/train.py --epochs 200 -b 32 --seed 42
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# Resolve backend/ on sys.path so all absolute imports work
BACKEND = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import DATA_DIR, MODELS_DIR, ModelConfig
from app.services.anomaly_service import AnomalyDetectionService
from utils.preprocessing import load_and_prepare_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)


def _find_data(explicit: str | None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            logger.error(f"Data file not found: {explicit}")
            sys.exit(1)
        return explicit

    candidates = [
        DATA_DIR / "pakistan_weather_2000_2024.csv",
        Path("backend/data/pakistan_weather_2000_2024.csv"),
        Path("pakistan_weather_2000_2024.csv"),
    ]
    for p in candidates:
        if Path(p).exists():
            return str(p)

    logger.error("No dataset found. Use --data <path>")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGuard-AI Model Training")
    parser.add_argument("--data",       "-d", type=str, default=None)
    parser.add_argument("--epochs",     "-e", type=int, default=ModelConfig.EPOCHS)
    parser.add_argument("--batch-size", "-b", type=int, default=ModelConfig.BATCH_SIZE)
    parser.add_argument("--use-lstm",   action="store_true", default=False)
    parser.add_argument("--visualize",  "-v", action="store_true")
    parser.add_argument("--output-dir", "-o", type=str, default=str(MODELS_DIR))
    parser.add_argument("--seed",       type=int, default=42)
    args = parser.parse_args()

    set_seed(args.seed)
    data_path = _find_data(args.data)

    logger.info("=" * 60)
    logger.info("HydroGuard-AI — Training Started")
    logger.info("=" * 60)
    logger.info(f"Dataset   : {data_path}")
    logger.info(f"Epochs    : {args.epochs}  | Batch: {args.batch_size}  | LSTM: {args.use_lstm}")
    logger.info(f"Output    : {args.output_dir}")
    logger.info("=" * 60)

    start_time = datetime.now()
    try:
        service = AnomalyDetectionService()
        result  = service.train(
            data_path  = data_path,
            use_lstm   = args.use_lstm,
            epochs     = args.epochs,
            batch_size = args.batch_size,
            save_model = True,
        )
        elapsed  = (datetime.now() - start_time).total_seconds()
        ae_meta  = result["training_metadata"]["autoencoder"]
        ae_stats = result["training_metadata"]["anomaly_stats"]

        logger.info("=" * 60)
        logger.info(f"Wall time        : {elapsed:.1f}s")
        logger.info(f"Train/Val samples: {result['training_metadata']['train_samples']} / {result['training_metadata']['validation_samples']}")
        logger.info(f"AE loss (train)  : {ae_meta['final_loss']:.6f}")
        logger.info(f"AE loss (val)    : {ae_meta['final_val_loss']:.6f}")
        logger.info(f"AE threshold     : {ae_meta['threshold']:.6f}")
        logger.info(f"Anomaly rate     : {ae_stats['anomaly_percentage']:.2f}%")

        if result["training_metadata"].get("lstm"):
            m = result["training_metadata"]["lstm"]
            logger.info(f"LSTM loss (train) : {m['final_loss']:.6f}")
            logger.info(f"LSTM loss (val)   : {m['final_val_loss']:.6f}")

        if args.visualize:
            try:
                from utils.visualization import create_analysis_report
                df   = load_and_prepare_data(data_path)
                X, _ = service.preprocessor.transform(df)
                errors = service.autoencoder.get_reconstruction_error(X)
                feat_names = (
                    list(service.preprocessor.numerical_features)
                    + list(service.preprocessor.temporal_features)
                )[:X.shape[1]]
                feature_importance = service.autoencoder.get_feature_importance(X, feat_names)
                vis_dir = Path(args.output_dir) / "visualizations"
                create_analysis_report(
                    output_dir        = str(vis_dir),
                    history           = result["ae_history"],
                    errors            = errors,
                    threshold         = service.autoencoder.threshold,
                    df                = df,
                    feature_importance = feature_importance,
                )
                logger.info(f"Visualizations → {vis_dir}")
            except Exception as e:
                logger.warning(f"Visualization failed (non-fatal): {e}")

        logger.info(f"Models saved → {args.output_dir}")
        logger.info("=" * 60)

    except Exception as exc:
        logger.error(f"Training failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
