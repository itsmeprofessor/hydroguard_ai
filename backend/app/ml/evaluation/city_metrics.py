"""
HydroGuard-AI — Per-City Evaluation Metrics v1.0
=================================================
Computes the full evaluation metric suite for a trained city model from
saved artifacts — no TensorFlow, no training re-run required.

Metric sources and domain:
  AUC / PR-AUC / ECE / Brier
      Loaded from training_metrics.json when present (TEST split, unbiased).
      Recomputed from test_data.npz if the JSON keys are absent.

  Precision / Recall / F1
      Computed from test_data.npz (unbiased TEST split, preferred).
      Falls back to cal_data.npz with a note (CAL split; mildly in-distribution
      for threshold derivation but shares the calibrated probability domain).

  AlertTier thresholds
      Always derived from cal_data.npz via AlertTierClassifier.from_cal_data().

Operational semantics preserved:
  ADVISORY tier  — recall-priority (recall ≥ 85%); in-app notification only
  ALERT tier     — precision-priority (precision ≥ 65%); push notification
  F1             — balance metric reported for academic completeness; not the
                   primary optimisation target of this architecture.
  Brier Score    — evaluates calibrated probability quality, not classification
                   accuracy. Lower is better (0 = perfect).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Data containers ──────────────────────────────────────────────────────────

@dataclass
class TierMetrics:
    """Classification metrics at a single decision threshold."""
    threshold: float
    n_predicted_positive: int
    n_true_positive: int
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]


@dataclass
class CityEvalReport:
    """Full per-city evaluation report.

    Probabilistic metrics (auc, brier_score, ece) are threshold-free and
    characterise the calibrated probability output quality.
    Tier metrics (advisory, alert) apply the operational thresholds derived
    from AlertTierClassifier to classify predictions into ADVISORY/ALERT.
    """
    city_slug: str
    eval_split: str           # "test" | "cal" — which data P/R/F1 was computed on
    n_rows: int
    n_positive: int
    positive_rate: float

    # Probabilistic metrics — no threshold
    auc: Optional[float]
    pr_auc: Optional[float]
    brier_score: Optional[float]
    ece: Optional[float]

    # Operational thresholds (from cal_data.npz → AlertTierClassifier)
    threshold_source: str

    # ADVISORY tier: recall-priority threshold
    advisory: TierMetrics

    # ALERT tier: precision-priority threshold
    alert: TierMetrics

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Evaluator ─────────────────────────────────────────────────────────────────

class CityEvaluator:
    """
    Load saved city model artifacts and compute the full metric suite.

    Designed to be called from scripts/evaluate.py or as a library function.
    Does NOT load TensorFlow models or re-run training.
    """

    def evaluate(self, city_dir: Path) -> Optional[CityEvalReport]:
        """Evaluate one city from its saved_models directory.

        Parameters
        ----------
        city_dir : Path
            Path to the city's saved-models directory, e.g.
            ``backend/saved_models/city_models/islamabad/``

        Returns
        -------
        CityEvalReport or None if required artifacts are missing.
        """
        city_dir = Path(city_dir)
        slug = city_dir.name

        cal_path  = city_dir / "cal_data.npz"
        test_path = city_dir / "test_data.npz"
        metrics_path = city_dir / "training_metrics.json"

        if not cal_path.exists():
            logger.warning("[%s] cal_data.npz not found — skipping evaluation", slug)
            return None

        # ── 1. Load AlertTier thresholds from CAL data ────────────────────────
        from app.services.alert_tier import AlertTierClassifier
        atc = AlertTierClassifier.from_cal_data(cal_path)

        # ── 2. Select probability arrays for P/R/F1 ──────────────────────────
        if test_path.exists():
            arr = np.load(test_path)
            y_true = arr["y_true"].astype(float)
            y_score = arr["y_score"].astype(float)
            eval_split = "test"
        else:
            arr = np.load(cal_path)
            y_true = arr["y_true"].astype(float)
            y_score = arr["y_score"].astype(float)
            eval_split = "cal"
            logger.info(
                "[%s] test_data.npz not found — using cal_data.npz for P/R/F1 "
                "(mildly in-distribution for threshold; train with v3.5+ to generate test_data.npz)",
                slug,
            )

        n_rows    = len(y_true)
        n_pos     = int((y_true == 1).sum())
        pos_rate  = round(float(n_pos / max(n_rows, 1)), 4)

        # ── 3. Probabilistic metrics ──────────────────────────────────────────
        # Prefer training_metrics.json (TEST split, already validated)
        stored = _load_training_metrics(metrics_path)
        auc      = _metric_from(stored, "test_auc",    y_true, y_score, "roc_auc")
        pr_auc   = _metric_from(stored, "test_pr_auc", y_true, y_score, "pr_auc")
        brier    = _metric_from(stored, "test_brier",  y_true, y_score, "brier")
        ece      = _metric_from(stored, "test_ece",    y_true, y_score, "ece")

        # ── 4. Tier-aware classification metrics ──────────────────────────────
        advisory = _tier_metrics(y_true, y_score, atc.advisory_threshold)
        alert    = _tier_metrics(y_true, y_score, atc.alert_threshold)

        return CityEvalReport(
            city_slug       = slug,
            eval_split      = eval_split,
            n_rows          = n_rows,
            n_positive      = n_pos,
            positive_rate   = pos_rate,
            auc             = auc,
            pr_auc          = pr_auc,
            brier_score     = brier,
            ece             = ece,
            threshold_source= atc.source,
            advisory        = advisory,
            alert           = alert,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_training_metrics(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _metric_from(
    stored: dict,
    key: str,
    y_true: np.ndarray,
    y_score: np.ndarray,
    metric: str,
) -> Optional[float]:
    """Return stored scalar metric if present and valid; otherwise recompute."""
    v = stored.get(key)
    if v is not None and isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
        return round(float(v), 4)
    # Fall back: recompute from the probability arrays at hand
    try:
        from sklearn.metrics import (
            roc_auc_score, average_precision_score, brier_score_loss,
        )
        from app.ml.calibration.isotonic import IsotonicCalibrator

        if metric == "roc_auc":
            return round(float(roc_auc_score(y_true, y_score)), 4)
        if metric == "pr_auc":
            return round(float(average_precision_score(y_true, y_score)), 4)
        if metric == "brier":
            return round(float(brier_score_loss(y_true, y_score)), 4)
        if metric == "ece":
            return round(float(IsotonicCalibrator.ece(y_score, y_true)), 4)
    except Exception as exc:
        logger.debug("Recompute %s failed: %s", metric, exc)
    return None


def _tier_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float,
) -> TierMetrics:
    """Compute classification metrics at a single decision threshold."""
    try:
        from sklearn.metrics import precision_score, recall_score, f1_score

        y_pred = (y_score >= threshold).astype(int)
        n_pred  = int(y_pred.sum())
        n_tp    = int(((y_pred == 1) & (y_true == 1)).sum())

        prec = round(float(precision_score(y_true, y_pred, zero_division=0)), 4)
        rec  = round(float(recall_score(y_true, y_pred,    zero_division=0)), 4)
        f1   = round(float(f1_score(y_true, y_pred,        zero_division=0)), 4)

        return TierMetrics(
            threshold            = round(float(threshold), 4),
            n_predicted_positive = n_pred,
            n_true_positive      = n_tp,
            precision            = prec,
            recall               = rec,
            f1                   = f1,
        )
    except Exception as exc:
        logger.warning("_tier_metrics at thr=%.4f failed: %s", threshold, exc)
        return TierMetrics(
            threshold            = round(float(threshold), 4),
            n_predicted_positive = 0,
            n_true_positive      = 0,
            precision            = None,
            recall               = None,
            f1                   = None,
        )
