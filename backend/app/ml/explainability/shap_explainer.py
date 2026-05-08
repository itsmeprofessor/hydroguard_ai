"""
HydroGuard-AI — SHAP Explainability for FusionModel
=====================================================
Uses SHAP TreeExplainer on the LightGBM FusionModel to produce
per-feature contribution values for each prediction.

Fast: TreeExplainer is O(n_leaves) per sample — no model calls needed.
Returns top-N features by absolute SHAP value for API responses.

Usage:
    explainer = SHAPExplainer(fusion_model)
    drivers = explainer.explain(feature_dict, top_n=8)
    # drivers: [{"feature": "prcp_climo_pct", "shap": 0.31, "value": 2.8}, ...]
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SHAPExplainer:
    """
    SHAP TreeExplainer wrapper for HydroGuard-AI FusionModel (LightGBM).

    Lazily initialises the SHAP explainer on first call to explain()
    to avoid import overhead at startup.
    """

    def __init__(self, fusion_model):
        """
        Parameters
        ----------
        fusion_model : FusionModel instance (must have _model and _feature_names attrs)
        """
        self._fusion       = fusion_model
        self._explainer    = None   # lazy init

    def _ensure_explainer(self) -> None:
        """Initialise SHAP TreeExplainer if not already done."""
        if self._explainer is not None:
            return
        try:
            import shap
            self._explainer = shap.TreeExplainer(self._fusion._model)
            logger.info("SHAPExplainer initialised (TreeExplainer)")
        except Exception as exc:
            logger.warning("SHAP TreeExplainer init failed: %s", exc)
            self._explainer = None

    def explain(
        self,
        features: Dict[str, float],
        top_n: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Compute SHAP values for one observation.

        Parameters
        ----------
        features : dict of feature_name -> float value
                   (must contain all keys in FusionModel.FEATURE_NAMES)
        top_n    : number of top features to return (by |SHAP|)

        Returns
        -------
        list of dicts: [{"feature": str, "shap": float, "value": float}]
        sorted by |shap| descending. Empty list on failure.
        """
        self._ensure_explainer()
        if self._explainer is None or self._fusion._model is None:
            return []

        try:
            feature_names = getattr(self._fusion, "_feature_names", [])
            if not feature_names:
                return []

            # Build feature array in training order
            x = np.array(
                [float(features.get(f, 0.0) or 0.0) for f in feature_names],
                dtype=float,
            ).reshape(1, -1)

            shap_vals = self._explainer.shap_values(x)

            # LightGBM binary: shap_values is (1, n_features) or list of two
            if isinstance(shap_vals, list):
                # [negative_class, positive_class] — take positive class
                sv = np.asarray(shap_vals[1]).ravel()
            else:
                sv = np.asarray(shap_vals).ravel()

            if len(sv) != len(feature_names):
                return []

            # Sort by |SHAP| descending, take top_n
            order   = np.argsort(-np.abs(sv))[:top_n]
            drivers = [
                {
                    "feature": feature_names[i],
                    "shap":    round(float(sv[i]), 4),
                    "value":   round(float(features.get(feature_names[i], 0.0) or 0.0), 4),
                }
                for i in order
            ]
            return drivers

        except Exception as exc:
            logger.warning("SHAPExplainer.explain failed: %s", exc)
            return []

    def feature_importance(self) -> Dict[str, float]:
        """
        Mean |SHAP| across the training set (if explainer is fitted on background data).
        Falls back to LightGBM's built-in feature importance.
        """
        try:
            feature_names = getattr(self._fusion, "_feature_names", [])
            if not feature_names or self._fusion._model is None:
                return {}
            imp = self._fusion._model.feature_importances_
            return {name: float(v) for name, v in zip(feature_names, imp)}
        except Exception:
            return {}
