"""
HydroGuard-AI — Labeling Functions (Weak Supervision)
=======================================================
Seven physics-based labeling functions that produce weak labels
(positive=1, negative=0, abstain=-1) with associated confidence scores.

All functions share the signature:
    (args...) -> tuple[int, float, float]
    # (label: -1|0|1, confidence: 0–1, rule_score: 0–1)

Thresholds are LOCKED per Phase 3 spec:
  L1 rainfall:  positive >= 2.5x climo q90 (conf 1.0) or >= 1.5x (conf 0.7)
                negative <= 0.3x climo q90 (conf 0.9)
  L2 pressure:  positive drop <= -3.0 hPa/3h (conf 0.9) or <= -1.5 (conf 0.6)
                negative rise >= +1.5 hPa/3h (conf 0.8)
  L3 humidity:  positive >= 90% AND prcp >= 10 mm (conf 0.8)
                negative <= 60% (conf 0.8)
  L4 cloud:     positive >= 90% AND prcp_climo_pct >= 1.5 (conf 0.75)
                negative <= 30% (conf 0.7)
  L5 tdew:      positive T-Td <= 3°C AND prcp >= 5 mm (conf 0.85)
                negative T-Td >= 15°C (conf 0.7)
  L6 persist:   positive sum(last 3 labels == 1) >= 2 (conf 0.90)
                negative sum(last 3 labels == 0) >= 2 (conf 0.85)
  L7 extreme:   positive frac(features >= q99) >= 0.5 (conf 0.85)
                negative frac <= 0.1 (conf 0.75)
"""
from __future__ import annotations

from typing import Optional

# LabelResult = (label, confidence, rule_score)
LabelResult = tuple[int, float, float]

ABSTAIN  = (-1, 0.0, 0.0)


# ─────────────────────────────────────────────────────────────
#  L1 — Rainfall Intensity
# ─────────────────────────────────────────────────────────────

def rule_rainfall_intensity(
    prcp: float,
    prcp_climo_pct: float,
) -> LabelResult:
    """
    Positive: precipitation is climatologically extreme (>= 2.5x q90).
    Negative: precipitation is well below normal (<= 0.3x q90).
    """
    if prcp_climo_pct >= 2.5:
        return (1, 1.0, min(prcp_climo_pct / 3.0, 1.0))
    if prcp_climo_pct >= 1.5:
        return (1, 0.7, prcp_climo_pct / 2.5)
    if prcp_climo_pct <= 0.3:
        return (0, 0.9, 1.0 - prcp_climo_pct / 0.3)
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L2 — Pressure Drop
# ─────────────────────────────────────────────────────────────

def rule_pressure_drop(
    pressure_delta_3h: Optional[float],
    pressure_delta_6h: Optional[float] = None,
) -> LabelResult:
    """
    Positive: rapid surface pressure drop (mesoscale convection signature).
    Negative: stable or rising pressure.
    Uses 3h delta primarily, 6h as fallback.
    """
    delta = pressure_delta_3h
    if delta is None:
        delta = pressure_delta_6h
    if delta is None:
        return ABSTAIN

    if delta <= -3.0:
        score = min(abs(delta) / 6.0, 1.0)
        return (1, 0.9, score)
    if delta <= -1.5:
        score = abs(delta) / 3.0
        return (1, 0.6, score)
    if delta >= 1.5:
        score = min(delta / 5.0, 1.0)
        return (0, 0.8, score)
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L3 — Humidity
# ─────────────────────────────────────────────────────────────

def rule_humidity(
    humidity: float,
    prcp: float,
) -> LabelResult:
    """
    Positive: near-saturated atmosphere with active precipitation.
    Negative: clearly dry conditions.
    """
    if humidity >= 90 and prcp >= 10:
        score = min((humidity - 90) / 10.0 + prcp / 50.0, 1.0)
        return (1, 0.8, score)
    if humidity >= 85:
        score = (humidity - 85) / 15.0
        return (1, 0.5, score)
    if humidity <= 60:
        score = (60 - humidity) / 40.0
        return (0, 0.8, score)
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L4 — Cloud Concentration
# ─────────────────────────────────────────────────────────────

