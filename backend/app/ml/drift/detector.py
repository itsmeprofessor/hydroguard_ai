"""
DriftDetector — Population Stability Index (PSI) based drift detection.
Compares a rolling window of recent predictions against training baseline statistics.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PSI_WARN = 0.10   # distribution shift detected
PSI_CRIT = 0.20   # retrain likely required
N_BUCKETS = 10


def _compute_psi(baseline_values: np.ndarray, current_values: np.ndarray) -> float:
    """Population Stability Index between two distributions."""
    if len(baseline_values) == 0 or len(current_values) == 0:
        return 0.0

    # Build bucket edges from baseline
    percentiles = np.linspace(0, 100, N_BUCKETS + 1)
    edges       = np.percentile(baseline_values, percentiles)
    edges[0]    = -np.inf
    edges[-1]   = np.inf

    base_counts = np.histogram(baseline_values, bins=edges)[0].astype(float)
    curr_counts = np.histogram(current_values,  bins=edges)[0].astype(float)

    # Avoid division by zero / log(0)
    base_pct = (base_counts + 0.5) / (len(baseline_values) + N_BUCKETS * 0.5)
    curr_pct = (curr_counts + 0.5) / (len(current_values)  + N_BUCKETS * 0.5)

    psi = float(np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct)))
    return max(0.0, psi)


class DriftDetector:
    """
    Holds baseline statistics saved at train time.
    Call should_retrain() with a recent window DataFrame to check drift.
    """

    WATCH_FEATURES = ["prcp", "humidity", "pressure", "cloud_cover"]

    def __init__(self, baseline_stats: Dict[str, List[float]]):
        """
        baseline_stats: {feature_name: [list of training values (sample)]}
        Built and stored during model training.
        """
        self.baseline = {
            k: np.array(v, dtype=float) for k, v in baseline_stats.items()
        }

    def psi_scores(self, recent: Dict[str, List[float]]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for feat in self.WATCH_FEATURES:
            if feat in self.baseline and feat in recent:
                scores[feat] = _compute_psi(
                    self.baseline[feat],
                    np.array(recent[feat], dtype=float),
                )
        return scores

    def should_retrain(
        self,
        recent: Dict[str, List[float]],
    ) -> Tuple[bool, Dict[str, Any]]:
        scores   = self.psi_scores(recent)
        max_psi  = max(scores.values(), default=0.0)
        triggered = max_psi >= PSI_CRIT
        warning   = max_psi >= PSI_WARN

        return triggered, {
            "should_retrain": triggered,
            "drift_warning":  warning,
            "max_psi":        round(max_psi, 4),
            "psi_threshold_warn": PSI_WARN,
            "psi_threshold_crit": PSI_CRIT,
            "feature_psi":    {k: round(v, 4) for k, v in scores.items()},
        }
