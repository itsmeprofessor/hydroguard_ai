"""
HydroGuard-AI -- LightGBM Fusion Model
========================================
Supervised binary classifier that converts AE/TCN branch outputs +
dynamic weather features into a calibrated P(hydro-meteorological event).

Trained on the calibration set (chronologically last 10% of data) using
weak labels from LabelEngine. Positive class weighted by weak_label_conf.

Input features (16 total -- FUSION_FEATURES list):
  ae_percentile, tcn_percentile,       -- branch ECDF scores
  ae_variance, tcn_variance,           -- model uncertainty (Addition A)
  pressure_delta_3h, pressure_delta_6h,-- dynamics
  rain_rate_1h, rain_accumulation_3h,
  prcp_climo_pct, humidity_climo_pct,
  moisture_flux, tdew_spread, cloud_jump_3h,
  month, is_monsoon_month, vulnerability

Output: P(event) in [0, 1] -- uncalibrated (IsotonicCalibrator applied downstream).

Usage:
    model = FusionModel()
    metrics = model.train(X_cal, y_cal, sample_weight=conf_cal)
    p_raw = model.predict_proba(X_new)
    drivers = model.shap_values(feature_dict)
    model.save(Path("lgbm_model.pkl"))
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

logger = logging.getLogger(__name__)


# Locked feature order -- must match the dict keys produced by CityModelService
FUSION_FEATURES: List[str] = [
    "ae_percentile",
    "tcn_percentile",
    "ae_variance",
    "tcn_variance",
    "pressure_delta_3h",
    "pressure_delta_6h",
    "rain_rate_1h",
    "rain_accumulation_3h",
    "prcp_climo_pct",
    "humidity_climo_pct",
    "moisture_flux",
    "tdew_spread",
    "cloud_jump_3h",
    "month",
    "is_monsoon_month",
    "vulnerability",
]

LGB_PARAMS: Dict[str, Any] = {
    "objective":          "binary",
    "n_estimators":       300,
    "learning_rate":      0.05,
    "max_depth":          6,
    "num_leaves":         31,
    "min_child_samples":  20,
    "subsample":          0.8,
    "colsample_bytree":   0.8,
    "random_state":       42,
    "verbose":            -1,
    "n_jobs":             -1,
}


class FusionModel:
    """
    LightGBM binary classifier for P(hydro event) estimation.

    Inputs  : 16-feature vector assembled by CityModelService at inference time.
    Outputs : scalar probability P(event) in [0, 1].

    Training
    --------
    Caller is responsible for:
      - Providing X_cal (n, 16) from the calibration set.
      - Providing y_cal (n,) of binary labels {0, 1} -- abstains (-1) removed.
      - Providing sample_weight (n,) = weak_label_conf values.
      - scale_pos_weight is set automatically from class counts.
    """

    def __init__(self):
        self._model         = None
        self._feature_names = FUSION_FEATURES
        self._is_fitted     = False
        self._train_metrics: Dict[str, float] = {}

    # --------------------------------------------------------
    #  Training
    # --------------------------------------------------------

    def train(
        self,
        X_cal:         np.ndarray,       # (N, 16) calibration feature matrix
        y_cal:         np.ndarray,       # (N,) binary labels
        sample_weight: Optional[np.ndarray] = None,  # (N,) weak_label_conf
        eval_frac:     float = 0.2,
    ) -> Dict[str, float]:
        """
        Train LightGBM on calibration set.

        Parameters
        ----------
        X_cal         : feature matrix, rows in calibration order
        y_cal         : binary labels (no abstains)
        sample_weight : per-sample confidence weights
        eval_frac     : fraction of X_cal used as LGB eval set

        Returns
        -------
        dict with val_auc, val_brier, positive_rate, n_samples
        """
        try:
            import lightgbm as lgb
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import roc_auc_score, brier_score_loss
        except ImportError as exc:
            raise ImportError(
                "lightgbm and scikit-learn are required for FusionModel. "
                f"Install with: pip install lightgbm scikit-learn. Error: {exc}"
            )

        X = np.asarray(X_cal, dtype=float)
        y = np.asarray(y_cal, dtype=float)

        # Imbalance correction
        pos = int(y.sum())
        neg = int((y == 0).sum())
        scale_pos = (neg / max(pos, 1)) if pos > 0 else 1.0

        params = {**LGB_PARAMS, "scale_pos_weight": scale_pos}

        # Train / eval split (chronological -- do NOT shuffle)
        split_idx = int(len(X) * (1 - eval_frac))
        X_tr, X_ev = X[:split_idx],  X[split_idx:]
        y_tr, y_ev = y[:split_idx],  y[split_idx:]
        sw_tr = sample_weight[:split_idx] if sample_weight is not None else None
        sw_ev = sample_weight[split_idx:] if sample_weight is not None else None

        self._model = lgb.LGBMClassifier(**params)
        self._model.fit(
            X_tr, y_tr,
            sample_weight = sw_tr,
            eval_set      = [(X_ev, y_ev)],
            eval_sample_weight = [sw_ev] if sw_ev is not None else None,
            callbacks     = [lgb.early_stopping(30, verbose=False),
                             lgb.log_evaluation(period=-1)],
        )

        # Compute metrics
        p_ev = self._model.predict_proba(X_ev)[:, 1]
        try:
            val_auc = float(roc_auc_score(y_ev, p_ev))
        except Exception:
            val_auc = 0.5
        val_brier = float(brier_score_loss(y_ev, p_ev))

        self._is_fitted     = True
        self._train_metrics = {
            "val_auc":       round(val_auc, 4),
            "val_brier":     round(val_brier, 4),
            "positive_rate": round(float(y.mean()), 4),
            "n_samples":     int(len(X)),
            "scale_pos_weight": round(scale_pos, 2),
        }

        logger.info(
            "FusionModel trained: n=%d  pos_rate=%.1f%%  val_auc=%.3f  val_brier=%.4f",
            len(X), 100 * float(y.mean()), val_auc, val_brier,
        )
        return self._train_metrics

    # --------------------------------------------------------
    #  Inference
    # --------------------------------------------------------

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        (N, 16) -> (N,) P(event) values, uncalibrated.
        """
        if not self._is_fitted or self._model is None:
            raise RuntimeError("FusionModel not trained. Call train() first.")
        X = np.asarray(X, dtype=float)
        return self._model.predict_proba(X)[:, 1]

    def predict_scalar(self, features: Dict[str, float]) -> float:
        """Single observation dict -> scalar P(event)."""
        x = np.array(
            [float(features.get(f, 0.0) or 0.0) for f in self._feature_names],
            dtype=float,
        ).reshape(1, -1)
        return float(self.predict_proba(x)[0])

    def shap_values(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Top-8 SHAP values for one observation via TreeExplainer.
        Returns {feature: shap_value}. Empty dict on failure.
        """
        if not self._is_fitted or self._model is None:
            return {}
        try:
            import shap
            explainer = shap.TreeExplainer(self._model)
            x = np.array(
                [float(features.get(f, 0.0) or 0.0) for f in self._feature_names],
            ).reshape(1, -1)
            sv = explainer.shap_values(x)
            if isinstance(sv, list):
                sv = sv[1]
            sv = np.asarray(sv).ravel()
            order = np.argsort(-np.abs(sv))[:8]
            return {self._feature_names[i]: round(float(sv[i]), 4) for i in order}
        except Exception as exc:
            logger.debug("FusionModel.shap_values failed: %s", exc)
            return {}

    def feature_importance(self) -> Dict[str, float]:
        """LightGBM built-in feature importance (gain)."""
        if not self._is_fitted or self._model is None:
            return {}
        imp = self._model.feature_importances_
        return {f: float(v) for f, v in zip(self._feature_names, imp)}

    # --------------------------------------------------------
    #  Persistence
    # --------------------------------------------------------

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("FusionModel saved -> %s", path)

    @classmethod
    def load(cls, path: Path) -> "FusionModel":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected FusionModel, got {type(obj)}")
        logger.info("FusionModel loaded <- %s (fitted=%s)", path, obj._is_fitted)
        return obj

    # --------------------------------------------------------
    #  Properties
    # --------------------------------------------------------

    @property
    def train_metrics(self) -> Dict[str, float]:
        return self._train_metrics

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted
