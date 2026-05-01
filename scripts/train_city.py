#!/usr/bin/env python3
"""
HydroGuard-AI — City-Specific Hybrid Model Training (DYNAMIC)
==============================================================
Trains the AE + LSTM + Attention pipeline for one or all cities.

Cities are discovered from the dataset CSV's `city` column at runtime — no
hardcoded list. Adding a new city to the CSV → `--all` will pick it up.

Usage:
    # Train every city found in the dataset
    python scripts/train_city.py --all --data backend/data/pakistan_weather_2000_2024.csv

    # Single city by name
    python scripts/train_city.py --city Islamabad --epochs 200

    # Reduced epochs / smaller batch / no LSTM (AE only)
    python scripts/train_city.py --city Karachi -e 80 -b 32 --no-lstm

    # List cities in the dataset (no training)
    python scripts/train_city.py --list-cities --data path/to/data.csv

Output
------
saved_models/city_models/<slug>/
    ├── autoencoder/         # Keras SavedModel
    ├── lstm_attention/      # Keras SavedModel (only if enough sequences)
    ├── ae_calibration.npy   # [mean, std, p99] from training reconstruction errors
    └── preprocessor.joblib  # WeatherDataPreprocessor fitted on this city's data

Notes
-----
- Each city's rows are filtered, then **sorted by `date`** to guarantee
  chronological order — required for the LSTM rolling 7-day windows and a
  leak-free chronological train/val split.
- Cities with fewer than --min-records rows are skipped (default 200).
- After every successful train, the in-memory CityModelService is hot-swapped.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path
from typing import List, Optional, Set

import joblib
import numpy as np
import pandas as pd

# Resolve backend/ for imports
BACKEND = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import DATA_DIR, MODELS_DIR, ModelConfig
from app.ml.models.city_hybrid import CityHybridModel
from app.services.city_model_service import (
    _slug, _display_name, _meta_for,
    city_model_service,
)
from utils.preprocessing import WeatherDataPreprocessor, load_and_prepare_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

CITY_MODELS_DIR = MODELS_DIR / "city_models"


# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

def _set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
    except Exception:
        pass


def _find_data(explicit: Optional[str]) -> str:
    """Locate the master CSV (falls back to common paths)."""
    if explicit:
        if not Path(explicit).exists():
            logger.error("Data file not found: %s", explicit)
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
    # Last-ditch: any CSV in DATA_DIR
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.csv"):
            return str(f)
    logger.error("No dataset found. Use --data <path>")
    sys.exit(1)


def _discover_cities(data_path: str) -> Set[str]:
    """Read the unique city slugs from the dataset's `city` column."""
    df = pd.read_csv(data_path, usecols=["city"], low_memory=True)
    return {
        _slug(c) for c in df["city"].dropna().astype(str).str.strip().unique()
        if c.strip()
    }


