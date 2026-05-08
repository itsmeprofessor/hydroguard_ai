"""
HydroGuard-AI — Compute Per-City Climatology Baselines
=======================================================
Reads the master weather CSV and writes per-city per-month quantile
JSON files to backend/data/climatology/<city_slug>.json.

These files are consumed by ClimatologyStore at runtime to compute
prcp_climo_pct, pressure_climo_z, humidity_climo_pct features.

Usage:
    python scripts/compute_climatology.py \\
        --data backend/data/pakistan_weather_2000_2024.csv \\
        --output backend/data/climatology/ \\
        [--cities all | islamabad,lahore,...]

Run this once after obtaining new training data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

FEATURES_TO_COMPUTE = [
    "prcp", "pressure", "humidity", "cloud_cover",
    "tmax", "tmin", "tavg", "dew_point", "wspd",
]


def _slug(city: str) -> str:
    return city.strip().lower().replace(" ", "_").replace("-", "_")


def compute_city_climatology(
    df_city: pd.DataFrame,
    city_slug: str,
) -> dict:
    """Compute per-month quantiles for one city's data."""
    monthly: dict = {}

    for month in range(1, 13):
        df_m = df_city[df_city["month"] == month]
        if len(df_m) < 10:
            # Not enough data for this month — skip; store will use defaults
            continue
        monthly[str(month)] = {}
        for feat in FEATURES_TO_COMPUTE:
            if feat not in df_m.columns:
                continue
            vals = df_m[feat].dropna().values.astype(float)
            if len(vals) < 5:
                continue
            monthly[str(month)][feat] = {
                "q50":   float(np.percentile(vals, 50)),
                "q90":   float(np.percentile(vals, 90)),
                "q99":   float(np.percentile(vals, 99)),
                "mu":    float(np.mean(vals)),
                "sigma": float(max(np.std(vals), 0.01)),
            }

    return {
        "city_slug":          city_slug,
        "computed_from_rows": int(len(df_city)),
        "monthly":            monthly,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute per-city climatology baselines")
    parser.add_argument("--data",   required=True, help="Path to master weather CSV")
    parser.add_argument("--output", required=True, help="Output directory for JSON files")
    parser.add_argument(
        "--cities", default="all",
        help="Comma-separated city slugs or 'all'",
    )
    args = parser.parse_args()

    data_path   = Path(args.data)
    output_dir  = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {data_path} ...")
    df = pd.read_csv(data_path, low_memory=False)
    print(f"  Rows: {len(df):,}  Columns: {list(df.columns)[:8]}...")

    # Ensure month column
    if "month" not in df.columns:
        if "date" in df.columns:
            df["date"]  = pd.to_datetime(df["date"], errors="coerce")
            df["month"] = df["date"].dt.month
        else:
            print("ERROR: CSV has no 'month' or 'date' column.", file=sys.stderr)
            sys.exit(1)

    # City column
    if "city" not in df.columns:
        print("ERROR: CSV has no 'city' column.", file=sys.stderr)
        sys.exit(1)

    all_slugs = {_slug(c) for c in df["city"].dropna().unique()}

    if args.cities.lower() == "all":
        target_slugs = all_slugs
    else:
        target_slugs = {s.strip() for s in args.cities.split(",")}
        missing = target_slugs - all_slugs
        if missing:
            print(f"WARNING: cities not in data: {missing}")

    print(f"Computing climatology for {len(target_slugs)} cities ...\n")

    for slug in sorted(target_slugs):
        mask    = df["city"].apply(_slug) == slug
        df_city = df[mask].copy()
        if len(df_city) < 30:
            print(f"  SKIP {slug}: only {len(df_city)} rows")
            continue

        clim = compute_city_climatology(df_city, slug)
        out  = output_dir / f"{slug}.json"
        out.write_text(json.dumps(clim, indent=2), encoding="utf-8")
        print(f"  {slug}: {len(df_city):,} rows -> {len(clim['monthly'])} months -> {out}")

    print(f"\nDone. JSON files written to {output_dir}")


if __name__ == "__main__":
    main()
