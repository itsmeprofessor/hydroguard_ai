"""
HydroGuard-AI -- Generate Weak Labels from Historical CSV
==========================================================
Runs LabelEngine on the master weather CSV to produce weak labels
for LightGBM FusionModel training.

Output: new CSV with added columns:
  weak_label, weak_label_conf, event_type, rule_votes

Usage:
    python scripts/generate_labels.py \\
        --data backend/data/pakistan_weather_2000_2024.csv \\
        --climatology backend/data/climatology/ \\
        --output backend/data/pakistan_weather_labeled.csv \\
        [--city islamabad]
        [--no-db]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


def _slug(city: str) -> str:
    return city.strip().lower().replace(" ", "_").replace("-", "_")


def _ensure_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns needed by labeling rules if not present."""
    if "month" not in df.columns and "date" in df.columns:
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.month
    if "tavg" in df.columns and "dew_point" in df.columns:
        if "tdew_spread" not in df.columns:
            df["tdew_spread"] = df["tavg"] - df["dew_point"]
    if "humidity" in df.columns and "wspd" in df.columns:
        if "moisture_flux" not in df.columns:
            df["moisture_flux"] = (df["humidity"] / 100.0) * df["wspd"]
    # prcp_climo_pct defaults to 1.0 if climatology files unavailable
    if "prcp_climo_pct" not in df.columns:
        df["prcp_climo_pct"] = 1.0
    # Rolling deltas -- default to 0.0 (no history in batch mode)
    for col in ["pressure_delta_3h", "pressure_delta_6h", "humidity_delta_3h"]:
        if col not in df.columns:
            df[col] = 0.0
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weak supervision labels")
    parser.add_argument("--data",        required=True)
    parser.add_argument("--climatology", default=None,
                        help="Directory containing <city_slug>.json climatology files")
    parser.add_argument("--output",      required=True)
    parser.add_argument("--city",        default=None,
                        help="Single city slug (default: all cities in CSV)")
    parser.add_argument("--no-db",       action="store_true",
                        help="Skip writing label_events to DB")
    args = parser.parse_args()

    data_path = Path(args.data)
    out_path  = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {data_path} ...")
    df = pd.read_csv(data_path, low_memory=False)
    print(f"  Rows: {len(df):,}")

    # Setup climatology store
    climatology = None
    if args.climatology and Path(args.climatology).exists():
        import types, os
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda *a, **k: None
        sys.modules.setdefault("dotenv", dotenv)
        os.environ.setdefault("JWT_SECRET_KEY", "generate-labels-script")
        try:
            from app.services.climatology_store import ClimatologyStore
            climatology = ClimatologyStore(Path(args.climatology))
            print(f"  Climatology: {args.climatology}")
        except Exception as exc:
            print(f"  WARNING: climatology load failed: {exc}")

    # Filter to one city if specified
    if args.city:
        mask = df["city"].apply(_slug) == _slug(args.city)
        df   = df[mask].copy()
        print(f"  Filtered to '{args.city}': {len(df):,} rows")

    # Derived features
    df = _ensure_derived_features(df)

    # Import labeling engine
    import types as _types, os as _os
    dotenv_mod = _types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *a, **k: None
    sys.modules.setdefault("dotenv", dotenv_mod)
    _os.environ.setdefault("JWT_SECRET_KEY", "generate-labels-script")

    from app.ml.labeling.engine import LabelEngine

    all_results = []

    cities = [_slug(c) for c in df["city"].dropna().unique()] if "city" in df.columns else ["unknown"]
    for slug in cities:
        mask     = df["city"].apply(_slug) == slug if "city" in df.columns else pd.Series([True] * len(df))
        df_city  = df[mask].copy()
        engine   = LabelEngine(climatology=climatology)
        df_city  = engine.label_dataframe(df_city, city_slug=slug)
        all_results.append(df_city)

        pos = (df_city["weak_label"] == 1).sum()
        neg = (df_city["weak_label"] == 0).sum()
        abs_ = (df_city["weak_label"] == -1).sum()
        print(f"  {slug}: {len(df_city):,} rows | pos={pos} ({100*pos/len(df_city):.1f}%) "
              f"neg={neg} ({100*neg/len(df_city):.1f}%) abs={abs_} ({100*abs_/len(df_city):.1f}%)")

    labeled_df = pd.concat(all_results, ignore_index=True)

    # Summary
    total = len(labeled_df)
    pos   = (labeled_df["weak_label"] == 1).sum()
    neg   = (labeled_df["weak_label"] == 0).sum()
    abs_  = (labeled_df["weak_label"] == -1).sum()
    print(f"\nTotal: {total:,}")
    print(f"  Positive:  {pos:,} ({100*pos/total:.1f}%)")
    print(f"  Negative:  {neg:,} ({100*neg/total:.1f}%)")
    print(f"  Abstained: {abs_:,} ({100*abs_/total:.1f}%)")

    labeled_df.to_csv(out_path, index=False)
    print(f"\nLabeled CSV written to {out_path}")


if __name__ == "__main__":
    main()
