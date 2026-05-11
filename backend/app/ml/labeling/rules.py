"""
HydroGuard-AI — Labeling Functions (Physics-Informed Weak Supervision) v3.3
=============================================================================
Ten physics-based labeling functions that produce weak labels.
Upgraded in v3.3: added L8 (EWI), L9 (pressure acceleration), L10 (instability).

All functions share the signature:
    (args...) -> tuple[int, float, float]
    # (label: -1|0|1, confidence: 0–1, rule_score: 0–1)

Original thresholds (L1–L7) unchanged.
New functions:
  L8 EWI:   Extreme Weather Index — combines rainfall, pressure drop,
            humidity saturation, cloud cover into a single physics score.
            positive EWI >= 0.55 (conf 0.90), negative EWI <= 0.20 (conf 0.85)
  L9 acc:   Pressure acceleration (ΔΔP). Rapid acceleration of pressure drop
            is a mesoscale convective system (MCS) onset signature.
            positive <= -1.5 hPa/step² (conf 0.85)
  L10 inst: Atmospheric instability proxy (moisture_flux × |Δpressure|).
            High value with small dew-point spread = high convective risk.
            positive >= 5.0 (conf 0.80)
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


# ─────────────────────────────────────────────────────────────
#  L8 — Extreme Weather Index (EWI)  [NEW v3.3]
# ─────────────────────────────────────────────────────────────

def rule_ewi(
    prcp:              float,
    pressure_delta:    Optional[float],
    humidity:          float,
    cloud_cover:       float,
    is_monsoon:        bool = False,
) -> LabelResult:
    """
    Physics-based Extreme Weather Index combining the four primary storm signals.

    EWI = 0.35·rain_norm + 0.30·pressure_drop_norm + 0.20·humidity_norm + 0.15·cloud_norm

    Monsoon season multiplier: ×1.15 (heightened sensitivity during active monsoon).

    Thresholds:
      positive: EWI >= 0.55 (conf 0.90)
      negative: EWI <= 0.20 (conf 0.85)
    """
    # Normalise each component to [0, 1]
    rain_norm    = float(min(max(prcp, 0.0) / 80.0, 1.0))
    # Pressure drop: more negative = more extreme
    pdelta       = float(pressure_delta) if pressure_delta is not None else 0.0
    pdrop_norm   = float(min(max(-pdelta, 0.0) / 10.0, 1.0))
    hum_norm     = float(max(humidity - 50.0, 0.0) / 50.0)
    cloud_norm   = float(cloud_cover / 100.0)

    ewi = 0.35 * rain_norm + 0.30 * pdrop_norm + 0.20 * hum_norm + 0.15 * cloud_norm

    if is_monsoon:
        ewi = min(ewi * 1.15, 1.0)

    if ewi >= 0.55:
        conf = min(0.80 + ewi * 0.20, 0.95)
        return (1, round(conf, 3), round(ewi, 4))
    if ewi <= 0.20:
        inv = 1.0 - ewi / 0.20
        return (0, round(0.75 + inv * 0.10, 3), round(1.0 - ewi, 4))
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L9 — Pressure Acceleration  [NEW v3.3]
# ─────────────────────────────────────────────────────────────

def rule_pressure_acceleration(
    pressure_accel: Optional[float],
) -> LabelResult:
    """
    Positive: rapid acceleration of pressure drop (ΔΔP <= -1.5 hPa/step²).
    This is a signature of mesoscale convective system (MCS) rapid development.

    Negative: steady or increasing pressure tendency (ΔΔP >= +0.5).
    """
    if pressure_accel is None:
        return ABSTAIN

    acc = float(pressure_accel)

    if acc <= -1.5:
        score = min(abs(acc) / 5.0, 1.0)
        conf  = min(0.75 + score * 0.15, 0.90)
        return (1, round(conf, 3), round(score, 4))
    if acc <= -0.5:
        score = abs(acc) / 1.5
        return (1, 0.60, round(score, 4))
    if acc >= 0.5:
        score = min(acc / 3.0, 1.0)
        return (0, 0.70, round(score, 4))
    return ABSTAIN


# ─────────────────────────────────────────────────────────────
#  L10 — Atmospheric Instability Proxy  [NEW v3.3]
# ─────────────────────────────────────────────────────────────

def rule_atm_instability(
    atm_instability: Optional[float],
    tdew_spread:     Optional[float] = None,
) -> LabelResult:
    """
    Positive: high moisture flux combined with pressure forcing and near-saturation.
    `atm_instability` = moisture_flux × |Δpressure| / tdew_spread (physics proxy).

    A high value means the atmosphere is simultaneously:
      1. Transporting large amounts of moisture (moisture_flux high)
      2. Under significant pressure forcing (|Δpressure| high)
      3. Near saturation (tdew_spread small → denominator small → index high)

    This combination is a reliable convective initiation precursor.
    """
    if atm_instability is None:
        return ABSTAIN

    inst = float(atm_instability)

    # Additional confirmation: near-saturation (optional)
    near_saturation = tdew_spread is not None and float(tdew_spread) <= 5.0

    if inst >= 8.0 or (inst >= 5.0 and near_saturation):
        score = min(inst / 15.0, 1.0)
        conf  = 0.85 if near_saturation else 0.75
        return (1, round(conf, 3), round(score, 4))

    if inst >= 5.0:
        score = inst / 10.0
        return (1, 0.70, round(score, 4))

    if inst <= 0.5:
        return (0, 0.75, 0.90)

    return ABSTAIN
