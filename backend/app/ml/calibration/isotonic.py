"""
HydroGuard-AI -- Isotonic Calibrator
======================================
Post-hoc probability calibration via isotonic regression.
Maps raw FusionModel P(event) -> calibrated P_calib.

Calibration quality measured by:
  Brier Score: mean squared error between probability and outcome (lower = better)
  ECE (Expected Calibration Error): mean |predicted - actual| in bins

CI lookup table:
  Pre-computed bootstrap confidence intervals at 99 probability points.
  Interpolated at inference time -> O(1) CI per prediction.

Uncertainty computation (Addition A):
  uncertainty = CI_width + entropy_component + drift_component + branch_variance
  model_entropy H(p) = -p*log(p) - (1-p)*log(1-p)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

import joblib
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibrationMetrics:
    brier_before: float
    brier_after:  float
    ece_before:   float
    ece_after:    float
    n_samples:    int


class IsotonicCalibrator:
    """
    Isotonic regression probability calibrator with bootstrap CI table.

    fit(p_raw, y_true):
        Fits isotonic regression and builds a 99-point CI lookup table.

    transform(p_raw):
        Map raw probabilities to calibrated probabilities.

    confidence_interval(p_calib):
        Return (ci_lower, ci_upper) via table interpolation -- O(1).

    compute_uncertainty(p_calib, ae_variance, tcn_variance, drift_penalty):
        Combined uncertainty estimate for Addition A.
    """

    # 99 probability grid points for CI table
    _P_POINTS = np.linspace(0.01, 0.99, 99)
    _N_BOOTSTRAP = 200   # bootstrap replicas for CI computation

    def __init__(self):
        from sklearn.isotonic import IsotonicRegression
        self._iso:       Optional[IsotonicRegression] = None
        self._ci_table:  Optional[np.ndarray]         = None  # (99, 2) [lower, upper]
        self._is_fitted: bool                          = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    # --------------------------------------------------------
    #  Fit
    # --------------------------------------------------------

    def fit(
        self,
        p_raw:  np.ndarray,
        y_true: np.ndarray,
    ) -> CalibrationMetrics:
        """
        Fit isotonic regression on held-out calibration set.

        Parameters
        ----------
        p_raw  : (N,) uncalibrated FusionModel probabilities
        y_true : (N,) binary ground truth labels

        Returns
        -------
        CalibrationMetrics (before/after Brier and ECE)
        """
        from sklearn.isotonic import IsotonicRegression

        p_raw  = np.asarray(p_raw,  dtype=float).ravel()
        y_true = np.asarray(y_true, dtype=float).ravel()

        if len(p_raw) < 20:
            logger.warning(
                "IsotonicCalibrator: only %d samples -- calibration may be noisy.",
                len(p_raw),
            )

        # Metrics before calibration
        brier_before = self.brier_score(p_raw, y_true)
        ece_before   = self.ece(p_raw, y_true)

        # Fit
        self._iso = IsotonicRegression(out_of_bounds="clip")
        self._iso.fit(p_raw, y_true)

        p_calib       = self._iso.predict(p_raw)
        brier_after   = self.brier_score(p_calib, y_true)
        ece_after     = self.ece(p_calib, y_true)
        self._is_fitted = True

        # Build CI lookup table
        self._build_ci_table(p_raw, y_true)

        metrics = CalibrationMetrics(
            brier_before = round(brier_before, 5),
            brier_after  = round(brier_after,  5),
            ece_before   = round(ece_before,   5),
            ece_after    = round(ece_after,    5),
            n_samples    = len(p_raw),
        )
        logger.info(
            "IsotonicCalibrator fitted: n=%d  "
            "Brier %.4f->%.4f  ECE %.4f->%.4f",
            len(p_raw), brier_before, brier_after, ece_before, ece_after,
        )
        return metrics

    # --------------------------------------------------------
    #  Transform
    # --------------------------------------------------------

    def transform(
        self, p_raw: Union[np.ndarray, float]
    ) -> Union[np.ndarray, float]:
        """Map raw probabilities to calibrated probabilities."""
        if not self._is_fitted or self._iso is None:
            return p_raw
        scalar = np.isscalar(p_raw)
        arr    = np.asarray([p_raw] if scalar else p_raw, dtype=float)
        out    = self._iso.predict(arr)
        return float(out[0]) if scalar else out

    # --------------------------------------------------------
    #  Confidence interval
    # --------------------------------------------------------

    def confidence_interval(self, p_calib: float) -> Tuple[float, float]:
        """
        Return (ci_lower, ci_upper) via interpolation on the pre-built table.
        O(1) per call.
        """
        if self._ci_table is None:
            half = min(0.15, max(0.05, p_calib * (1 - p_calib) * 2))
            return (max(0.0, p_calib - half), min(1.0, p_calib + half))

        p   = float(np.clip(p_calib, 0.01, 0.99))
        idx = np.searchsorted(self._P_POINTS, p)
        idx = int(np.clip(idx, 0, len(self._P_POINTS) - 1))
        return (
            float(np.clip(self._ci_table[idx, 0], 0.0, 1.0)),
            float(np.clip(self._ci_table[idx, 1], 0.0, 1.0)),
        )

    # --------------------------------------------------------
    #  Uncertainty (Addition A)
    # --------------------------------------------------------

    def compute_uncertainty(
        self,
        p_calib:      float,
        ae_variance:  float  = 0.0,
        tcn_variance: float  = 0.0,
        drift_penalty: float = 0.0,
    ) -> float:
        """
        Combined uncertainty estimate.

        uncertainty = CI_width
                    + 0.3 * H(p)          <- model entropy component
                    + branch_variance      <- AE/TCN model uncertainty
                    + drift_component      <- capped drift contribution

        H(p) = -p*log(p) - (1-p)*log(1-p)  (entropy of Bernoulli)
        """
        ci_lo, ci_hi = self.confidence_interval(p_calib)
        ci_width = ci_hi - ci_lo

        # Entropy component
        p   = float(np.clip(p_calib, 1e-9, 1 - 1e-9))
        H_p = -p * np.log(p) - (1 - p) * np.log(1 - p)
        entropy_component = 0.3 * float(H_p)

        # Branch variance (average of AE + TCN uncertainties)
        branch_variance = 0.1 * (float(ae_variance) + float(tcn_variance)) / 2.0

        # Drift penalty (capped)
        drift_component = float(np.clip(drift_penalty, 0.0, 0.2))

        return float(np.clip(
            ci_width + entropy_component + branch_variance + drift_component,
            0.0, 1.0,
        ))

    def model_entropy(self, p_calib: float) -> float:
        """H(p) = -p*log(p) - (1-p)*log(1-p) for Addition A field."""
        p = float(np.clip(p_calib, 1e-9, 1 - 1e-9))
        return float(-p * np.log(p) - (1 - p) * np.log(1 - p))

    # --------------------------------------------------------
    #  Quality metrics
    # --------------------------------------------------------

    @staticmethod
    def brier_score(p: np.ndarray, y: np.ndarray) -> float:
        p = np.asarray(p, dtype=float)
        y = np.asarray(y, dtype=float)
        return float(np.mean((p - y) ** 2))

    @staticmethod
    def ece(
        p: np.ndarray,
        y: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        """Expected Calibration Error (uniform binning)."""
        p = np.asarray(p, dtype=float)
        y = np.asarray(y, dtype=float)
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        ece  = 0.0
        n    = len(p)
        for i in range(n_bins):
            mask = (p >= bins[i]) & (p < bins[i + 1])
            if not mask.any():
                continue
            frac = mask.sum() / n
            avg_conf = float(p[mask].mean())
            avg_acc  = float(y[mask].mean())
            ece     += frac * abs(avg_conf - avg_acc)
        return ece

    # --------------------------------------------------------
    #  Persistence
    # --------------------------------------------------------

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("IsotonicCalibrator saved -> %s", path)

    @classmethod
    def load(cls, path: Path) -> "IsotonicCalibrator":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected IsotonicCalibrator, got {type(obj)}")
        logger.info("IsotonicCalibrator loaded <- %s", path)
        return obj

    # --------------------------------------------------------
    #  Private
    # --------------------------------------------------------

    def _build_ci_table(
        self,
        p_raw:  np.ndarray,
        y_true: np.ndarray,
    ) -> None:
        """
        Pre-compute bootstrap CI at 99 probability points.
        Bootstrap 200 replicas; for each, re-fit isotonic and transform the point.
        CI = [q2.5, q97.5] of the 200 calibrated values.
        """
        from sklearn.isotonic import IsotonicRegression

        n   = len(p_raw)
        ci  = np.zeros((99, 2))

        for j, p_val in enumerate(self._P_POINTS):
            boot_vals = []
            for _ in range(self._N_BOOTSTRAP):
                idx   = np.random.randint(0, n, size=n)
                iso_b = IsotonicRegression(out_of_bounds="clip")
                try:
                    iso_b.fit(p_raw[idx], y_true[idx])
                    boot_vals.append(float(iso_b.predict([p_val])[0]))
                except Exception:
                    boot_vals.append(p_val)
            boot_arr   = np.array(boot_vals)
            ci[j, 0]   = np.percentile(boot_arr, 2.5)
            ci[j, 1]   = np.percentile(boot_arr, 97.5)

        self._ci_table = ci
        logger.debug("IsotonicCalibrator: CI table built (%d points)", len(self._P_POINTS))
