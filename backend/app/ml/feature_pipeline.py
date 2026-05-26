"""
HydroGuard-AI — Feature Pipeline V2
=====================================
Converts raw weather inputs + rolling history + climatology context
into the EnrichedFeatures dataclass consumed by:
  - WeatherDataPreprocessorV2 (for AE/TCN)
  - FusionModel (direct feature dict for LightGBM)
  - LabelEngine (for weak supervision labeling)

Stages:
  1. Validation & typing
  2. Static derivations (no history): temp_range, tdew_spread, moisture_flux
  3. Rolling window deltas (Redis-backed): pressure_delta_*, rain_rate_*, cloud_jump_*
  4. Climatological context: prcp_climo_pct, pressure_climo_z, humidity_climo_pct
  5. Temporal features: month, day, dayofweek, is_weekend, is_monsoon_month, season
  6. City prior: vulnerability, is_flash_flood_prone
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MONSOON_MONTHS      = {6, 7, 8, 9}
FLASH_FLOOD_CITIES  = {"islamabad", "rawalpindi", "peshawar", "lahore", "karachi"}

# Arabian Sea cyclone season: May–November (peak Jun–Oct)
ARABIAN_SEA_CYCLONE_SEASON = {5, 6, 7, 8, 9, 10, 11}


def _karachi_coastal_features(
    raw: Dict[str, Any],
    month: int,
    day: int,
    pressure_delta_3h: Optional[float],
    pressure_delta_6h: Optional[float],
    humidity_delta_3h: Optional[float],
    rain_accumulation_6h: Optional[float],
) -> Dict[str, float]:
    """
    Karachi-specific coastal feature engineering.

    Karachi sits on the Arabian Sea coast: its flood/cloudburst risk
    is driven by completely different mechanisms than northern monsoon systems:
      - Sea-breeze instability (land-sea thermal gradient)
      - Cyclonic systems from the Arabian Sea
      - Urban drainage stress (flat terrain, dense impervious surface)
      - Humidity persistence from sea moisture
      - Coastal pressure gradients

    These features are derived from existing weather variables without
    external APIs. When Karachi is retrained with these features added to
    its preprocessor, discrimination will improve significantly.
    """
    humidity    = float(raw.get("humidity",    50.0) or 50.0)
    pressure    = float(raw.get("pressure",    1013.0) or 1013.0)
    tmax        = float(raw.get("tmax",        30.0) or 30.0)
    tmin        = float(raw.get("tmin",        25.0) or 25.0)
    tavg        = float(raw.get("tavg",        (tmax + tmin) / 2) or (tmax + tmin) / 2)
    dew_point   = float(raw.get("dew_point",   tavg - 5.0) or (tavg - 5.0))
    wspd        = float(raw.get("wspd",        0.0) or 0.0)
    prcp        = float(raw.get("prcp",        0.0) or 0.0)
    cloud_cover = float(raw.get("cloud_cover", 0.0) or 0.0)

    # ── Sea surface temperature anomaly proxy ─────────────────────────────
    # Arabian Sea SST seasonal baseline (°C): peaks Jun-Sep ~29-30°C
    # Proxy: compare tavg to seasonal SST baseline; warmer = more evaporation
    sst_baseline_by_month = {
        1: 24.5, 2: 24.0, 3: 25.0, 4: 27.0, 5: 28.5,
        6: 29.5, 7: 29.5, 8: 29.0, 9: 28.5, 10: 27.5,
        11: 26.0, 12: 25.0,
    }
    sst_baseline    = sst_baseline_by_month.get(month, 27.0)
    sst_anomaly     = tavg - sst_baseline        # positive = anomalously warm

    # ── Sea-breeze instability ────────────────────────────────────────────
    # Sea breeze strengthens when land is much hotter than sea.
    # High diurnal range + high humidity = convective instability
    diurnal_range         = max(tmax - tmin, 0.0)
    sea_breeze_instability = diurnal_range * (humidity / 100.0) * (1 - pressure / 1020.0)

    # ── Cyclone proximity proxy ───────────────────────────────────────────
    # Actual cyclone track data not available — use concurrent indicators:
    # rapid pressure drop + high wind + high humidity in cyclone season
    cyclone_season        = int(month in ARABIAN_SEA_CYCLONE_SEASON)
    pressure_drop_3h      = abs(pressure_delta_3h) if pressure_delta_3h else 0.0
    pressure_drop_6h      = abs(pressure_delta_6h) if pressure_delta_6h else 0.0
    cyclone_proxy         = float(
        cyclone_season
        * (pressure_drop_3h / 5.0)      # normalise: 5 hPa/3h = strong signal
        * min(wspd / 30.0, 1.0)          # normalise: 30 km/h
        * (humidity / 100.0)
    )

    # ── Humidity persistence ─────────────────────────────────────────────
    # Sustained high humidity (slow-moving marine air mass) = flooding risk
    # Proxy: current humidity × (1 - |humidity_delta_3h| / 20)
    # Delta near 0 = humidity has been stable (persistent marine air)
    hum_delta   = abs(humidity_delta_3h) if humidity_delta_3h else 5.0  # assume moderate change
    hum_persist = (humidity / 100.0) * (1.0 - min(hum_delta / 30.0, 1.0))

    # ── Coastal moisture flux ─────────────────────────────────────────────
    # Enhanced moisture_flux for onshore winds (generic direction assumed)
    coastal_moisture = (humidity / 100.0) * min(wspd / 20.0, 1.0) * (1 - pressure / 1020.0)

    # ── Urban drainage stress ─────────────────────────────────────────────
    # Karachi has poor drainage; even moderate rain causes flooding
    # Stress = rain accumulation weighted by ground saturation proxy
    rain_acc   = rain_accumulation_6h or prcp * 6    # rough proxy if no history
    drain_stress = min(rain_acc / 30.0, 1.0) * (humidity / 100.0)

    # ── Tidal influence proxy ─────────────────────────────────────────────
    # Arabian Sea has mixed semi-diurnal tides (~2–3m range in Karachi)
    # Proxy: sin-based seasonal + intra-month variation (no real tidal model)
    import math
    tidal_proxy = 0.5 * (
        math.sin(2 * math.pi * month / 12)     # seasonal
        + math.sin(2 * math.pi * day / 29.5)   # lunar month proxy
    )

    # ── Pressure gradient proxy ───────────────────────────────────────────
    # Large 6h pressure gradient = organised convective system approaching
    pressure_gradient = (pressure_drop_6h / 10.0)   # normalise: 10 hPa/6h

    return {
        "sst_anomaly":           round(sst_anomaly,          4),
        "sea_breeze_instability":round(sea_breeze_instability, 4),
        "cyclone_proximity":     round(min(cyclone_proxy, 1.0), 4),
        "humidity_persistence":  round(hum_persist,          4),
        "coastal_moisture_flux": round(coastal_moisture,     4),
        "urban_drainage_stress": round(drain_stress,         4),
        "tidal_proxy":           round(tidal_proxy,          4),
        "coastal_pressure_grad": round(pressure_gradient,    4),
        "cyclone_season":        float(cyclone_season),
    }


def _slug(city: str) -> str:
    return city.strip().lower().replace(" ", "_").replace("-", "_")


# ─────────────────────────────────────────────────────────────
#  EnrichedFeatures — the single intermediate representation
# ─────────────────────────────────────────────────────────────

@dataclass
class EnrichedFeatures:
    # ── Raw inputs ─────────────────────────────────────────
    city_slug:   str
    prcp:        float
    humidity:    float
    pressure:    float
    cloud_cover: float
    tmax:        float
    tmin:        float
    tavg:        float
    temp_range:  float
    dew_point:   float
    wspd:        float

    # ── Static derivations ─────────────────────────────────
    tdew_spread:   float          # tavg - dew_point  (moisture saturation proxy)
    moisture_flux: float          # (humidity/100) * wspd (horizontal transport)

    # ── Rolling window deltas (None = history unavailable) ─
    pressure_delta_3h:    Optional[float] = None
    pressure_delta_6h:    Optional[float] = None
    humidity_delta_3h:    Optional[float] = None
    rain_rate_1h:         Optional[float] = None
    rain_accumulation_3h: Optional[float] = None
    rain_accumulation_6h: Optional[float] = None
    cloud_jump_3h:        Optional[float] = None

    # ── Climatological context ─────────────────────────────
    prcp_climo_pct:    float = 1.0   # prcp / city×month q90
    pressure_climo_z:  float = 0.0   # z-score vs city×month baseline
    humidity_climo_pct: float = 1.0  # humidity / city×month q90

    # ── Temporal features ──────────────────────────────────
    month:            int   = 1
    day:              int   = 1
    dayofweek:        int   = 0
    is_weekend:       int   = 0
    is_monsoon_month: int   = 0
    season:           str   = "Winter"

    # ── City prior ─────────────────────────────────────────
    vulnerability:        float = 0.65
    is_flash_flood_prone: int   = 0

    # ── Karachi coastal features (None for non-coastal cities) ─
    sst_anomaly:           Optional[float] = None
    sea_breeze_instability:Optional[float] = None
    cyclone_proximity:     Optional[float] = None
    humidity_persistence:  Optional[float] = None
    coastal_moisture_flux: Optional[float] = None
    urban_drainage_stress: Optional[float] = None
    tidal_proxy:           Optional[float] = None
    coastal_pressure_grad: Optional[float] = None
    cyclone_season:        Optional[float] = None

    # ── Observed at ────────────────────────────────────────
    observed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Flat dict for LightGBM fusion + label engine. Replaces None deltas with 0.0."""
        d = asdict(self)
        # Replace None rolling deltas with 0.0 (safe default: "no change from baseline")
        for key in (
            "pressure_delta_3h", "pressure_delta_6h", "humidity_delta_3h",
            "rain_rate_1h", "rain_accumulation_3h", "rain_accumulation_6h",
            "cloud_jump_3h",
        ):
            if d[key] is None:
                d[key] = 0.0
        # Coastal features: replace None with 0.0 (non-coastal cities have no signal)
        for key in (
            "sst_anomaly", "sea_breeze_instability", "cyclone_proximity",
            "humidity_persistence", "coastal_moisture_flux", "urban_drainage_stress",
            "tidal_proxy", "coastal_pressure_grad", "cyclone_season",
        ):
            if d[key] is None:
                d[key] = 0.0
        # Remove non-numeric fields
        d.pop("city_slug", None)
        d.pop("season", None)
        d.pop("observed_at", None)
        return d


