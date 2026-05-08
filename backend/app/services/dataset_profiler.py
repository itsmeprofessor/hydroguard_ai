"""
HydroGuard-AI — Dynamic Dataset Profiler
=========================================
Automatically inspects any incoming weather CSV and builds a
machine-readable profile used by the rest of the pipeline.

The profiler produces a `dataset_profile.json` containing:
  - feature names and inferred types
  - temporal resolution (hourly / daily / sub-hourly)
  - geographic coverage (city list)
  - date range
  - data completeness per feature
  - feature statistics
  - suggested modeling configuration
  - dataset SHA256 fingerprint

No city names or feature lists are hardcoded here.  A new city in the
CSV, or a new column (e.g. "cape_index"), is automatically discovered.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
#  Feature classification heuristics
# ──────────────────────────────────────────────────────────

# Known meteorological feature groups with default weights
_KNOWN_FEATURE_META: Dict[str, Dict[str, Any]] = {
    # Primary flood indicators
    "prcp":             {"group": "primary",   "weight": 3.0, "unit": "mm"},
    "precipitation":    {"group": "primary",   "weight": 3.0, "unit": "mm"},
    "rain":             {"group": "primary",   "weight": 3.0, "unit": "mm"},
    "rainfall":         {"group": "primary",   "weight": 3.0, "unit": "mm"},
    "humidity":         {"group": "primary",   "weight": 2.0, "unit": "%"},
    "relative_humidity":{"group": "primary",   "weight": 2.0, "unit": "%"},
    "pressure":         {"group": "primary",   "weight": 2.0, "unit": "hPa"},
    "slp":              {"group": "primary",   "weight": 2.0, "unit": "hPa"},
    "cloud_cover":      {"group": "primary",   "weight": 1.5, "unit": "%"},
    "clouds":           {"group": "primary",   "weight": 1.5, "unit": "%"},
    # Secondary
    "dew_point":        {"group": "secondary", "weight": 1.0, "unit": "°C"},
    "dewpoint":         {"group": "secondary", "weight": 1.0, "unit": "°C"},
    "wspd":             {"group": "secondary", "weight": 1.0, "unit": "km/h"},
    "wind_speed":       {"group": "secondary", "weight": 1.0, "unit": "km/h"},
    "wdir":             {"group": "secondary", "weight": 0.5, "unit": "°"},
    "wind_direction":   {"group": "secondary", "weight": 0.5, "unit": "°"},
    "visibility":       {"group": "secondary", "weight": 0.8, "unit": "km"},
    # Context / temperature
    "tmin":             {"group": "context",   "weight": 0.1, "unit": "°C"},
    "tmax":             {"group": "context",   "weight": 0.1, "unit": "°C"},
    "tavg":             {"group": "context",   "weight": 0.1, "unit": "°C"},
    "temp_range":       {"group": "context",   "weight": 0.1, "unit": "°C"},
    "temperature":      {"group": "context",   "weight": 0.1, "unit": "°C"},
    # Advanced / optional
    "cape":             {"group": "advanced",  "weight": 2.5, "unit": "J/kg"},
    "cape_index":       {"group": "advanced",  "weight": 2.5, "unit": "J/kg"},
    "soil_moisture":    {"group": "advanced",  "weight": 2.0, "unit": "m³/m³"},
    "runoff":           {"group": "advanced",  "weight": 2.5, "unit": "mm"},
    "river_discharge":  {"group": "advanced",  "weight": 3.0, "unit": "m³/s"},
    "radar_reflectivity": {"group": "advanced","weight": 2.0, "unit": "dBZ"},
    "lightning_density": {"group": "advanced", "weight": 1.5, "unit": "/km²"},
    "upstream_rainfall": {"group": "advanced", "weight": 2.5, "unit": "mm"},
    "drainage_score":   {"group": "advanced",  "weight": 1.0, "unit": "score"},
    "elevation":        {"group": "spatial",   "weight": 1.0, "unit": "m"},
}

_CATEGORICAL_KEYWORDS = {"city", "region", "province", "season", "category", "label", "type"}
_DATE_KEYWORDS        = {"date", "datetime", "timestamp", "time", "dt"}
_TARGET_KEYWORDS      = {"label", "flood", "anomaly", "event", "is_flood", "is_anomaly"}


class DatasetProfile:
    """Structured profile of a weather dataset."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)

    def to_dict(self) -> Dict[str, Any]:
        return self._data.copy()

    def save(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)
        logger.info("Dataset profile saved → %s", path)

    @classmethod
    def load(cls, path: Path) -> "DatasetProfile":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    # ── Convenience getters ────────────────────────────────

    @property
    def numerical_features(self) -> List[str]:
        return [f for f, m in self._data.get("features", {}).items()
                if m.get("type") == "numerical"]

    @property
    def categorical_features(self) -> List[str]:
        return [f for f, m in self._data.get("features", {}).items()
                if m.get("type") == "categorical"]

    @property
    def temporal_features(self) -> List[str]:
        return self._data.get("derived_temporal_features", [])

    @property
    def feature_weights(self) -> Dict[str, float]:
        weights = {
            f: m.get("weight", 1.0)
            for f, m in self._data.get("features", {}).items()
            if m.get("type") == "numerical"
        }
        # Normalize
        total = sum(weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}

    @property
    def cities(self) -> List[str]:
        return self._data.get("cities", [])

    @property
    def city_column(self) -> Optional[str]:
        return self._data.get("city_column")

    @property
    def date_column(self) -> Optional[str]:
        return self._data.get("date_column")

    @property
    def has_target_labels(self) -> bool:
        return bool(self._data.get("target_column"))

    @property
    def target_column(self) -> Optional[str]:
        return self._data.get("target_column")

    @property
    def suggested_sequence_length(self) -> int:
        return self._data.get("modeling", {}).get("suggested_sequence_length", 7)

    @property
    def sha256(self) -> str:
        return self._data.get("sha256", "")


