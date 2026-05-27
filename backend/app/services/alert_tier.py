from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_ADVISORY_THRESHOLD: float = 0.35
DEFAULT_ALERT_THRESHOLD: float = 0.65


@dataclass(frozen=True)
class AlertTierResult:
    tier: Literal["NORMAL", "ADVISORY", "ALERT"]
    push_notification: bool
    advisory_threshold: float
    alert_threshold: float


class AlertTierClassifier:
    """Per-city two-tier alert threshold classifier.

    Thresholds are derived from the calibration dataset PR curve at model-load
    time — not hardcoded, not dynamic at inference time. This ensures
    deterministic, auditable runtime behaviour.

    advisory tier: elevated probability, high recall (>=85%) — in-app only
    alert tier:    high probability, high precision (>=65%) — push-notification quality
    """

    def __init__(
        self,
        advisory_threshold: float = DEFAULT_ADVISORY_THRESHOLD,
        alert_threshold: float = DEFAULT_ALERT_THRESHOLD,
    ) -> None:
        if advisory_threshold >= alert_threshold:
            raise ValueError(
                f"advisory_threshold ({advisory_threshold}) must be less than "
                f"alert_threshold ({alert_threshold})"
            )
        self.advisory_threshold = advisory_threshold
        self.alert_threshold = alert_threshold

    @classmethod
    def from_cal_data(
        cls,
        cal_data_path: Path,
        *,
        advisory_recall_target: float = 0.85,
        alert_precision_target: float = 0.65,
    ) -> "AlertTierClassifier":
        """Derive thresholds from held-out calibration data PR curve.

        Expects cal_data.npz with arrays y_true and y_score.
        Falls back to defaults on any failure (missing file, bad arrays, inversion).
        """
        try:
            from sklearn.metrics import precision_recall_curve

            data = np.load(cal_data_path)
            y_true = data["y_true"]
            y_score = data["y_score"]

            prec, rec, thresh = precision_recall_curve(y_true, y_score)
            # prec/rec have one extra element (no-threshold endpoint)
            prec_t = prec[:-1]
            rec_t = rec[:-1]

            advisory_mask = rec_t >= advisory_recall_target
            alert_mask = prec_t >= alert_precision_target

            advisory_threshold = (
                float(thresh[advisory_mask].min())   # lowest threshold still achieving target recall
                if advisory_mask.any()
                else DEFAULT_ADVISORY_THRESHOLD
            )
            if not advisory_mask.any():
                logger.warning(
                    "cal_data at %s: recall never reaches %.0f%% — using default advisory threshold %.3f",
                    cal_data_path, advisory_recall_target * 100, DEFAULT_ADVISORY_THRESHOLD,
                )

            alert_threshold = (
                float(thresh[alert_mask].max())      # highest threshold still meeting precision target
                if alert_mask.any()
                else DEFAULT_ALERT_THRESHOLD
            )
            if not alert_mask.any():
                logger.warning(
                    "cal_data at %s: precision never reaches %.0f%% (max p_score=%.4f) — "
                    "using default alert threshold %.3f; city model may lack discriminative power",
                    cal_data_path, alert_precision_target * 100, float(y_score.max()),
                    DEFAULT_ALERT_THRESHOLD,
                )

            if advisory_threshold >= alert_threshold:
                logger.warning(
                    "cal_data threshold inversion at %s "
                    "(advisory=%.3f >= alert=%.3f) — using defaults",
                    cal_data_path,
                    advisory_threshold,
                    alert_threshold,
                )
                return cls()

            logger.info(
                "AlertTierClassifier derived from %s: advisory=%.3f alert=%.3f",
                cal_data_path,
                advisory_threshold,
                alert_threshold,
            )
            return cls(advisory_threshold, alert_threshold)

        except Exception as exc:
            logger.warning(
                "AlertTierClassifier.from_cal_data(%s) failed — using defaults: %s",
                cal_data_path,
                exc,
            )
            return cls()

    def classify(self, event_probability: float) -> AlertTierResult:
        if event_probability >= self.alert_threshold:
            return AlertTierResult(
                tier="ALERT",
                push_notification=True,
                advisory_threshold=self.advisory_threshold,
                alert_threshold=self.alert_threshold,
            )
        if event_probability >= self.advisory_threshold:
            return AlertTierResult(
                tier="ADVISORY",
                push_notification=False,
                advisory_threshold=self.advisory_threshold,
                alert_threshold=self.alert_threshold,
            )
        return AlertTierResult(
            tier="NORMAL",
            push_notification=False,
            advisory_threshold=self.advisory_threshold,
            alert_threshold=self.alert_threshold,
        )
