"""
HydroGuard-AI — Physics-Aware Weather Preprocessor v3.3
=========================================================
Upgrades WeatherDataPreprocessorV2 with real temporal dynamics and
physics-informed interaction features.

Breaking changes from v3.2:
  - NUMERICAL_V2 expanded from 22 → 28 features
    * Removed: pressure_climo_z (never populated from CSV)
    * Added: pressure_accel, humidity_accel, pressure_volatility_6d,
             humidity_volatility_6d, prcp_trend_6d, atm_instability
  - _ZERO_IMPUTE_FEATURES extended to cover new derived features
  - All rolling-delta features are now computed from REAL time-series diffs
    in scripts/train_city.py — zero-fill is the cold-start fallback only,
    not the training-time default

Zero-impute features:
  All temporal dynamics features default to 0.0 at cold start (first row in buffer
  before enough history accumulates). This is the correct physical interpretation:
  zero delta = no change detected yet. The model learned this distribution.

No LSTM anywhere in this module. No BiLSTM. Strictly causal.
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
    Physics-aware preprocessor for the v3.3 enriched feature set.

    Feature groups (in output order):
      NUMERICAL_V2   -- 28 features (raw + static derived + temporal dynamics
                        + physics interaction); StandardScale after imputation.
                        Rolling-delta features → 0.0 when history unavailable.
      TEMPORAL_V2    -- 5 features; MinMaxScale
      CATEGORICAL_V2 -- city_slug, season; one-hot (unseen → zero row)
      PASSTHROUGH_V2 -- vulnerability, is_flash_flood_prone; already 0-1 scaled

    Output: concatenated numpy array (float32), feature_names list.
    """

    # ── Feature registry ───────────────────────────────────────
    NUMERICAL_V2: List[str] = [
        # ── Raw meteorological (10) ──────────────────────────
        "prcp",        # Precipitation intensity (mm/day)
        "humidity",    # Relative humidity (%)
        "pressure",    # Surface/MSL pressure (hPa)
        "cloud_cover", # Cloud cover fraction (%)
        "tmin",        # Minimum temperature (°C)
        "tmax",        # Maximum temperature (°C)
        "tavg",        # Average temperature (°C)
        "temp_range",  # Diurnal range: tmax − tmin (°C)
        "dew_point",   # Dew point temperature (°C)
        "wspd",        # Wind speed (km/h)

        # ── Static physics interaction (2) ───────────────────
        "tdew_spread",   # Saturation deficit: tavg − dew_point (→ 0 = near saturation)
        "moisture_flux", # Moisture transport proxy: (humidity/100) × wspd

        # ── 1st-order temporal dynamics (7) ──────────────────
        # Real diffs computed from time-sorted series in train_city.py.
        # Names kept from v3.2 for model-dir backward compat.
        "pressure_delta_3h",     # Δpressure over 1 step (≈ 1 day for daily data)
        "pressure_delta_6h",     # Δpressure over 2 steps
        "humidity_delta_3h",     # Δhumidity over 1 step
        "rain_rate_1h",          # Δprcp clipped to 0 (positive = intensifying rain)
        "rain_accumulation_3h",  # Rolling 3-step precipitation sum
        "rain_accumulation_6h",  # Rolling 6-step precipitation sum
        "cloud_jump_3h",         # Δcloud_cover over 1 step (rapid cloud buildup)

        # ── 2nd-order dynamics & volatility (5) — NEW v3.3 ───
        "pressure_accel",        # ΔΔpressure: rate-of-change of pressure drop
        "humidity_accel",        # ΔΔhumidity: accelerating moisture buildup
        "pressure_volatility_6d",# 6-step rolling std of pressure (storm variability)
        "humidity_volatility_6d",# 6-step rolling std of humidity
        "prcp_trend_6d",         # 6-step linear slope of prcp (storm intensification)

        # ── Physics interaction proxy (1) — NEW v3.3 ─────────
        "atm_instability",       # moisture_flux × |pressure_delta| / tdew_spread
                                 # High = moist, rapidly falling pressure, near-saturated
                                 # → convective instability precursor

        # ── Climatological anomaly indicators (2) ────────────
        "prcp_climo_pct",     # prcp / climatological median (>1.0 = above normal)
        "humidity_climo_pct", # humidity / climatological median
        # NOTE: pressure_climo_z removed (was never populated from training CSV)
    ]

    # Features that get 0.0 when history is unavailable (cold start / first rows)
    # Physical interpretation: "no change detected yet" → correct for Δ features
    _ZERO_IMPUTE_FEATURES: frozenset = frozenset({
        "pressure_delta_3h", "pressure_delta_6h",
        "humidity_delta_3h", "rain_rate_1h",
        "rain_accumulation_3h", "rain_accumulation_6h", "cloud_jump_3h",
        # New v3.3 features also default to zero at cold start
        "pressure_accel", "humidity_accel",
        "pressure_volatility_6d", "humidity_volatility_6d",
        "prcp_trend_6d", "atm_instability",
    })

    TEMPORAL_V2:    List[str] = ["month", "day", "dayofweek", "is_weekend", "is_monsoon_month"]
    CATEGORICAL_V2: List[str] = ["city_slug", "season"]
    PASSTHROUGH_V2: List[str] = ["vulnerability", "is_flash_flood_prone"]

    def __init__(self) -> None:
        self._num_imputer    = SimpleImputer(strategy="median")
        self._num_scaler     = StandardScaler()
        self._temp_scaler    = MinMaxScaler()
        self._ohe_categories: Dict[str, List[str]] = {}
        self._feature_names:  List[str] = []
        self._is_fitted = False

    # ── Fit ─────────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> "WeatherDataPreprocessorV2":
        """Fit on training data only — no leakage from val/cal sets."""
        df = self._apply_zero_impute(df.copy())

        # Numerical: impute → StandardScale
        num_present = [f for f in self.NUMERICAL_V2 if f in df.columns]
        if num_present:
            arr = df[num_present].values.astype(float)
            self._num_imputer.fit(arr)
            self._num_scaler.fit(self._num_imputer.transform(arr))

        # Temporal: MinMaxScale
        temp_present = [f for f in self.TEMPORAL_V2 if f in df.columns]
        if temp_present:
            self._temp_scaler.fit(df[temp_present].fillna(0).values.astype(float))

        # Categorical: record unique categories per column
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

    # ── Transform ───────────────────────────────────────────────

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
        """Transform DataFrame → (float32 array, feature_names)."""
        if not self._is_fitted:
            raise RuntimeError("Preprocessor not fitted. Call fit() first.")

        df = self._apply_zero_impute(df.copy())
        parts: List[np.ndarray] = []
        names: List[str]        = []

        # ── Numerical ────────────────────────────────────────
        num_present = [f for f in self.NUMERICAL_V2 if f in df.columns]
        if num_present:
            arr     = df[num_present].values.astype(float)
            imputed = self._num_imputer.transform(arr)
            scaled  = self._num_scaler.transform(imputed)
            parts.append(scaled)
            names.extend(num_present)

        # ── Temporal ─────────────────────────────────────────
        temp_present = [f for f in self.TEMPORAL_V2 if f in df.columns]
        if temp_present:
            arr    = df[temp_present].fillna(0).values.astype(float)
            scaled = self._temp_scaler.transform(arr)
            parts.append(scaled)
            names.extend(temp_present)

        # ── Categorical OHE ───────────────────────────────────
        for col in self.CATEGORICAL_V2:
            cats = self._ohe_categories.get(col, [])
            if not cats:
                continue
            col_vals = (
                df[col].fillna("UNKNOWN").astype(str).values
                if col in df.columns
                else ["UNKNOWN"] * len(df)
            )
            ohe = np.zeros((len(df), len(cats)), dtype=float)
            for i, val in enumerate(col_vals):
                if val in cats:
                    ohe[i, cats.index(val)] = 1.0
                else:
                    logger.warning(
                        "OHE: unseen category '%s' in '%s' → zero row", val, col
                    )
            parts.append(ohe)
            names.extend([f"{col}_{c}" for c in cats])

        # ── Passthrough ───────────────────────────────────────
        for col in self.PASSTHROUGH_V2:
            if col in df.columns:
                vals = df[col].fillna(0.0).values.astype(float).reshape(-1, 1)
                parts.append(vals)
                names.append(col)

        if not parts:
            raise ValueError("No features found in DataFrame — check column names.")

        out = np.hstack(parts).astype(np.float32)
        return out, names

    # ── Single-dict transform ────────────────────────────────────

    def transform_dict(self, feature_dict: Dict) -> Tuple[np.ndarray, List[str]]:
        """Transform a single feature dict → (1D float32 array, feature_names)."""
        arr, names = self.transform(pd.DataFrame([feature_dict]))
        return arr[0], names

    # ── Save / Load ──────────────────────────────────────────────

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

    # ── Private helpers ──────────────────────────────────────────

    def _apply_zero_impute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill temporal-dynamics features with 0.0 before median imputation.
        0.0 = physically correct cold-start value (no change detected yet).
        """
        for col in self._ZERO_IMPUTE_FEATURES:
            if col in df.columns:
                df[col] = df[col].fillna(0.0)
            else:
                df[col] = 0.0
        return df

    @property
    def input_dim(self) -> int:
        """Total output feature dimension (after all encoding)."""
        if not self._is_fitted:
            return 0
        ohe_total = sum(len(cats) for cats in self._ohe_categories.values())
        return (
            len(self.NUMERICAL_V2)
            + len(self.TEMPORAL_V2)
            + ohe_total
            + len(self.PASSTHROUGH_V2)
        )