# ─────────────────────────────────────────────────────────────
#  Season helper
# ─────────────────────────────────────────────────────────────

def _month_to_season(month: int) -> str:
    if month in (12, 1, 2):  return "Winter"
    if month in (3, 4, 5):   return "Spring"
    if month in (6, 7, 8):   return "Summer"   # includes monsoon
    return "Autumn"


# ─────────────────────────────────────────────────────────────
#  Pipeline entry point
# ─────────────────────────────────────────────────────────────

async def build_features(
    city_slug:        str,
    raw_weather:      Dict[str, Any],
    rolling_buffer=None,       # RollingWindowBuffer | None
    climatology=None,          # ClimatologyStore | None
    observed_at:      Optional[datetime] = None,
) -> EnrichedFeatures:
    """
    Full feature engineering pipeline.

    Parameters
    ----------
    city_slug     : normalised city slug (lowercase_underscore)
    raw_weather   : dict with keys matching WeatherSnapshot.to_feature_dict()
    rolling_buffer: RollingWindowBuffer singleton (or None -> no deltas)
    climatology   : ClimatologyStore singleton (or None -> default climo values)
    observed_at   : datetime of the observation (or None -> now UTC)

    Returns
    -------
    EnrichedFeatures -- complete feature set ready for preprocessor/fusion model.
    """
    now  = observed_at or datetime.now(timezone.utc)
    slug = _slug(city_slug)

    # ── 1. Extract raw inputs with safe defaults ─────────────
    prcp        = float(raw_weather.get("prcp",        0.0) or 0.0)
    humidity    = float(raw_weather.get("humidity",    50.0) or 50.0)
    pressure    = float(raw_weather.get("pressure",    1013.0) or 1013.0)
    cloud_cover = float(raw_weather.get("cloud_cover", 0.0) or 0.0)
    tmax        = float(raw_weather.get("tmax",        25.0) or 25.0)
    tmin        = float(raw_weather.get("tmin",        20.0) or 20.0)
    tavg        = float(raw_weather.get("tavg",        (tmax + tmin) / 2) or (tmax + tmin) / 2)
    dew_point   = float(raw_weather.get("dew_point",   tavg - 10.0) or (tavg - 10.0))
    wspd        = float(raw_weather.get("wspd",        0.0) or 0.0)
    temp_range  = float(raw_weather.get("temp_range",  tmax - tmin) or (tmax - tmin))

    # ── 2. Static derivations ────────────────────────────────
    tdew_spread   = tavg - dew_point                     # near 0 = near saturation
    moisture_flux = (humidity / 100.0) * wspd            # horizontal moisture transport

    # ── 3. Rolling window deltas ─────────────────────────────
    pressure_delta_3h    = None
    pressure_delta_6h    = None
    humidity_delta_3h    = None
    rain_rate_1h         = None
    rain_accumulation_3h = None
    rain_accumulation_6h = None
    cloud_jump_3h        = None

    if rolling_buffer is not None:
        try:
            deltas = await rolling_buffer.get_deltas(
                city_slug  = slug,
                current_ts = now.timestamp(),
            )
            pressure_delta_3h    = deltas.pressure_delta_3h
            pressure_delta_6h    = deltas.pressure_delta_6h
            humidity_delta_3h    = deltas.humidity_delta_3h
            rain_rate_1h         = deltas.rain_rate_1h
            rain_accumulation_3h = deltas.rain_accumulation_3h
            rain_accumulation_6h = deltas.rain_accumulation_6h
            cloud_jump_3h        = deltas.cloud_jump_3h
        except Exception as exc:
            logger.debug("Rolling deltas unavailable for %s: %s", slug, exc)

    # ── 4. Climatological context ────────────────────────────
    prcp_climo_pct     = 1.0
    pressure_climo_z   = 0.0
    humidity_climo_pct = 1.0

    if climatology is not None:
        try:
            month = now.month
            prcp_climo_pct     = climatology.prcp_climo_pct(slug, month, prcp)
            pressure_climo_z   = climatology.pressure_climo_z(slug, month, pressure)
            humidity_climo_pct = climatology.humidity_climo_pct(slug, month, humidity)
        except Exception as exc:
            logger.debug("Climatology context failed for %s: %s", slug, exc)

    # ── 5. Temporal features ─────────────────────────────────
    month     = now.month
    day       = now.day
    dow       = now.weekday()
    is_weekend        = int(dow >= 5)
    is_monsoon_month  = int(month in MONSOON_MONTHS)
    season            = _month_to_season(month)

    # ── 6. City prior ────────────────────────────────────────
    vulnerability        = 0.65   # default
    is_flash_flood_prone = int(slug in FLASH_FLOOD_CITIES)

    # Try to get city vulnerability from registry
    try:
        from app.services.city_model_service import CITY_METADATA
        meta = CITY_METADATA.get(slug, {})
        vulnerability = float(meta.get("vulnerability", 0.65))
    except Exception:
        pass

    # ── 7. Karachi coastal features ──────────────────────────
    coastal: Dict[str, Optional[float]] = {
        "sst_anomaly": None, "sea_breeze_instability": None,
        "cyclone_proximity": None, "humidity_persistence": None,
        "coastal_moisture_flux": None, "urban_drainage_stress": None,
        "tidal_proxy": None, "coastal_pressure_grad": None, "cyclone_season": None,
    }
    if slug == "karachi":
        coastal = _karachi_coastal_features(
            raw_weather, month, day,
            pressure_delta_3h, pressure_delta_6h,
            humidity_delta_3h, rain_accumulation_6h,
        )

    return EnrichedFeatures(
        city_slug    = slug,
        prcp         = prcp,
        humidity     = humidity,
        pressure     = pressure,
        cloud_cover  = cloud_cover,
        tmax         = tmax,
        tmin         = tmin,
        tavg         = tavg,
        temp_range   = temp_range,
        dew_point    = dew_point,
        wspd         = wspd,
        tdew_spread  = tdew_spread,
        moisture_flux= moisture_flux,
        pressure_delta_3h    = pressure_delta_3h,
        pressure_delta_6h    = pressure_delta_6h,
        humidity_delta_3h    = humidity_delta_3h,
        rain_rate_1h         = rain_rate_1h,
        rain_accumulation_3h = rain_accumulation_3h,
        rain_accumulation_6h = rain_accumulation_6h,
        cloud_jump_3h        = cloud_jump_3h,
        prcp_climo_pct       = prcp_climo_pct,
        pressure_climo_z     = pressure_climo_z,
        humidity_climo_pct   = humidity_climo_pct,
        month             = month,
        day               = day,
        dayofweek         = dow,
        is_weekend        = is_weekend,
        is_monsoon_month  = is_monsoon_month,
        season            = season,
        vulnerability     = vulnerability,
        is_flash_flood_prone = is_flash_flood_prone,
        # Karachi coastal features (None for all other cities)
        sst_anomaly           = coastal.get("sst_anomaly"),
        sea_breeze_instability= coastal.get("sea_breeze_instability"),
        cyclone_proximity     = coastal.get("cyclone_proximity"),
        humidity_persistence  = coastal.get("humidity_persistence"),
        coastal_moisture_flux = coastal.get("coastal_moisture_flux"),
        urban_drainage_stress = coastal.get("urban_drainage_stress"),
        tidal_proxy           = coastal.get("tidal_proxy"),
        coastal_pressure_grad = coastal.get("coastal_pressure_grad"),
        cyclone_season        = coastal.get("cyclone_season"),
        observed_at       = now,
    )


def features_to_fusion_dict(ef: EnrichedFeatures) -> Dict[str, float]:
    """
    Extract the 16 features used by FusionModel (LightGBM).
    ae_percentile and tcn_percentile are added by the caller after branch scoring.
    ae_variance and tcn_variance likewise.
    """
    d = ef.to_dict()
    return {
        "pressure_delta_3h":    d["pressure_delta_3h"],
        "pressure_delta_6h":    d["pressure_delta_6h"],
        "rain_rate_1h":         d["rain_rate_1h"],
        "rain_accumulation_3h": d["rain_accumulation_3h"],
        "prcp_climo_pct":       d["prcp_climo_pct"],
        "humidity_climo_pct":   d["humidity_climo_pct"],
        "moisture_flux":        d["moisture_flux"],
        "tdew_spread":          d["tdew_spread"],
        "cloud_jump_3h":        d["cloud_jump_3h"],
        "month":                float(d["month"]),
        "is_monsoon_month":     float(d["is_monsoon_month"]),
        "vulnerability":        d["vulnerability"],
    }