# ──────────────────────────────────────────────────────────
#  Profiler
# ──────────────────────────────────────────────────────────

class DatasetProfiler:
    """
    Inspect a CSV and produce a DatasetProfile describing its structure,
    geographic coverage, feature types, completeness, and recommended
    modeling configuration.
    """

    def profile(
        self,
        csv_path: Path,
        *,
        save_to: Optional[Path] = None,
        max_rows_for_stats: int = 50_000,
    ) -> DatasetProfile:
        """
        Read *csv_path* and build a DatasetProfile.

        Parameters
        ----------
        csv_path : Path to the CSV file.
        save_to  : If provided, write the profile JSON here.
        max_rows_for_stats : Cap rows used for heavy statistics (correlation, etc.).
        """
        csv_path = Path(csv_path)
        logger.info("Profiling dataset: %s", csv_path)

        # ── SHA256 fingerprint ─────────────────────────────
        sha256 = self._sha256(csv_path)

        # ── Load ───────────────────────────────────────────
        df = pd.read_csv(csv_path, low_memory=False)
        n_rows, n_cols = df.shape
        logger.info("  Loaded %d rows × %d columns", n_rows, n_cols)

        # ── Identify special columns ───────────────────────
        date_col   = self._find_date_column(df)
        city_col   = self._find_city_column(df)
        target_col = self._find_target_column(df)

        # ── Parse dates ────────────────────────────────────
        date_range, temporal_res = {}, "unknown"
        if date_col:
            try:
                dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
                date_range = {
                    "min": str(dates.min().date()),
                    "max": str(dates.max().date()),
                    "span_days": int((dates.max() - dates.min()).days),
                }
                temporal_res = self._infer_temporal_resolution(dates)
            except Exception as exc:
                logger.warning("  Could not parse dates: %s", exc)

        # ── Cities ─────────────────────────────────────────
        cities: List[str] = []
        if city_col:
            cities = sorted(
                df[city_col].dropna().astype(str).str.strip().unique().tolist()
            )
        city_stats: Dict[str, Any] = {}
        if city_col:
            city_counts = df[city_col].value_counts().to_dict()
            city_stats = {str(k): int(v) for k, v in city_counts.items()}

        # ── Feature classification ─────────────────────────
        skip_cols = {date_col, city_col, target_col} - {None}
        features  = self._classify_features(df, skip_cols)

        # ── Feature statistics ─────────────────────────────
        sample = df.head(max_rows_for_stats)
        feat_stats = self._compute_feature_stats(sample, features)

        # ── Completeness ───────────────────────────────────
        completeness = {
            col: round(1.0 - df[col].isna().mean(), 4)
            for col in df.columns
        }

        # ── Derived temporal features ──────────────────────
        derived_temporal = ["month", "day", "dayofweek", "is_weekend"]
        if temporal_res == "hourly":
            derived_temporal += ["hour"]

        # ── Suggested modeling configuration ──────────────
        n_num_features = sum(1 for m in features.values() if m["type"] == "numerical")
        modeling = self._suggest_modeling_config(
            n_rows, n_num_features, len(cities), temporal_res, bool(target_col)
        )

        profile_data: Dict[str, Any] = {
            "profiled_at":    datetime.utcnow().isoformat(),
            "sha256":         sha256,
            "file":           str(csv_path.name),
            "n_rows":         n_rows,
            "n_columns":      n_cols,
            "date_column":    date_col,
            "city_column":    city_col,
            "target_column":  target_col,
            "date_range":     date_range,
            "temporal_resolution": temporal_res,
            "cities":         cities,
            "city_count":     len(cities),
            "city_record_counts": city_stats,
            "features":       features,
            "feature_stats":  feat_stats,
            "completeness":   completeness,
            "derived_temporal_features": derived_temporal,
            "modeling":       modeling,
        }

        prof = DatasetProfile(profile_data)
        if save_to:
            prof.save(save_to)

        logger.info(
            "  Profile complete: %d cities · %d numerical features · resolution=%s",
            len(cities), n_num_features, temporal_res,
        )
        return prof

    # ── Private helpers ────────────────────────────────────

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _find_date_column(self, df: pd.DataFrame) -> Optional[str]:
        for col in df.columns:
            if col.lower() in _DATE_KEYWORDS:
                return col
        # Try columns that parse as datetime
        for col in df.columns:
            if df[col].dtype == object:
                sample = df[col].dropna().head(5)
                try:
                    pd.to_datetime(sample)
                    return col
                except Exception:
                    pass
        return None

    def _find_city_column(self, df: pd.DataFrame) -> Optional[str]:
        for col in df.columns:
            if col.lower() in _CATEGORICAL_KEYWORDS and col.lower() in {"city", "cities"}:
                return col
        for col in df.columns:
            if col.lower() == "city":
                return col
        return None

    def _find_target_column(self, df: pd.DataFrame) -> Optional[str]:
        for col in df.columns:
            if col.lower() in _TARGET_KEYWORDS:
                return col
        return None

    def _classify_features(
        self,
        df: pd.DataFrame,
        skip: set,
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for col in df.columns:
            if col in skip:
                continue
            col_lower = col.lower()

            # Determine type
            if df[col].dtype in (np.float64, np.float32, np.int64, np.int32, int, float):
                col_type = "numerical"
            elif col_lower in _CATEGORICAL_KEYWORDS or df[col].nunique() < 30:
                col_type = "categorical"
            else:
                col_type = "numerical"  # default unknown columns to numerical

            # Get known metadata
            meta = _KNOWN_FEATURE_META.get(col_lower, {})
            group  = meta.get("group", "unknown")
            weight = meta.get("weight", 1.0) if col_type == "numerical" else 0.0
            unit   = meta.get("unit", "")

            result[col] = {
                "type":    col_type,
                "group":   group,
                "weight":  weight,
                "unit":    unit,
                "missing": round(float(df[col].isna().mean()), 4),
            }
        return result

    def _compute_feature_stats(
        self, df: pd.DataFrame, features: Dict[str, Dict]
    ) -> Dict[str, Dict[str, float]]:
        stats = {}
        for col, meta in features.items():
            if meta["type"] != "numerical" or col not in df.columns:
                continue
            s = df[col].dropna()
            if len(s) == 0:
                continue
            stats[col] = {
                "mean":   round(float(s.mean()), 4),
                "std":    round(float(s.std()), 4),
                "min":    round(float(s.min()), 4),
                "max":    round(float(s.max()), 4),
                "p25":    round(float(s.quantile(0.25)), 4),
                "p50":    round(float(s.quantile(0.50)), 4),
                "p75":    round(float(s.quantile(0.75)), 4),
                "p99":    round(float(s.quantile(0.99)), 4),
            }
        return stats

    def _infer_temporal_resolution(self, dates: pd.Series) -> str:
        if len(dates) < 2:
            return "unknown"
        deltas = dates.sort_values().diff().dropna()
        median_hours = deltas.dt.total_seconds().median() / 3600
        if median_hours <= 1.1:
            return "hourly"
        elif median_hours <= 24.5:
            return "daily"
        else:
            return f"{int(median_hours / 24)}-daily"

    def _suggest_modeling_config(
        self,
        n_rows: int,
        n_features: int,
        n_cities: int,
        temporal_res: str,
        has_labels: bool,
    ) -> Dict[str, Any]:
        """Suggest sequence length, model type, and training config."""

        # Sequence length heuristic:
        # - hourly data → 24h (1 day) or 72h (3 days)
        # - daily data  → 7 or 14 depending on record count
        if temporal_res == "hourly":
            seq_len = 72 if n_rows > 5_000 else 24
        elif n_rows > 3_000:
            seq_len = 14
        else:
            seq_len = 7

        # Model type heuristic
        model_type = "ae_lstm_attention"  # default full hybrid
        if n_rows < 500:
            model_type = "ae_only"        # too little data for LSTM

        # Suggested epochs based on dataset size
        epochs = min(max(int(n_rows / 100), 50), 200)

        return {
            "suggested_sequence_length": seq_len,
            "suggested_model_type":      model_type,
            "suggested_epochs":          epochs,
            "can_train_lstm":            n_rows >= 500,
            "has_supervised_labels":     has_labels,
            "n_features":                n_features,
            "n_cities":                  n_cities,
            "notes": (
                "Supervised fusion recommended — use flood event labels "
                "to replace heuristic score mixing."
                if has_labels else
                "Unsupervised AE+LSTM reconstruction scoring. "
                "Add flood/cloudburst labels to enable supervised fusion."
            ),
        }


# ── Singleton ─────────────────────────────────────────────
dataset_profiler = DatasetProfiler()
