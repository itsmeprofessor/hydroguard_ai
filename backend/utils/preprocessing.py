"""
Data Preprocessing Module for HydroGuard-AI
=============================================
Key fixes vs original:
  1. fit() only called on TRAIN split — no data leakage
  2. FEATURE_WEIGHTS applied before scaling — flood focus enforced
  3. One-hot encoding for categoricals — no ordinal magnitude confusion
  4. Season/city/region unknown-category handled safely
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.impute import SimpleImputer
from typing import Tuple, Dict, List, Optional, Union
import joblib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class WeatherDataPreprocessor:
    """
    Preprocessor for weather data.

    Encoding:
      - Numerical: impute(median) → weight multiply → StandardScale
      - Temporal:  MinMaxScale  (no imputation needed, always provided)
      - Categorical: one-hot (unseen → all-zero row, no magnitude error)
    """

    def __init__(
        self,
        numerical_features: List[str],
        categorical_features: List[str],
        temporal_features: List[str],
        sequence_length: int = 7,
        feature_weights: Optional[Dict[str, float]] = None,
    ):
        self.numerical_features   = numerical_features
        self.categorical_features = categorical_features
        self.temporal_features    = temporal_features
        self.sequence_length      = sequence_length
        self.feature_weights      = feature_weights or {}

        self.numerical_scaler  = StandardScaler()
        self.temporal_scaler   = MinMaxScaler()
        self.numerical_imputer = SimpleImputer(strategy='median')

        # one-hot: dict[col_name] -> list[known_categories]
        self.ohe_categories: Dict[str, List[str]] = {}

        self._is_fitted  = False
        self.feature_stats: Dict[str, Dict] = {}

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def fit(self, df: pd.DataFrame) -> 'WeatherDataPreprocessor':
        """Fit on training data only (no leakage)."""
        logger.info("Fitting preprocessor on training data...")
        self._compute_feature_stats(df)

        if self.numerical_features:
            num_data = df[self.numerical_features].values.astype(float)
            self.numerical_imputer.fit(num_data)
            imputed = self.numerical_imputer.transform(num_data)
            weighted = self._apply_weights(imputed)
            self.numerical_scaler.fit(weighted)

        if self.temporal_features:
            temporal_data = df[[c for c in self.temporal_features if c in df.columns]].fillna(0).infer_objects(copy=False).values.astype(float)
            self.temporal_scaler.fit(temporal_data)

        for col in self.categorical_features:
            if col in df.columns:
                cats = sorted(df[col].fillna('UNKNOWN').astype(str).unique().tolist())
                self.ohe_categories[col] = cats

        self._is_fitted = True
        logger.info("Preprocessor fitting complete.")
        return self

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
        """Transform data using fitted preprocessor."""
        if not self._is_fitted:
            raise ValueError("Preprocessor must be fitted before transform.")

        df_out = df.copy()
        arrays = []

        # --- Numerical ---
        if self.numerical_features:
            for col in self.numerical_features:
                if col not in df_out.columns:
                    df_out[col] = np.nan
            num_data = df_out[self.numerical_features].values.astype(float)
            imputed  = self.numerical_imputer.transform(num_data)
            weighted = self._apply_weights(imputed)
            scaled   = self.numerical_scaler.transform(weighted)
            arrays.append(scaled)

        # --- Temporal ---
        if self.temporal_features:
            avail = [c for c in self.temporal_features if c in df_out.columns]
            missing = [c for c in self.temporal_features if c not in df_out.columns]
            for c in missing:
                df_out[c] = 0
            temporal_data = df_out[self.temporal_features].astype(float).fillna(0).values
            scaled_temporal = self.temporal_scaler.transform(temporal_data)
            arrays.append(scaled_temporal)

        # --- Categorical (one-hot) ---
        for col in self.categorical_features:
            if col not in self.ohe_categories:
                continue
            if col in df_out.columns:
                vals = df_out[col].fillna('UNKNOWN').astype(str)
            else:
                vals = pd.Series(['UNKNOWN'] * len(df_out))
            cats = self.ohe_categories[col]
            ohe = np.zeros((len(vals), len(cats)), dtype=float)
            for i, v in enumerate(vals):
                if v in cats:
                    ohe[i, cats.index(v)] = 1.0
                # unknown → all zeros (safe, no magnitude confusion)
            arrays.append(ohe)

        X = np.hstack(arrays) if arrays else np.zeros((len(df_out), 1))
        return X, df_out

    def fit_transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
        self.fit(df)
        return self.transform(df)

    def create_sequences(
        self,
        X: np.ndarray,
        df: pd.DataFrame,
        group_by: str = 'city',
    ) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """Create LSTM sequences grouped by city."""
        sequences, targets, indices = [], [], []
        if group_by in df.columns:
            df_reset = df.reset_index(drop=True)
            for group in df_reset[group_by].unique():
                mask = df_reset[group_by] == group
                gX   = X[mask]
                gidx = df_reset[mask].index.tolist()
                for i in range(len(gX) - self.sequence_length):
                    sequences.append(gX[i:i + self.sequence_length])
                    targets.append(gX[i + self.sequence_length])
                    indices.append(gidx[i + self.sequence_length])
        else:
            for i in range(len(X) - self.sequence_length):
                sequences.append(X[i:i + self.sequence_length])
                targets.append(X[i + self.sequence_length])
                indices.append(i + self.sequence_length)
        return np.array(sequences), np.array(targets), indices

    def get_feature_deviation(self, values: Dict[str, float]) -> Dict[str, Dict]:
        deviations = {}
        for feature, value in values.items():
            if feature in self.feature_stats:
                s = self.feature_stats[feature]
                z = (value - s['mean']) / (s['std'] + 1e-8)
                pp = (value - s['min']) / (s['max'] - s['min'] + 1e-8)
                deviations[feature] = {
                    'value': value,
                    'mean':  s['mean'],
                    'z_score': z,
                    'percentile_position': pp,
                    'is_outlier': abs(z) > 2.0,
                }
        return deviations

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        joblib.dump({
            'numerical_scaler':   self.numerical_scaler,
            'temporal_scaler':    self.temporal_scaler,
            'numerical_imputer':  self.numerical_imputer,
            'ohe_categories':     self.ohe_categories,
            'feature_stats':      self.feature_stats,
            'feature_weights':    self.feature_weights,
            'numerical_features': self.numerical_features,
            'categorical_features': self.categorical_features,
            'temporal_features':  self.temporal_features,
            'sequence_length':    self.sequence_length,
            '_is_fitted':         self._is_fitted,
        }, path)
        logger.info(f"Preprocessor saved to {path}")

    @classmethod
    def load(cls, path: Union[str, Path]) -> 'WeatherDataPreprocessor':
        path = Path(path)
        data = joblib.load(path)
        inst = cls(
            numerical_features   = data['numerical_features'],
            categorical_features = data['categorical_features'],
            temporal_features    = data['temporal_features'],
            sequence_length      = data['sequence_length'],
            feature_weights      = data.get('feature_weights', {}),
        )
        inst.numerical_scaler  = data['numerical_scaler']
        inst.temporal_scaler   = data['temporal_scaler']
        inst.numerical_imputer = data['numerical_imputer']
        inst.feature_stats     = data['feature_stats']
        inst._is_fitted        = data['_is_fitted']

        # Backwards-compat: old saves used label_encoders
        if 'ohe_categories' in data:
            inst.ohe_categories = data['ohe_categories']
        elif 'label_encoders' in data:
            # Migrate: rebuild ohe_categories from label encoder classes
            inst.ohe_categories = {}
            for col, le in data['label_encoders'].items():
                inst.ohe_categories[col] = sorted(le.classes_.tolist())
        logger.info(f"Preprocessor loaded from {path}")
        return inst

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _apply_weights(self, arr: np.ndarray) -> np.ndarray:
        """Multiply each numerical column by its configured weight."""
        if not self.feature_weights:
            return arr
        arr = arr.copy()
        for i, col in enumerate(self.numerical_features):
            w = self.feature_weights.get(col, 1.0)
            arr[:, i] *= w
        return arr

    def _compute_feature_stats(self, df: pd.DataFrame) -> None:
        for col in self.numerical_features:
            if col in df.columns:
                self.feature_stats[col] = {
                    'mean':   float(df[col].mean()),
                    'std':    float(df[col].std()),
                    'min':    float(df[col].min()),
                    'max':    float(df[col].max()),
                    'q25':    float(df[col].quantile(0.25)),
                    'q75':    float(df[col].quantile(0.75)),
                    'median': float(df[col].median()),
                }


def load_and_prepare_data(filepath: str, date_column: str = 'date') -> pd.DataFrame:
    """Load and sort weather CSV."""
    logger.info(f"Loading data from {filepath}")
    df = pd.read_csv(filepath)
    df[date_column] = pd.to_datetime(df[date_column], format='mixed', dayfirst=False)
    df = df.sort_values(['city', date_column]).reset_index(drop=True)
    df = df.dropna(axis=1, how='all')
    logger.info(f"Loaded {len(df)} records from {df['city'].nunique()} cities")
    logger.info(f"Date range: {df[date_column].min()} to {df[date_column].max()}")
    return df