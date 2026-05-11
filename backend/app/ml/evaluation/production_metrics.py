"""
HydroGuard-AI — Operational Forecast Metrics v1.0
==================================================
Six production-grade operational metrics for evaluating HydroGuard-AI
as a deployed early-warning system.

Metrics:
  1. Precision@TopK     — accuracy of highest-confidence alerts
  2. Event Recall       — detection rate of known historical events
  3. Lead Time          — how far in advance warnings fire
  4. False Alarm Rate   — false positives per 100 forecasts
  5. Alert Stability    — oscillation / volatility score
  6. Persistence Score  — sustained elevated risk before events

Usage:
    from app.ml.evaluation.production_metrics import OperationalMetricsCalculator

    calc    = OperationalMetricsCalculator()
    metrics = calc.compute_all(
        dates=df["date"],
        y_true=df["weak_label"],
        p_hat=predictions,          # calibrated probabilities
        event_anchors=event_list,   # ISO date strings
        city_slug="islamabad",
    )
    print(metrics.summary())
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Data containers ───────────────────────────────────────────────────────

@dataclass
class PrecisionAtTopK:
    k_pct:      float          # e.g. 0.01 = top 1%
    n_top:      int
    precision:  float          # true positive rate in top-k
    n_true_pos: int

@dataclass
class EventRecallResult:
    n_events:          int
    n_detected:        int
    recall:            float
    missed_events:     List[str]
    detected_events:   List[str]

@dataclass
class LeadTimeResult:
    n_events_with_lead: int
    mean_days:          float
    median_days:        float
    p90_days:           float
    max_days:           float
    by_event:           Dict[str, float]    # event_date → lead_days

@dataclass
class FalseAlarmResult:
    false_alarms:       int
    total_alerts:       int
    far_per_100:        float               # False alarm rate per 100 alerts
    by_month:           Dict[int, float]    # month → FAR
    by_season:          Dict[str, float]    # season → FAR

@dataclass
class AlertStabilityResult:
    oscillation_count:  int                 # transitions Low→High or High→Low
    volatility_score:   float               # 0 = perfectly stable, 1 = max volatile
    n_single_day_spikes: int                # isolated high-risk days (no neighbours)

@dataclass
class PersistenceResult:
    n_events_assessed:  int
    mean_persistence:   float               # avg days of elevated risk before event
    median_persistence: float
    p10_persistence:    float               # lowest 10% (poorly signalled events)
    by_event:           Dict[str, float]

@dataclass
class OperationalMetrics:
    city_slug:          str
    n_observations:     int
    alert_threshold:    float
    precision_top1:     Optional[PrecisionAtTopK]    = None
    precision_top5:     Optional[PrecisionAtTopK]    = None
    precision_top10:    Optional[PrecisionAtTopK]    = None
    event_recall:       Optional[EventRecallResult]  = None
    lead_time:          Optional[LeadTimeResult]     = None
    false_alarm:        Optional[FalseAlarmResult]   = None
    alert_stability:    Optional[AlertStabilityResult] = None
    persistence:        Optional[PersistenceResult]  = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info("OperationalMetrics saved → %s", path)

    def summary(self) -> str:
        lines = [
            f"  ── Operational Metrics [{self.city_slug}] ──",
            f"  Observations : {self.n_observations}",
            f"  Alert threshold: {self.alert_threshold:.2f}",
        ]
        if self.precision_top1:
            lines.append(
                f"  Precision@Top1% : {self.precision_top1.precision:.3f}  "
                f"({self.precision_top1.n_true_pos}/{self.precision_top1.n_top} events)"
            )
        if self.precision_top5:
            lines.append(
                f"  Precision@Top5% : {self.precision_top5.precision:.3f}"
            )
        if self.event_recall:
            lines.append(
                f"  Event Recall    : {self.event_recall.recall:.3f}  "
                f"({self.event_recall.n_detected}/{self.event_recall.n_events} detected)"
            )
        if self.lead_time and self.lead_time.n_events_with_lead > 0:
            lines.append(
                f"  Lead Time       : mean={self.lead_time.mean_days:.1f}d  "
                f"median={self.lead_time.median_days:.1f}d  "
                f"p90={self.lead_time.p90_days:.1f}d"
            )
        if self.false_alarm:
            lines.append(
                f"  FAR/100         : {self.false_alarm.far_per_100:.1f}  "
                f"({self.false_alarm.false_alarms}/{self.false_alarm.total_alerts})"
            )
        if self.alert_stability:
            lines.append(
                f"  Volatility      : {self.alert_stability.volatility_score:.3f}  "
                f"oscillations={self.alert_stability.oscillation_count}  "
                f"spikes={self.alert_stability.n_single_day_spikes}"
            )
        if self.persistence:
            lines.append(
                f"  Persistence     : mean={self.persistence.mean_persistence:.1f}d  "
                f"p10={self.persistence.p10_persistence:.1f}d"
            )
        return "\n".join(lines)


# ── Calculator ────────────────────────────────────────────────────────────

class OperationalMetricsCalculator:
    """
    Compute all six operational forecast metrics for one city/split.
    """

    def compute_all(
        self,
        dates:          Any,                    # pd.Series of dates
        y_true:         np.ndarray,             # binary labels
        p_hat:          np.ndarray,             # calibrated probabilities
        event_anchors:  Optional[List[str]] = None,
        city_slug:      str                 = "unknown",
        alert_threshold: float              = 0.50,
        pre_event_days: int                 = 2,
    ) -> OperationalMetrics:
        """
        Parameters
        ----------
        dates           : pd.Series aligned to y_true/p_hat
        y_true          : binary ground-truth labels (1 = event)
        p_hat           : calibrated P(event) per observation
        event_anchors   : known extreme event ISO date strings
        city_slug       : city identifier
        alert_threshold : probability threshold for binary alert classification
        pre_event_days  : days before event to check for lead-time
        """
        import pandas as pd

        dates  = pd.to_datetime(dates).reset_index(drop=True)
        y_true = np.asarray(y_true, dtype=float)
        p_hat  = np.asarray(p_hat,  dtype=float)
        n      = len(p_hat)

        metrics = OperationalMetrics(
            city_slug      = city_slug,
            n_observations = n,
            alert_threshold= alert_threshold,
        )

        # 1. Precision@Top-K
        metrics.precision_top1  = self._precision_at_topk(y_true, p_hat, 0.01)
        metrics.precision_top5  = self._precision_at_topk(y_true, p_hat, 0.05)
        metrics.precision_top10 = self._precision_at_topk(y_true, p_hat, 0.10)

        # 2. Event Recall
        metrics.event_recall = self._event_recall(
            dates, y_true, p_hat, event_anchors or [],
            alert_threshold, pre_event_days
        )

        # 3. Lead Time
        metrics.lead_time = self._lead_time(
            dates, p_hat, event_anchors or [],
            alert_threshold, pre_event_days
        )

        # 4. False Alarm Rate
        metrics.false_alarm = self._false_alarm_rate(
            dates, y_true, p_hat, alert_threshold
        )

        # 5. Alert Stability
        metrics.alert_stability = self._alert_stability(p_hat, alert_threshold)

        # 6. Persistence Score
        metrics.persistence = self._persistence_score(
            dates, p_hat, event_anchors or [],
            alert_threshold, pre_event_days
        )

        logger.info("[%s] Operational metrics computed:\n%s",
                    city_slug, metrics.summary())
        return metrics

    # ── 1. Precision@Top-K ────────────────────────────────────────

    def _precision_at_topk(
        self,
        y_true: np.ndarray,
        p_hat:  np.ndarray,
        k:      float,
    ) -> Optional[PrecisionAtTopK]:
        n     = len(p_hat)
        n_top = max(1, int(n * k))
        idx   = np.argsort(-p_hat)[:n_top]
        tp    = int(y_true[idx].sum())
        return PrecisionAtTopK(
            k_pct     = k,
            n_top     = n_top,
            precision = round(tp / max(n_top, 1), 4),
            n_true_pos= tp,
        )

    # ── 2. Event Recall ───────────────────────────────────────────

    def _event_recall(
        self,
        dates:           Any,
        y_true:          np.ndarray,
        p_hat:           np.ndarray,
        event_anchors:   List[str],
        alert_threshold: float,
        pre_event_days:  int,
    ) -> EventRecallResult:
        import pandas as pd
        detected  = []
        missed    = []
        for event_str in event_anchors:
            event_dt = pd.Timestamp(event_str)
            # Window: [event - pre_event_days, event + 1]
            window_mask = (
                (dates >= event_dt - pd.Timedelta(days=pre_event_days))
                & (dates <= event_dt + pd.Timedelta(days=1))
            )
            if not window_mask.any():
                missed.append(event_str)
                continue
            if (p_hat[window_mask] >= alert_threshold).any():
                detected.append(event_str)
            else:
                missed.append(event_str)

        n = len(event_anchors)
        return EventRecallResult(
            n_events        = n,
            n_detected      = len(detected),
            recall          = round(len(detected) / max(n, 1), 4),
            missed_events   = missed,
            detected_events = detected,
        )

    # ── 3. Lead Time ──────────────────────────────────────────────

    def _lead_time(
        self,
        dates:           Any,
        p_hat:           np.ndarray,
        event_anchors:   List[str],
        alert_threshold: float,
        pre_event_days:  int,
    ) -> LeadTimeResult:
        import pandas as pd
        lead_days: List[float] = []
        by_event:  Dict[str, float] = {}

        for event_str in event_anchors:
            event_dt = pd.Timestamp(event_str)
            # Look back pre_event_days+5 to capture early warnings
            lookback = pre_event_days + 5
            pre_mask = (
                (dates >= event_dt - pd.Timedelta(days=lookback))
                & (dates <  event_dt)
            )
            if not pre_mask.any():
                continue
            pre_dates = dates[pre_mask]
            pre_probs = p_hat[pre_mask]

            # Earliest day with p_hat >= threshold
            alert_mask = pre_probs >= alert_threshold
            if not alert_mask.any():
                continue
            first_alert_date = pre_dates[alert_mask].min()
            lead = float((event_dt - first_alert_date).days)
            lead_days.append(lead)
            by_event[event_str] = round(lead, 1)

        if not lead_days:
            return LeadTimeResult(
                n_events_with_lead=0,
                mean_days=0.0, median_days=0.0,
                p90_days=0.0,  max_days=0.0,
                by_event={},
            )

        arr = np.array(lead_days)
        return LeadTimeResult(
            n_events_with_lead = len(arr),
            mean_days          = round(float(arr.mean()), 2),
            median_days        = round(float(np.median(arr)), 2),
            p90_days           = round(float(np.percentile(arr, 90)), 2),
            max_days           = round(float(arr.max()), 2),
            by_event           = by_event,
        )

    # ── 4. False Alarm Rate ───────────────────────────────────────

    def _false_alarm_rate(
        self,
        dates:           Any,
        y_true:          np.ndarray,
        p_hat:           np.ndarray,
        alert_threshold: float,
    ) -> FalseAlarmResult:
        import pandas as pd

        alerts = p_hat >= alert_threshold
        fa     = alerts & (y_true == 0)
        total_alerts  = int(alerts.sum())
        false_alarms  = int(fa.sum())
        far_per_100   = round(100 * false_alarms / max(total_alerts, 1), 2)

        # By month
        by_month: Dict[int, float] = {}
        for m in range(1, 13):
            mask = dates.dt.month == m
            if not mask.any():
                continue
            m_alerts = int(alerts[mask].sum())
            m_fa     = int(fa[mask].sum())
            by_month[m] = round(100 * m_fa / max(m_alerts, 1), 2)

        # By season
        season_map = {12: "Winter", 1: "Winter", 2: "Winter",
                      3: "Spring", 4: "Spring", 5: "Spring",
                      6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
                      10: "Autumn", 11: "Autumn"}
        seasons = dates.dt.month.map(season_map)
        by_season: Dict[str, float] = {}
        for season in ["Winter", "Spring", "Monsoon", "Autumn"]:
            mask = seasons == season
            if not mask.any():
                continue
            s_alerts = int(alerts[mask].sum())
            s_fa     = int(fa[mask].sum())
            by_season[season] = round(100 * s_fa / max(s_alerts, 1), 2)

        return FalseAlarmResult(
            false_alarms  = false_alarms,
            total_alerts  = total_alerts,
            far_per_100   = far_per_100,
            by_month      = by_month,
            by_season     = by_season,
        )

    # ── 5. Alert Stability ────────────────────────────────────────

    def _alert_stability(
        self,
        p_hat:           np.ndarray,
        alert_threshold: float,
    ) -> AlertStabilityResult:
        binary = (p_hat >= alert_threshold).astype(int)
        # Count transitions: 0→1 or 1→0
        transitions = int(np.sum(np.diff(binary) != 0))
        n = len(binary)
        volatility = round(transitions / max(n - 1, 1), 4)

        # Single-day spikes: high with no high neighbours
        spikes = 0
        for i in range(1, n - 1):
            if binary[i] == 1 and binary[i-1] == 0 and binary[i+1] == 0:
                spikes += 1

        return AlertStabilityResult(
            oscillation_count   = transitions,
            volatility_score    = volatility,
            n_single_day_spikes = spikes,
        )

    # ── 6. Persistence Score ──────────────────────────────────────

    def _persistence_score(
        self,
        dates:           Any,
        p_hat:           np.ndarray,
        event_anchors:   List[str],
        alert_threshold: float,
        pre_event_days:  int,
    ) -> PersistenceResult:
        import pandas as pd

        persistence_days: List[float] = []
        by_event: Dict[str, float] = {}

        for event_str in event_anchors:
            event_dt = pd.Timestamp(event_str)
            window   = pre_event_days + 7
            pre_mask = (
                (dates >= event_dt - pd.Timedelta(days=window))
                & (dates <  event_dt)
            )
            if not pre_mask.any():
                continue
            pre_probs = p_hat[pre_mask]
            # Consecutive high-risk days before event
            above = (pre_probs >= alert_threshold).astype(int)
            # Longest consecutive run
            max_run = _longest_run(above)
            persistence_days.append(float(max_run))
            by_event[event_str] = float(max_run)

        if not persistence_days:
            return PersistenceResult(
                n_events_assessed=0,
                mean_persistence=0.0, median_persistence=0.0,
                p10_persistence=0.0, by_event={},
            )

        arr = np.array(persistence_days)
        return PersistenceResult(
            n_events_assessed  = len(arr),
            mean_persistence   = round(float(arr.mean()), 2),
            median_persistence = round(float(np.median(arr)), 2),
            p10_persistence    = round(float(np.percentile(arr, 10)), 2),
            by_event           = by_event,
        )


# ── Utility ───────────────────────────────────────────────────────────────

def _longest_run(arr: np.ndarray) -> int:
    """Longest consecutive run of 1s in a binary array."""
    if len(arr) == 0:
        return 0
    max_run = current = 0
    for v in arr:
        if v == 1:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run
