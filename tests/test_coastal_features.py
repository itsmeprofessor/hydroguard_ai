from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND   = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND))

import os, types as _t
_d = _t.ModuleType("dotenv"); _d.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _d)
os.environ.setdefault("JWT_SECRET_KEY", "test-key")


COASTAL_NAMES = [
    "sst_anomaly", "sea_breeze_instability", "cyclone_proximity",
    "cyclone_season", "humidity_persistence", "coastal_moisture_flux",
    "urban_drainage_stress", "tidal_proxy", "coastal_pressure_grad",
]


def _make_karachi_df(n: int = 100) -> pd.DataFrame:
    """Minimal Karachi DataFrame with all required features including coastal."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "prcp":           rng.uniform(0, 50, n),
        "humidity":       rng.uniform(40, 95, n),
        "pressure":       rng.uniform(1000, 1020, n),
        "cloud_cover":    rng.uniform(0, 100, n),
        "tmin":           rng.uniform(15, 25, n),
        "tmax":           rng.uniform(28, 40, n),
        "tavg":           rng.uniform(22, 35, n),
        "temp_range":     rng.uniform(5, 15, n),
        "dew_point":      rng.uniform(18, 28, n),
        "wspd":           rng.uniform(0, 30, n),
        "tdew_spread":    rng.uniform(0, 10, n),
        "moisture_flux":  rng.uniform(0, 1, n),
        "month":          rng.integers(1, 13, n),
        "day":            rng.integers(1, 29, n),
        "pressure_delta_3h":    rng.uniform(-5, 5, n),
        "pressure_delta_6h":    rng.uniform(-8, 8, n),
        "humidity_delta_3h":    rng.uniform(-10, 10, n),
        "rain_accumulation_6h": rng.uniform(0, 100, n),
        "rain_rate_1h":          np.zeros(n),
        "rain_accumulation_3h":  np.zeros(n),
        "cloud_jump_3h":         np.zeros(n),
        "pressure_accel":        np.zeros(n),
        "humidity_accel":        np.zeros(n),
        "pressure_volatility_6d":np.zeros(n),
        "humidity_volatility_6d":np.zeros(n),
        "prcp_trend_6d":         np.zeros(n),
        "atm_instability":       np.zeros(n),
        "prcp_climo_pct":        np.ones(n),
        "humidity_climo_pct":    np.ones(n),
        "city_slug":    ["karachi"] * n,
        "season":       ["summer"]  * n,
        "vulnerability":         np.full(n, 0.85),
        "is_flash_flood_prone":  np.ones(n),
        "dayofweek":    rng.integers(0, 7, n),
        "is_weekend":   rng.integers(0, 2, n),
        "is_monsoon_month": rng.integers(0, 2, n),
    })
    for col in COASTAL_NAMES:
        df[col] = rng.uniform(0, 1, n)
    return df


def _make_islamabad_df(n: int = 100) -> pd.DataFrame:
    df = _make_karachi_df(n)
    df["city_slug"] = "islamabad"
    df["vulnerability"] = 0.75
    return df.drop(columns=COASTAL_NAMES)


class TestCoastalFeatureExtension:
    def test_coastal_features_computed_for_karachi(self):
        from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
        df = _make_karachi_df(100)
        assert all(c in df.columns for c in COASTAL_NAMES), \
            f"Missing: {[c for c in COASTAL_NAMES if c not in df.columns]}"
        prep = WeatherDataPreprocessorV2()
        prep.fit(df)
        X, feat_names = prep.transform(df)
        assert X.shape[0] == 100
        assert X.shape[1] > 35, f"Expected >35 dims with coastal, got {X.shape[1]}"

    def test_coastal_features_absent_for_islamabad(self):
        from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
        df = _make_islamabad_df(100)
        for col in COASTAL_NAMES:
            assert col not in df.columns
        prep = WeatherDataPreprocessorV2()
        prep.fit(df)
        X, _ = prep.transform(df)
        assert X.shape[0] == 100

    def test_preprocessor_accepts_44_dim(self):
        """Karachi with all 9 coastal features produces >= 44-dim output."""
        from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
        df = _make_karachi_df(100)
        prep = WeatherDataPreprocessorV2()
        prep.fit(df)
        X, feat_names = prep.transform(df)
        assert X.shape[1] >= 44, f"Expected >=44 dims, got {X.shape[1]}"

    def test_coastal_features_absent_in_nonkarachi_output(self):
        """Non-Karachi cities: no coastal features leak into output."""
        from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
        df = _make_islamabad_df(100)
        prep = WeatherDataPreprocessorV2()
        prep.fit(df)
        X, feat_names = prep.transform(df)
        coastal_in_feats = [f for f in feat_names if f in COASTAL_NAMES]
        assert len(coastal_in_feats) == 0, \
            f"Coastal features leaked into non-Karachi output: {coastal_in_feats}"

    def test_input_dim_matches_output_shape(self):
        """input_dim must equal X.shape[1] for both Karachi and non-Karachi."""
        from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2

        # Karachi
        df_k = _make_karachi_df(100)
        prep_k = WeatherDataPreprocessorV2()
        prep_k.fit(df_k)
        X_k, _ = prep_k.transform(df_k)
        assert prep_k.input_dim == X_k.shape[1], (
            f"Karachi: input_dim={prep_k.input_dim} != X.shape[1]={X_k.shape[1]}"
        )

        # Islamabad (no coastal columns)
        df_i = _make_islamabad_df(100)
        prep_i = WeatherDataPreprocessorV2()
        prep_i.fit(df_i)
        X_i, _ = prep_i.transform(df_i)
        assert prep_i.input_dim == X_i.shape[1], (
            f"Islamabad: input_dim={prep_i.input_dim} != X_i.shape[1]={X_i.shape[1]}"
        )
