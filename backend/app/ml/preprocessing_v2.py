"""
HydroGuard-AI — WeatherDataPreprocessorV2
===========================================
Replaces utils/preprocessing.py for city-model training and inference.
Operates on the full EnrichedFeatures feature set (22 numerical + temporal + categorical).

Changes from v1:
  - Includes all Stage 2 derived features (tdew_spread, moisture_flux, deltas, climo)
  - Rolling delta None values imputed to 0.0 (not median -- zero means "no change")
  - Unseen OHE categories -> all-zero row + WARNING log (unchanged)
  - save/load via joblib (unchanged)
  - Returns (np.ndarray, list[str]) -- feature names alongside values
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import MinMaxScaler, StandardScaler

logger = logging.getLogger(__name__)


class WeatherDataPreprocessorV2:
    """
    Preprocessor for the v2 enriched feature set.

    Feature groups:
      NUMERICAL_V2   -- 22 features (raw + derived); StandardScale after median imputation
                        EXCEPT rolling deltas which are imputed to 0.0 (not median)
      TEMPORAL_V2    -- 5 features; MinMaxScale
      CATEGORICAL_V2 -- city_slug, season; one-hot (unseen -> zero row)
      PASSTHROUGH_V2 -- vulnerability, is_flash_flood_prone; already 0-1 scaled

    Output: concatenated numpy array, feature_names list.
    """

    NUMERICAL_V2 = [
        # Raw
        "prcp", "humidity", "pressure", "cloud_cover",
        "tmin", "tmax", "tavg", "temp_range", "dew_point", "wspd",
        # Static derived
        "tdew_spread", "moisture_flux",
        # Rolling deltas (imputed to 0.0 when None)
        "pressure_delta_3h", "pressure_delta_6h",
        "humidity_delta_3h", "rain_rate_1h",
        "rain_accumulation_3h", "rain_accumulation_6h", "cloud_jump_3h",
        # Climatological
        "prcp_climo_pct", "pressure_climo_z", "humidity_climo_pct",
    ]

    # Rolling features -- impute with 0.0 (not median)
    _ZERO_IMPUTE_FEATURES = {
        "pressure_delta_3h", "pressure_delta_6h", "humidity_delta_3h",
        "rain_rate_1h", "rain_accumulation_3h", "rain_accumulation_6h",
        "cloud_jump_3h",
    }

    TEMPORAL_V2    = ["month", "day", "dayofweek", "is_weekend", "is_monsoon_month"]
    CATEGORICAL_V2 = ["city_slug", "season"]
    PASSTHROUGH_V2 = ["vulnerability", "is_flash_flood_prone"]

    def __init__(self):
        self._num_imputer   = SimpleImputer(strategy="median")
        self._num_scaler    = StandardScaler()
        self._temp_scaler   = MinMaxScaler()
        self._ohe_categories: Dict[str, List[str]] = {}
        self._feature_names: List[str] = []
        self._is_fitted = False

    # ── Fit ─────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> "WeatherDataPreprocessorV2":
        """Fit on training data only (no leakage)."""
        df = self._fill_zero_impute(df.copy())

        # Numerical: median imputation -> StandardScale
        num_present = [f for f in self.NUMERICAL_V2 if f in df.columns]
        if num_present:
            num_data = df[num_present].values.astype(float)
            self._num_imputer.fit(num_data)
            imputed  = self._num_imputer.transform(num_data)
            self._num_scaler.fit(imputed)

        # Temporal: MinMaxScale
        temp_present = [f for f in self.TEMPORAL_V2 if f in df.columns]
        if temp_present:
            temp_data = df[temp_present].fillna(0).values.astype(float)
            self._temp_scaler.fit(temp_data)

        # Categorical: fit OHE categories
        for col in self.CATEGORICAL_V2:
            if col in df.columns:
                cats = sorted(df[col].fillna("UNKNOWN").astype(str).unique().tolist())
                self._ohe_categories[col] = cats

        self._is_fitted = True
        logger.info(
            "WeatherDataPreprocessorV2 fitted on %d rows, %d numerical features",
            len(df), len(num_present),
        )
        return self

    # ── Transform ────────────────────────────────────────────

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
        """Transform input DataFrame -> (array, feature_names)."""
        if not self._is_fitted:
            raise RuntimeError("Preprocessor not fitted. Call fit() first.")

        df = self._fill_zero_impute(df.copy())
        parts: List[np.ndarray] = []
        names: List[str]        = []

        # Numerical
        num_present = [f for f in self.NUMERICAL_V2 if f in df.columns]
        if num_present:
            num_data = df[num_present].values.astype(float)
            imputed  = self._num_imputer.transform(num_data)
            scaled   = self._num_scaler.transform(imputed)
            parts.append(scaled)
            names.extend(num_present)

        # Temporal
        temp_present = [f for f in self.TEMPORAL_V2 if f in df.columns]
        if temp_present:
            temp_data = df[temp_present].fillna(0).values.astype(float)
            scaled    = self._temp_scaler.transform(temp_data)
            parts.append(scaled)
            names.extend(temp_present)

        # Categorical OHE
        for col in self.CATEGORICAL_V2:
            cats = self._ohe_categories.get(col, [])
            if not cats:
                continue
            col_vals = df[col].fillna("UNKNOWN").astype(str).values if col in df.columns \
                       else ["UNKNOWN"] * len(df)
            ohe = np.zeros((len(df), len(cats)), dtype=float)
            for i, val in enumerate(col_vals):
                if val in cats:
                    ohe[i, cats.index(val)] = 1.0
                else:
                    logger.warning("OHE: unseen category '%s' in column '%s' -> zero row", val, col)
            parts.append(ohe)
            names.extend([f"{col}_{c}" for c in cats])

        # Passthrough
        for col in self.PASSTHROUGH_V2:
            if col in df.columns:
                vals = df[col].fillna(0.0).values.astype(float).reshape(-1, 1)
                parts.append(vals)
                names.append(col)

        if not parts:
            raise ValueError("No features found in DataFrame.")

        out = np.hstack(parts)
        return out, names

    # ── Convenience single-row transform ────────────────────

    def transform_dict(
        self, feature_dict: Dict
    ) -> Tuple[np.ndarray, List[str]]:
        """Transform a single feature dict -> (1D array, feature_names)."""
        df = pd.DataFrame([feature_dict])
        arr, names = self.transform(df)
        return arr[0], names

    # ── Save / Load ─────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("WeatherDataPreprocessorV2 saved to %s", path)

    @classmethod
    def load(cls, path: Path) -> "WeatherDataPreprocessorV2":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected WeatherDataPreprocessorV2, got {type(obj)}")
        logger.info("WeatherDataPreprocessorV2 loaded from %s", path)
        return obj

    # ── Private ──────────────────────────────────────────────

    def _fill_zero_impute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill rolling delta features with 0.0 before the general median imputer."""
        for col in self._ZERO_IMPUTE_FEATURES:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
            else:
                df[col] = 0.0
        return df

    @property
    def input_dim(self) -> int:
        """Total number of output features (after all encoding)."""
        if not self._is_fitted:
            return 0
        # Numerical + Temporal + OHE + Passthrough
        ohe_total = sum(len(cats) for cats in self._ohe_categories.values())
        return (
            len([f for f in self.NUMERICAL_V2])
            + len(self.TEMPORAL_V2)
            + ohe_total
            + len(self.PASSTHROUGH_V2)
        )
