"""
HydroGuard-AI — Label Engine (Weak Supervision Orchestrator)
=============================================================
Aggregates outputs from L1–L7 labeling functions via weighted majority vote
to produce final weak labels for LightGBM fusion model training.

Locked thresholds (Phase 3 spec):
  POSITIVE_THRESHOLD = 0.45  (weighted positive vote fraction)
  NEGATIVE_THRESHOLD = 0.15  (weighted negative vote fraction)
  Between → abstain (-1)

Aggregation:
  positive_score = sum(weight_i for rules i where label_i == 1)
                 / sum(all weights)
  if positive_score >= 0.45 → label = 1
  if positive_score <= 0.15 → label = 0
  else                      → label = -1 (abstain)

Event type assignment (priority order):
  1. "cloudburst"   if L2 fired + L1 >= 1.5x climo + L3 fired
  2. "flash_flood"  if L1 >= 2.5x climo + L6 fired
  3. "heavy_rain"   if L1 >= 1.5x climo
  4. None otherwise
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from app.ml.labeling.rules import (
    rule_rainfall_intensity,
    rule_pressure_drop,
    rule_humidity,
    rule_cloud_concentration,
    rule_tdew_spread,
    rule_persistence,
    rule_historical_extreme,
    LabelResult,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  LOCKED constants
# ─────────────────────────────────────────────────────────────

POSITIVE_THRESHOLD = 0.45   # ← LOCKED, do not change
NEGATIVE_THRESHOLD = 0.15   # ← LOCKED, do not change

RULE_WEIGHTS: Dict[str, float] = {
    "L1": 1.0,  # Rainfall intensity
    "L2": 1.0,  # Pressure drop
    "L3": 0.8,  # Humidity
    "L4": 0.7,  # Cloud concentration
    "L5": 0.9,  # T-Td spread
    "L6": 1.2,  # Persistence (highest — multi-indicator confirmation)
    "L7": 0.8,  # Historical extreme
}
_TOTAL_WEIGHT = sum(RULE_WEIGHTS.values())   # 6.4


# ─────────────────────────────────────────────────────────────
#  Output model
# ─────────────────────────────────────────────────────────────

@dataclass
class LabelOutput:
    weak_label:      int           # -1 (abstain) | 0 (no event) | 1 (event)
    weak_label_conf: float         # 0–1
    event_type:      Optional[str] # "cloudburst"|"flash_flood"|"heavy_rain"|None
    rule_votes:      Dict[str, int]    # {"L1": 1, "L2": -1, ...}  ← B: rule_votes JSONB
    rule_scores:     Dict[str, float]  # raw confidence per rule
    weighted_vote:   float             # final aggregated positive score


# ─────────────────────────────────────────────────────────────
#  Engine
# ─────────────────────────────────────────────────────────────

class LabelEngine:
    """
    Orchestrates all 7 labeling functions and aggregates to a final weak label.

    Parameters
    ----------
    climatology : ClimatologyStore instance (or None — L7 will abstain)
    weights     : custom weights dict (default: RULE_WEIGHTS)
    """

    def __init__(self, climatology=None, weights: Dict[str, float] = None):
        self._clim    = climatology
        self._weights = weights or RULE_WEIGHTS

    # ── Single row ───────────────────────────────────────────

    def label_row(
        self,
        features: Dict[str, Any],
        city_slug: str,
        month: int,
        recent_votes: Optional[List[int]] = None,
    ) -> LabelOutput:
        """
        Apply all labeling functions to one feature dict and aggregate.

        Parameters
        ----------
        features     : dict with keys matching EnrichedFeatures fields
        city_slug    : city slug for climatology lookup
        month        : calendar month (1-12)
        recent_votes : last N weak labels for L6 (persistence)
        """
        def _get(key: str, default=None):
            return features.get(key, default)

        prcp            = float(_get("prcp", 0.0) or 0.0)
        humidity        = float(_get("humidity", 50.0) or 50.0)
        cloud_cover     = float(_get("cloud_cover", 0.0) or 0.0)
        prcp_climo_pct  = float(_get("prcp_climo_pct", 1.0) or 1.0)
        pressure_d3h    = _get("pressure_delta_3h")
        pressure_d6h    = _get("pressure_delta_6h")
        tdew_spread     = _get("tdew_spread")

        if tdew_spread is None:
            tavg      = float(_get("tavg", 25.0) or 25.0)
            dew_point = float(_get("dew_point", tavg - 10.0) or (tavg - 10.0))
            tdew_spread = tavg - dew_point

        # Run all functions
        results: Dict[str, LabelResult] = {
            "L1": rule_rainfall_intensity(prcp, prcp_climo_pct),
            "L2": rule_pressure_drop(pressure_d3h, pressure_d6h),
            "L3": rule_humidity(humidity, prcp),
            "L4": rule_cloud_concentration(cloud_cover, prcp_climo_pct),
            "L5": rule_tdew_spread(tdew_spread, prcp),
            "L6": rule_persistence(recent_votes or []),
            "L7": rule_historical_extreme(
                features, self._clim, city_slug, month
            ),
        }

        # Aggregate: weighted positive vote fraction
        positive_weight = 0.0
        for key, (label, conf, score) in results.items():
            if label == 1:
                positive_weight += self._weights.get(key, 1.0)

        weighted_vote = positive_weight / _TOTAL_WEIGHT

        # Decision
        if weighted_vote >= POSITIVE_THRESHOLD:
            weak_label      = 1
            weak_label_conf = float(np.clip(weighted_vote, 0.0, 1.0))
        elif weighted_vote <= NEGATIVE_THRESHOLD:
            weak_label      = 0
            weak_label_conf = float(np.clip(1.0 - weighted_vote, 0.0, 1.0))
        else:
            weak_label      = -1
            weak_label_conf = 0.0

        # Event type classification
        event_type = self._classify_event(
            results=results,
            prcp_climo_pct=prcp_climo_pct,
        )

        # Build rule_votes dict (Addition B: stored as JSONB in label_events)
        rule_votes  = {k: v[0] for k, v in results.items()}
        rule_scores = {k: round(v[1], 4) for k, v in results.items()}

        return LabelOutput(
            weak_label      = weak_label,
            weak_label_conf = round(weak_label_conf, 4),
            event_type      = event_type,
            rule_votes      = rule_votes,
            rule_scores     = rule_scores,
            weighted_vote   = round(weighted_vote, 4),
        )

    # ── DataFrame batch ──────────────────────────────────────

    def label_dataframe(
        self,
        df: "pd.DataFrame",
        city_slug: str,
    ) -> "pd.DataFrame":
        """
        Add weak label columns to a DataFrame. Handles L6 persistence
        by maintaining a rolling vote history across rows.

        Adds columns:
          weak_label, weak_label_conf, event_type, rule_votes (JSON-serialisable dict)

        Parameters
        ----------
        df        : DataFrame with feature columns (must include date/month)
        city_slug : city slug
        """
        import pandas as pd
        import json

        results_rows = []
        recent_votes: List[int] = []

        for _, row in df.iterrows():
            month = int(row.get("month", 1) if hasattr(row, "get") else 1)
            feat  = row.to_dict() if hasattr(row, "to_dict") else dict(row)

            out = self.label_row(feat, city_slug, month, recent_votes)
            results_rows.append({
                "weak_label":      out.weak_label,
                "weak_label_conf": out.weak_label_conf,
                "event_type":      out.event_type,
                "rule_votes":      out.rule_votes,   # keep as dict for now
                "weighted_vote":   out.weighted_vote,
            })
            # Update recent votes for L6 (only include definitive labels)
            if out.weak_label in (0, 1):
                recent_votes.append(out.weak_label)
                if len(recent_votes) > 10:
                    recent_votes = recent_votes[-10:]

        label_df = pd.DataFrame(results_rows, index=df.index)

        df = df.copy()
        df["weak_label"]      = label_df["weak_label"]
        df["weak_label_conf"] = label_df["weak_label_conf"]
        df["event_type"]      = label_df["event_type"]
        df["rule_votes"]      = label_df["rule_votes"].apply(
            lambda x: json.dumps(x) if isinstance(x, dict) else x
        )

        pos_count = (df["weak_label"] == 1).sum()
        neg_count = (df["weak_label"] == 0).sum()
        abs_count = (df["weak_label"] == -1).sum()
        logger.info(
            "[%s] Labels: pos=%d (%.1f%%), neg=%d (%.1f%%), abstain=%d (%.1f%%)",
            city_slug,
            pos_count, 100 * pos_count / max(len(df), 1),
            neg_count, 100 * neg_count / max(len(df), 1),
            abs_count, 100 * abs_count / max(len(df), 1),
        )

        return df

    # ── Event type classification ────────────────────────────

    def _classify_event(
        self,
        results: Dict[str, LabelResult],
        prcp_climo_pct: float,
    ) -> Optional[str]:
        """Assign event_type based on labeling function outputs."""
        l1_fired    = results["L1"][0] == 1
        l2_fired    = results["L2"][0] == 1
        l3_fired    = results["L3"][0] == 1
        l6_fired    = results["L6"][0] == 1

        # Priority 1: cloudburst (pressure drop + extreme rain + humidity)
        if l2_fired and prcp_climo_pct >= 1.5 and l3_fired:
            return "cloudburst"

        # Priority 2: flash flood (extreme rain + persistent)
        if prcp_climo_pct >= 2.5 and l6_fired:
            return "flash_flood"

        # Priority 3: heavy rain
        if l1_fired:
            return "heavy_rain"

        return None