def _filter_city(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
    """Filter to one city + sort chronologically to keep LSTM windows valid."""
    if "city" not in df.columns:
        raise ValueError("Dataset is missing a 'city' column.")
    mask = df["city"].astype(str).str.strip().str.lower() == city_name.strip().lower()
    out = df.loc[mask].copy()
    if "date" in out.columns:
        out = out.sort_values("date").reset_index(drop=True)
    return out


# ──────────────────────────────────────────────────────────
#  Train one city
# ──────────────────────────────────────────────────────────

def train_one_city(
    city_slug: str,
    *,
    data_path: Optional[str] = None,
    epochs: int = 150,
    batch_size: int = 64,
    val_split: float = 0.2,
    use_lstm: bool = True,
    seed: int = 42,
    min_records: int = 200,
) -> bool:
    """Train a CityHybridModel for the given slug. Returns True on success."""
    _set_seed(seed)

    path = _find_data(data_path)

    # Discover whether this city is in the dataset (for nice error messages)
    available = _discover_cities(path)
    if city_slug not in available:
        logger.error(
            "City '%s' not found in dataset. Available cities: %s",
            city_slug, sorted(available),
        )
        return False

    # Use canonical name from metadata if known, otherwise title-case the slug
    meta      = _meta_for(city_slug)
    city_name = meta["name"]
    out_dir   = CITY_MODELS_DIR / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load + filter ──────────────────────────────────────────
    logger.info("[%s] Loading dataset: %s", city_slug, path)
    # load_and_prepare_data returns a single DataFrame
    loaded = load_and_prepare_data(path)
    df_full = loaded[0] if isinstance(loaded, tuple) else loaded  # tolerate either signature

    # Sometimes load_and_prepare_data lowercases or alters city — match by slug
    df_full = df_full.copy()
    df_full["_city_slug"] = (
        df_full["city"].astype(str).str.strip().str.lower().str.replace(" ", "_")
    )
    df = df_full.loc[df_full["_city_slug"] == city_slug].copy()
    df = df.drop(columns=["_city_slug"])
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    if len(df) < min_records:
        logger.warning("[%s] Only %d records (min %d) — skipping",
                       city_slug, len(df), min_records)
        return False
    logger.info("[%s] %d records loaded for training (city: %s)",
                city_slug, len(df), city_name)

    # ── Preprocess ────────────────────────────────────────────
    # Build feature lists from ModelConfig, filtered to columns present in df
    available_numerical   = [f for f in ModelConfig.NUMERICAL_FEATURES   if f in df.columns]
    available_categorical = [f for f in ModelConfig.CATEGORICAL_FEATURES if f in df.columns]
    available_temporal    = [f for f in ModelConfig.TEMPORAL_FEATURES    if f in df.columns]

    pre = WeatherDataPreprocessor(
        numerical_features   = available_numerical,
        categorical_features = available_categorical,
        temporal_features    = available_temporal,
        sequence_length      = ModelConfig.SEQUENCE_LENGTH,
        feature_weights      = ModelConfig.FEATURE_WEIGHTS,
    )

    # Chronological train/val split BEFORE fitting (no leakage)
    n_train = int(len(df) * (1 - val_split))
    df_train = df.iloc[:n_train].copy()
    df_val   = df.iloc[n_train:].copy()

    # fit_transform / transform return (X_array, df_processed)
    X_train, _ = pre.fit_transform(df_train)
    X_val,   _ = pre.transform(df_val)

    logger.info("[%s] Train shape: %s · Val shape: %s",
                city_slug, X_train.shape, X_val.shape)

    # ── Build + train ─────────────────────────────────────────
    model = CityHybridModel(city=city_name, input_dim=X_train.shape[1])
    model.build()

    if not use_lstm:
        logger.info("[%s] LSTM disabled — training AE only", city_slug)
        model._lstm = None  # type: ignore[attr-defined]

    ae_hist, lstm_hist = model.train(
        X_train, X_val,
        epochs=epochs, batch_size=batch_size,
    )

    # ── Save ──────────────────────────────────────────────────
    model.save(out_dir)
    joblib.dump(pre, out_dir / "preprocessor.joblib")
    logger.info("[%s] Saved → %s", city_slug, out_dir)

    # Hot-swap into the in-memory registry (also triggers refresh)
    city_model_service.register_model(city_slug, model, preprocessor=pre)
    return True


# ──────────────────────────────────────────────────────────
#  Train every city in the dataset
# ──────────────────────────────────────────────────────────

def train_all_cities(
    *,
    data_path: Optional[str] = None,
    epochs: int = 150,
    batch_size: int = 64,
    use_lstm: bool = True,
    seed: int = 42,
    min_records: int = 200,
) -> List[str]:
    """Train models for every city found in the dataset's `city` column."""
    path = _find_data(data_path)
    cities = sorted(_discover_cities(path))
    if not cities:
        logger.error("No cities discovered in %s", path)
        return []

    logger.info("Discovered %d cities in dataset: %s", len(cities), cities)
    trained: List[str] = []

    for slug in cities:
        logger.info("\n" + "=" * 60)
        logger.info("Training city: %s", slug)
        logger.info("=" * 60)
        ok = train_one_city(
            city_slug=slug,
            data_path=path,
            epochs=epochs, batch_size=batch_size,
            use_lstm=use_lstm, seed=seed,
            min_records=min_records,
        )
        if ok:
            trained.append(slug)

    # Final refresh so the service reflects all newly-trained models
    city_model_service.refresh_registry()
    return trained


# ──────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HydroGuard-AI city-specific model training")
    parser.add_argument("--city",        "-c", type=str,            help="City name or slug (e.g. Islamabad)")
    parser.add_argument("--all",         "-a", action="store_true", help="Train every city in the dataset")
    parser.add_argument("--list-cities", action="store_true",       help="Print cities found in the dataset and exit")
    parser.add_argument("--data",        "-d", type=str, default=None)
    parser.add_argument("--epochs",      "-e", type=int, default=150)
    parser.add_argument("--batch-size",  "-b", type=int, default=64)
    parser.add_argument("--no-lstm",     action="store_true",       help="Train AE only (skip LSTM+Attention)")
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--min-records", type=int, default=200,     help="Minimum rows required per city")
    args = parser.parse_args()

    if args.list_cities:
        path = _find_data(args.data)
        cities = sorted(_discover_cities(path))
        print(f"\nCities discovered in {path}:")
        for c in cities:
            print(f"  · {c}  ({_display_name(c)})")
        print(f"\nTotal: {len(cities)} cities\n")
        return

    if not (args.city or args.all):
        parser.error("Specify --city <name>, --all, or --list-cities")

    if args.all:
        trained = train_all_cities(
            data_path=args.data,
            epochs=args.epochs, batch_size=args.batch_size,
            use_lstm=not args.no_lstm,
            seed=args.seed, min_records=args.min_records,
        )
        path = _find_data(args.data)
        all_cities = sorted(_discover_cities(path))
        logger.info("\n" + "=" * 60)
        logger.info("Training complete · %d/%d cities trained",
                    len(trained), len(all_cities))
        logger.info("Trained: %s", ", ".join(trained))
        if len(trained) < len(all_cities):
            skipped = [s for s in all_cities if s not in trained]
            logger.warning("Skipped (insufficient data): %s", ", ".join(skipped))
    else:
        slug = _slug(args.city)
        ok = train_one_city(
            city_slug=slug,
            data_path=args.data,
            epochs=args.epochs, batch_size=args.batch_size,
            use_lstm=not args.no_lstm,
            seed=args.seed, min_records=args.min_records,
        )
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