def rule_cloud_concentration(
    cloud_cover: float,
    prcp_climo_pct: float,
) -> LabelResult:
    """
    Positive: overcast sky with active precipitation anomaly.
    Negative: mostly clear conditions.
    """
    if cloud_cover >= 90 and prcp_climo_pct >= 1.5:
        score = min((cloud_cover - 90) / 10.0 + prcp_climo_pct / 3.0, 1.0)
        return (1, 0.75, score)
    if cloud_cover <= 30:
        score = (30 - cloud_cover) / 30.0
        return (0, 0.7, score)
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L5 — Dew-point Spread (T − Td)
# ─────────────────────────────────────────────────────────────

def rule_tdew_spread(
    tdew_spread: Optional[float],
    prcp: float,
) -> LabelResult:
    """
    Positive: near-saturated atmosphere (small T-Td spread) with precipitation.
    Negative: very dry atmosphere (large T-Td spread).
    tdew_spread = tavg - dew_point; near 0 = near saturation.
    """
    if tdew_spread is None:
        return ABSTAIN

    if tdew_spread <= 3.0 and prcp >= 5:
        score = min((3.0 - tdew_spread) / 3.0 + prcp / 30.0, 1.0)
        return (1, 0.85, score)
    if tdew_spread >= 15.0:
        score = min((tdew_spread - 15.0) / 15.0, 1.0)
        return (0, 0.7, score)
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L6 — Persistence
# ─────────────────────────────────────────────────────────────

def rule_persistence(
    recent_votes: list[int],
    window_size: int = 3,
) -> LabelResult:
    """
    Positive: majority of recent labels (from L1–L5) were positive.
    Negative: majority were negative.

    Parameters
    ----------
    recent_votes : list of recent weak labels (-1, 0, or 1)
                   from the last `window_size` observations.
    """
    if not recent_votes:
        return ABSTAIN

    votes = recent_votes[-window_size:] if len(recent_votes) > window_size \
            else recent_votes

    pos_count  = sum(1 for v in votes if v == 1)
    neg_count  = sum(1 for v in votes if v == 0)

    if pos_count >= 2:
        conf  = min(0.70 + 0.10 * pos_count, 0.90)
        score = pos_count / max(len(votes), 1)
        return (1, conf, score)

    if neg_count >= 2:
        conf  = min(0.70 + 0.075 * neg_count, 0.85)
        score = neg_count / max(len(votes), 1)
        return (0, conf, score)

    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L7 — Historical Extreme
# ─────────────────────────────────────────────────────────────

def rule_historical_extreme(
    feature_dict: dict,
    climatology,       # ClimatologyStore instance
    city_slug: str,
    month: int,
    q_threshold: float = 0.99,
) -> LabelResult:
    """
    Positive: multiple features simultaneously exceed their q99.
    Negative: all features well within normal range.

    Parameters
    ----------
    feature_dict : dict of feature_name -> float value
    climatology  : ClimatologyStore (or None → abstain)
    city_slug    : city slug for climatology lookup
    month        : calendar month (1-12)
    q_threshold  : quantile threshold for "extreme" (default: 0.99)
    """
    if climatology is None:
        return ABSTAIN

    WATCH_FEATURES = ["prcp", "humidity", "pressure", "cloud_cover"]
    n_checked  = 0
    n_extreme  = 0
    n_normal   = 0

    for feat in WATCH_FEATURES:
        val = feature_dict.get(feat)
        if val is None:
            continue

        try:
            stats = climatology.get_stats(city_slug, month, feat)
        except Exception:
            continue

        n_checked += 1
        q99 = stats.q99

        if feat == "pressure":
            # Low pressure is the anomaly, not high
            if val < (stats.mu - 2 * stats.sigma):
                n_extreme += 1
            elif val > stats.q50:
                n_normal += 1
        else:
            if val >= q99:
                n_extreme += 1
            elif val <= stats.q50:
                n_normal += 1

    if n_checked == 0:
        return ABSTAIN

    frac_extreme = n_extreme / n_checked
    frac_normal  = n_normal  / n_checked

    if frac_extreme >= 0.5:
        conf  = min(0.75 + 0.10 * frac_extreme, 0.85)
        return (1, conf, frac_extreme)

    if frac_normal >= 0.9:
        return (0, 0.75, frac_normal)

    return ABSTAIN
