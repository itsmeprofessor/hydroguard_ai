"""
HydroGuard-AI — OOD (Out-of-Distribution) Detector
=====================================================
Mahalanobis distance-based detector that identifies weather observations
that fall outside the trained climatological manifold.

If an input is OOD, the system returns a safe "Unknown" response
instead of a potentially nonsensical high-confidence prediction.

This guards against:
  - WeatherAPI returning corrupt data (e.g., pressure = 0)
  - Sensor malfunctions or API outages returning edge values
  - City-season combinations never seen during training

Features used (13 features — excludes sparse rolling deltas):
    prcp, humidity, pressure, cloud_cover,
    tmin, tmax, dew_point, wspd,
    tdew_spread, moisture_flux,
    prcp_climo_pct, pressure_climo_z, humidity_climo_pct

Threshold: 99.5th percentile of training Mahalanobis distances.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

import joblib
import numpy as np

logger = logging.getLogger(__name__)


OOD_FEATURES = [
    "prcp", "humidity", "pressure", "cloud_cover",
    "tmin", "tmax", "dew_point", "wspd",
    "tdew_spread", "moisture_flux",
    "prcp_climo_pct", "pressure_climo_z", "humidity_climo_pct",
]


class OODDetector:
    """
    Mahalanobis distance OOD detector.

    fit(X_train, threshold_pct=99.5):
        Computes the mean vector and inverse covariance matrix from
        training data. Sets distance threshold at the given percentile
        of training distances.

    mahalanobis_distance(x):
        Computes the Mahalanobis distance of one 13-dim observation.

    is_ood(x):
        Returns True if the distance exceeds the training threshold.

    ood_response(city_slug, distance):
        Returns a safe standardised response dict for OOD inputs.
    """

    def __init__(self):
        self._mean:      Optional[np.ndarray] = None
        self._inv_cov:   Optional[np.ndarray] = None
        self._threshold: float                = float("inf")
        self._n_training: int                 = 0
        self._is_fitted: bool                 = False

    # ── Fit ─────────────────────────────────────────────────

    def fit(
        self,
        X_train: np.ndarray,
        threshold_pct: float = 99.5,
    ) -> "OODDetector":
        """
        Fit the OOD detector on training features.

        Parameters
        ----------
        X_train      : (N, 13) array of OOD_FEATURES values, pre-extracted from
                       training EnrichedFeatures.
        threshold_pct: percentile of training distances to use as threshold.
                       99.5 means 0.5% of training data will be flagged as OOD.
        """
        X = np.asarray(X_train, dtype=float)
        X = X[np.all(np.isfinite(X), axis=1)]   # remove rows with NaN/Inf

        if len(X) < 10:
            logger.warning("OODDetector.fit: < 10 finite samples — detector disabled.")
            self._threshold = float("inf")
            self._is_fitted = True
            return self

        self._mean      = np.mean(X, axis=0)
        cov             = np.cov(X, rowvar=False)

        # Regularise: add small diagonal to ensure invertibility
        cov += np.eye(cov.shape[0]) * 1e-6
        try:
            self._inv_cov = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            self._inv_cov = np.linalg.pinv(cov)

        # Compute training distances to set threshold
        train_distances = self._batch_mahalanobis(X)
        self._threshold  = float(np.percentile(train_distances, threshold_pct))
        self._n_training = len(X)
        self._is_fitted  = True

        logger.info(
            "OODDetector fitted: n=%d  threshold_pct=%.1f  threshold=%.3f  "
            "median_dist=%.3f  max_dist=%.3f",
            self._n_training,
            threshold_pct,
            self._threshold,
            float(np.median(train_distances)),
            float(np.max(train_distances)),
        )
        return self

    # ── Inference ────────────────────────────────────────────

    def mahalanobis_distance(self, x: np.ndarray) -> float:
        """
        Mahalanobis distance of one observation (13,) from training mean.
        Returns inf if not fitted or if x contains non-finite values.
        """
        if not self._is_fitted or self._mean is None:
            return float("inf")

        x = np.asarray(x, dtype=float).ravel()
        if not np.all(np.isfinite(x)):
            return float("inf")

        diff = x - self._mean
        try:
            dist = float(np.sqrt(diff @ self._inv_cov @ diff))
        except Exception:
            dist = float("inf")
        return dist

    def is_ood(self, x: np.ndarray) -> bool:
        """Return True if observation is out-of-distribution."""
        return self.mahalanobis_distance(x) > self._threshold

    def ood_response(self, city_slug: str, distance: float) -> dict:
        """
        Standardised response dict for OOD inputs.
        Matches PredictionResponseV2 shape so the API layer can return it directly.
        """
        from datetime import datetime, timezone
        return {
            "inference_id":      str(uuid4()),
            "city":              city_slug.replace("_", " ").title(),
            "city_slug":         city_slug,
            "inferred_at":       datetime.now(timezone.utc).isoformat(),
            "model_version":     "ood_guard",
            "calibration_version": "n/a",
            "source":            "ood_guard",
            "event_probability": None,
            "confidence_interval": None,
            "uncertainty":       None,
            "model_entropy":     None,
            "risk_band":         "Unknown",
            "is_alert":          False,
            "component_scores":  None,
            "drivers":           None,
            "weather_inputs":    {},
            "climatology_context": None,
            "ood_distance":      round(distance, 4),
            "ood_reason":        (
                "Observation outside the trained climatological manifold. "
                "Cannot produce a reliable probability estimate."
            ),
        }

    def extract_features(self, feature_dict: dict) -> np.ndarray:
        """
        Extract the 13 OOD features from a feature dict (e.g., EnrichedFeatures.to_dict()).
        Missing values → 0.0.
        """
        return np.array(
            [float(feature_dict.get(f, 0.0) or 0.0) for f in OOD_FEATURES],
            dtype=float,
        )

    # ── Diagnostics ─────────────────────────────────────────

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def n_training_samples(self) -> int:
        return self._n_training

    def __repr__(self) -> str:
        return (
            f"OODDetector(fitted={self._is_fitted}, "
            f"n={self._n_training}, threshold={self._threshold:.3f})"
        )

    # ── Persistence ─────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("OODDetector saved → %s", path)

    @classmethod
    def load(cls, path: Path) -> "OODDetector":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected OODDetector, got {type(obj)}")
        logger.info("OODDetector loaded ← %s (n=%d)", path, obj._n_training)
        return obj

    # ── Private ─────────────────────────────────────────────

    def _batch_mahalanobis(self, X: np.ndarray) -> np.ndarray:
        """Vectorised Mahalanobis distances for all rows in X."""
        diffs = X - self._mean
        # (N, d) @ (d, d) → (N, d); then element-wise * diffs → (N, d); sum → (N,)
        left  = diffs @ self._inv_cov
        dists = np.sqrt(np.sum(left * diffs, axis=1))
        return dists
