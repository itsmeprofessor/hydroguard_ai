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
if __name__ == "__main__":
    import asyncio

    async def _test():
        sample_weather = {
            "prcp": 12.3,
            "humidity": 78,
            "pressure": 1008,
            "cloud_cover": 65,
            "tmax": 31,
            "tmin": 24,
            "dew_point": 22,
            "wspd": 5.2
        }

        features = await build_features(
            city_slug="Islamabad",
            raw_weather=sample_weather,
            rolling_buffer=None,
            climatology=None
        )

        print("\nFEATURE PIPELINE OUTPUT:\n")
        print(features)
        print("\nFUSION DICT:\n")
        print(features_to_fusion_dict(features))

    asyncio.run(_test())