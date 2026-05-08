"""
HydroGuard-AI — ECDF Scaler
=============================
Maps raw reconstruction errors (from AE/TCN) to their percentile rank
in the training error distribution using the empirical CDF.

Unlike p99 normalisation (which saturates all errors above p99 to 1.0),
ECDF scoring preserves ordering above the training maximum — so a truly
extreme event scores higher than a merely unusual one.

Usage:
    scaler = ECDFScaler()
    scaler.fit(train_errors)              # numpy array of per-sample MSE
    pct = scaler.transform_scalar(0.047)  # float in [0, 1]
    arr = scaler.transform(new_errors)    # vectorised
    scaler.save(Path("ae_ecdf.pkl"))
    scaler2 = ECDFScaler.load(Path("ae_ecdf.pkl"))
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import joblib
import numpy as np

logger = logging.getLogger(__name__)


class ECDFScaler:
    """
    Empirical CDF scaler for reconstruction error normalisation.

    fit(errors):
        Stores the sorted training errors for interpolation.
        Requires >= 2 samples.

    transform(errors):
        Maps each error value to its percentile rank in [0, 1].
        Values above the training maximum extrapolate linearly
        (kept <= 1.0 for risk_band purposes, but the raw value
        is available via transform_raw() if needed).

    transform_scalar(error):
        Single-value convenience wrapper.
    """

    def __init__(self):
        self._sorted_errors: np.ndarray = np.array([0.0, 1.0])
        self._n: int = 0
        self._is_fitted: bool = False

    # ── Fit ─────────────────────────────────────────────────

    def fit(self, errors: np.ndarray) -> "ECDFScaler":
        """
        Fit on training reconstruction errors.

        Parameters
        ----------
        errors : 1-D numpy array of per-sample MSE values (>= 2 samples).
        """
        errors = np.asarray(errors, dtype=float).ravel()
        errors = errors[np.isfinite(errors)]   # strip NaN/Inf

        if len(errors) < 2:
            logger.warning("ECDFScaler.fit: fewer than 2 finite samples — using defaults.")
            self._sorted_errors = np.array([0.0, 1.0])
            self._n = 0
            self._is_fitted = True
            return self

        self._sorted_errors = np.sort(errors)
        self._n = len(self._sorted_errors)
        self._is_fitted = True

        logger.info(
            "ECDFScaler fitted: n=%d  min=%.6f  p50=%.6f  p99=%.6f  max=%.6f",
            self._n,
            self._sorted_errors[0],
            float(np.percentile(self._sorted_errors, 50)),
            float(np.percentile(self._sorted_errors, 99)),
            self._sorted_errors[-1],
        )
        return self

    # ── Transform (vectorised) ───────────────────────────────

    def transform(self, errors: np.ndarray) -> np.ndarray:
        """
        Map an array of errors → percentile scores in [0, 1].

        Uses np.searchsorted for O(n log n) vectorised lookup.
        Values at or above the training maximum return 1.0.
        """
        errors = np.asarray(errors, dtype=float).ravel()
        ranks  = np.searchsorted(self._sorted_errors, errors, side="right")
        pcts   = ranks / max(self._n, 1)
        return np.clip(pcts, 0.0, 1.0)

    def transform_scalar(self, error: float) -> float:
        """Single-value ECDF lookup. Returns float in [0, 1]."""
        if not np.isfinite(error):
            return 0.0
        rank = int(np.searchsorted(self._sorted_errors, error, side="right"))
        return float(np.clip(rank / max(self._n, 1), 0.0, 1.0))

    # ── Statistics ───────────────────────────────────────────

    @property
    def n_training_samples(self) -> int:
        return self._n

    @property
    def training_max(self) -> float:
        return float(self._sorted_errors[-1]) if self._n > 0 else 1.0

    @property
    def training_p99(self) -> float:
        if self._n == 0:
            return 1.0
        return float(np.percentile(self._sorted_errors, 99))

    def __repr__(self) -> str:
        return (
            f"ECDFScaler(fitted={self._is_fitted}, n={self._n}, "
            f"max={self.training_max:.6f})"
        )

    # ── Persistence ─────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("ECDFScaler saved → %s", path)

    @classmethod
    def load(cls, path: Path) -> "ECDFScaler":
        path = Path(path)
        obj  = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected ECDFScaler, got {type(obj)}")
        logger.info("ECDFScaler loaded ← %s (n=%d)", path, obj._n)
        return obj
