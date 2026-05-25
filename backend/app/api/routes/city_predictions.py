"""
HydroGuard-AI — City-Specific Prediction API
=============================================
All endpoints are read-accessible without auth; /train and /refresh require Admin.

The list of valid cities is **dynamic** — discovered from the dataset CSV and
the saved_models/city_models/ directory at startup. Adding a new city to the
dataset → POST /cities/refresh → it shows up immediately.

Endpoints
---------
GET  /cities                    — list every discovered city + model availability
GET  /cities/overview           — risk snapshot across all cities
POST /cities/refresh            — rescan CSV + disk for new cities (Admin)
GET  /cities/{city}/risk        — current risk assessment for one city
POST /cities/{city}/predict     — single prediction with provided weather data
GET  /cities/{city}/forecast    — 7-day outlook
GET  /cities/{city}/alerts      — recent alerts for one city
GET  /cities/{city}/status      — model status + metrics for one city
POST /cities/{city}/train       — trigger city-specific model training (Admin)
"""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.core.limiter import limiter

# Weather service import — optional; graceful fallback to climatology if unavailable
try:
    from app.services.weather_api import weather_service as _weather_service
    _HAS_WEATHER_SERVICE = True
except Exception:
    _weather_service = None
    _HAS_WEATHER_SERVICE = False
from app.services.city_model_service import (
    CITY_METADATA,
    DEFAULT_METADATA,
    city_model_service,
    _display_name,
    _meta_for,
    _slug,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cities", tags=["cities"])


# ──────────────────────────────────────────────────────────
#  Request / Response models
# ──────────────────────────────────────────────────────────

class WeatherInput(BaseModel):
    prcp:        Optional[float] = Field(None, description="Precipitation mm/h")
    humidity:    Optional[float] = Field(None, description="Relative humidity %")
    pressure:    Optional[float] = Field(None, description="Sea-level pressure hPa")
    tmax:        Optional[float] = Field(None, description="Max temperature °C")
    tmin:        Optional[float] = Field(None, description="Min temperature °C")
    tavg:        Optional[float] = Field(None, description="Avg temperature °C")
    cloud_cover: Optional[float] = Field(None, description="Cloud cover %")
    dew_point:   Optional[float] = Field(None, description="Dew point °C")
    wspd:        Optional[float] = Field(None, description="Wind speed km/h")
    date:        Optional[str]   = Field(None, description="ISO date string")


class CityTrainRequest(BaseModel):
    epochs:     int  = Field(150, ge=1, le=500)
    batch_size: int  = Field(64,  ge=8, le=512)
    use_tcn:    bool = True   # LSTM removed; TCN is the temporal branch


class PredictionResponse(BaseModel):
    city:          str
    city_slug:     str
    risk_level:    str
    anomaly_score: float
    confidence:    float
    is_anomaly:    bool
    ae_score:      float
    tcn_score:     float      # renamed from lstm_score (LSTM removed in v3.2)
    hri_score:     int
    source:        str
    timestamp:     str
    inputs:        Dict[str, Any]


# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

_UNKNOWN_CITY_CACHE: set = set()  # slugs confirmed not in registry; cleared on refresh


def _validate_city(city: str) -> str:
    """Resolve `city` to a valid slug or raise 404.

    The registry refresh (disk + CSV scan) only fires when the slug is not
    already in the registry AND has not already been checked since the last
    refresh — preventing unbounded disk I/O from unknown-city flood requests.
    """
    slug = _slug(city)
    if slug in city_model_service.list_slugs():
        return slug
    if slug in _UNKNOWN_CITY_CACHE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"City '{city}' not found. Use GET /cities to list valid cities. "
                f"If you've just added a new city to the dataset, call "
                f"POST /cities/refresh as an admin to rescan."
            ),
        )
    # First time seeing this slug — do one refresh to catch newly added cities
    city_model_service.refresh_registry()
    _UNKNOWN_CITY_CACHE.clear()  # registry changed; old negatives may be stale
    if slug in city_model_service.list_slugs():
        return slug
    _UNKNOWN_CITY_CACHE.add(slug)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"City '{city}' not found. Use GET /cities to list valid cities. "
            f"If you've just added a new city to the dataset, call "
            f"POST /cities/refresh as an admin to rescan."
        ),
    )


def _risk_to_scenario(risk_level: str) -> str:
    return {"Low": "safe", "Medium": "warn", "High": "crit"}.get(risk_level, "safe")


# Hand-curated climatology for known cities — used only when no live weather
# is available. ALL pressure values are sea-level (MSL) pressure in hPa.
# Training data uses MSL pressure (~1009 hPa mean). Surface pressure at high
# altitude (Gilgit 1500m ≈ 850 hPa, Quetta 1700m ≈ 830 hPa) must NOT be used.
_CLIMATOLOGY: Dict[str, Dict[str, float]] = {
    "islamabad":  dict(prcp=5,  humidity=60, pressure=1008, tmax=33, tmin=18, tavg=25, cloud_cover=40, dew_point=14, wspd=15),
    "rawalpindi": dict(prcp=5,  humidity=62, pressure=1007, tmax=34, tmin=19, tavg=26, cloud_cover=45, dew_point=15, wspd=14),
    "lahore":     dict(prcp=3,  humidity=55, pressure=1009, tmax=37, tmin=22, tavg=29, cloud_cover=30, dew_point=12, wspd=12),
    "karachi":    dict(prcp=2,  humidity=70, pressure=1011, tmax=34, tmin=26, tavg=30, cloud_cover=50, dew_point=22, wspd=18),
    "peshawar":   dict(prcp=6,  humidity=58, pressure=1008, tmax=35, tmin=20, tavg=27, cloud_cover=35, dew_point=13, wspd=16),
    # Quetta: training pressure mean=1012.6, wspd mean=13.4
    "quetta":     dict(prcp=4,  humidity=45, pressure=1013, tmax=28, tmin=10, tavg=19, cloud_cover=25, dew_point=8,  wspd=13),
    "faisalabad": dict(prcp=2,  humidity=52, pressure=1010, tmax=38, tmin=23, tavg=30, cloud_cover=28, dew_point=11, wspd=10),
    "multan":     dict(prcp=1,  humidity=48, pressure=1011, tmax=40, tmin=24, tavg=32, cloud_cover=20, dew_point=10, wspd=11),
    "hyderabad":  dict(prcp=2,  humidity=65, pressure=1012, tmax=36, tmin=25, tavg=30, cloud_cover=40, dew_point=20, wspd=15),
    # Gilgit: training pressure mean=1020.1 (higher than other cities), wspd mean=2.5 km/h (very low — mountain valley)
    "gilgit":     dict(prcp=8,  humidity=52, pressure=1020, tmax=22, tmin=8,  tavg=15, cloud_cover=55, dew_point=6,  wspd=3),
    "sialkot":    dict(prcp=4,  humidity=60, pressure=1009, tmax=35, tmin=20, tavg=27, cloud_cover=35, dew_point=14, wspd=12),
    "gujranwala": dict(prcp=3,  humidity=57, pressure=1009, tmax=36, tmin=21, tavg=28, cloud_cover=32, dew_point=13, wspd=11),
    "murree":     dict(prcp=12, humidity=72, pressure=1007, tmax=20, tmin=10, tavg=15, cloud_cover=65, dew_point=12, wspd=18),
    "skardu":     dict(prcp=6,  humidity=48, pressure=1008, tmax=18, tmin=4,  tavg=11, cloud_cover=40, dew_point=4,  wspd=20),
    "mirpur":     dict(prcp=7,  humidity=65, pressure=1007, tmax=30, tmin=18, tavg=24, cloud_cover=45, dew_point=16, wspd=14),
    "muzaffarabad":dict(prcp=10,humidity=68, pressure=1007, tmax=28, tmin=15, tavg=21, cloud_cover=55, dew_point=16, wspd=16),
}

_GENERIC_CLIMATOLOGY: Dict[str, float] = dict(
    prcp=4, humidity=58, pressure=1009, tmax=32, tmin=18,
    tavg=25, cloud_cover=40, dew_point=14, wspd=14,
)


def _default_weather(slug: str) -> Dict[str, float]:
    """Return climatological defaults for a city.
    For unknown cities, returns a generic mid-range default.
    """
    return _CLIMATOLOGY.get(slug, dict(_GENERIC_CLIMATOLOGY))


async def _get_weather(slug: str) -> Dict[str, float]:
    """
    Fetch live weather for *slug*, merging real values onto climatology defaults.
    Falls back to pure climatology if the weather service is unavailable or errors.
    All pressure values coming from the service are already MSL (pressure_msl).
    """
    defaults = _default_weather(slug)
    if not _HAS_WEATHER_SERVICE or _weather_service is None:
        return defaults
    try:
        live = await _weather_service.get_current(slug)
        if live and live.get("is_live"):
            # Merge: live values override defaults.
            # Keys intentionally NOT overridden:
            #   tmin/tmax/temp_range — current-hour APIs return tmin=tmax=current_temp
            #                          (daily range=0), wildly out-of-distribution for
            #                          daily training data.
            #   wspd               — instantaneous wind speed has huge variance vs the
            #                        daily-mean winds in the training CSV. Gilgit's
            #                        training wind std=0.5 km/h: even a 3 km/h gust
            #                        becomes a 6σ outlier after StandardScaler.
            _LIVE_KEYS = ("prcp", "humidity", "pressure", "cloud_cover", "dew_point")
            for k in _LIVE_KEYS:
                if k in live and live[k] is not None:
                    defaults[k] = float(live[k])
            # Update tavg from live temperature (sensible single-hour value)
            if "tavg" in live and live["tavg"] is not None:
                defaults["tavg"] = float(live["tavg"])
    except Exception as exc:
        logger.debug("Live weather fetch failed for %s (%s) — using climatology", slug, exc)
    return defaults


def _enrich_with_metadata(slug: str, base: Dict[str, Any]) -> Dict[str, Any]:
    meta = city_model_service.get_metadata(slug) or _meta_for(slug)
    base["province"] = meta.get("province", DEFAULT_METADATA["province"])
    base["lat"]      = meta.get("lat",      DEFAULT_METADATA["lat"])
    base["lon"]      = meta.get("lon",      DEFAULT_METADATA["lon"])
    return base


# ──────────────────────────────────────────────────────────
#  Routes
# ──────────────────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
async def list_cities():
    """List every discovered city. Includes both data-only and model-trained cities."""
    return city_model_service.list_cities()


@router.post("/refresh", response_model=Dict[str, Any])
async def refresh_registry(_admin=Depends(require_admin)):
    """Rescan dataset CSV + on-disk models for new cities (Admin)."""
    _UNKNOWN_CITY_CACHE.clear()
    registry = city_model_service.refresh_registry()
    status_info = city_model_service.model_status()
    return {
        "refreshed":    True,
        "total_cities": len(registry),
        **status_info,
    }


@router.get("/overview", response_model=Dict[str, Any])
async def cities_overview():
    """Risk snapshot across every discovered city using live weather where available."""
    import asyncio

    city_list = city_model_service.list_cities()

    # Fetch live weather for all cities concurrently
    weather_tasks = [_get_weather(c["slug"]) for c in city_list]
    all_features  = await asyncio.gather(*weather_tasks, return_exceptions=True)

    results: List[Dict[str, Any]] = []
    for city, features in zip(city_list, all_features):
        slug = city["slug"]
        if isinstance(features, Exception):
            features = _default_weather(slug)
        pred = city_model_service.predict(city=city["name"], features=features)
        results.append({
            "city":         city["name"],
            "city_slug":    slug,
            "province":     city["province"],
            "lat":          city["lat"],
            "lon":          city["lon"],
            "risk_level":   pred["risk_level"],
            "hri_score":    pred["hri_score"],
            "is_anomaly":   pred["is_anomaly"],
            "scenario":     _risk_to_scenario(pred["risk_level"]),
            "rainfall_mh":  features.get("prcp", 0),
            "has_model":    city["has_model"],
            "source":       pred.get("source", "—"),
        })
    return {
        "overview":     results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total":        len(results),
        "high_risk":    sum(1 for r in results if r["risk_level"] == "High"),
        "medium_risk":  sum(1 for r in results if r["risk_level"] == "Medium"),
        "low_risk":     sum(1 for r in results if r["risk_level"] == "Low"),
    }


@router.get("/{city}/risk", response_model=Dict[str, Any])
async def city_risk(city: str):
    """Current risk assessment for *city* — uses live weather when available,
    falls back to climatological defaults. Pressure is always MSL."""
    slug = _validate_city(city)
    features = await _get_weather(slug)
    pred = city_model_service.predict(city=_display_name(slug), features=features)
    pred["scenario"] = _risk_to_scenario(pred["risk_level"])
    pred["inputs"]   = {k: features.get(k) for k in ("prcp", "humidity", "pressure", "tmax", "tmin")}
    return _enrich_with_metadata(slug, pred)


@router.post("/{city}/predict", response_model=PredictionResponse)
@limiter.limit("30/minute")
async def city_predict(request: Request, city: str, body: WeatherInput):
    """Run city-specific hybrid model prediction with provided weather data."""
    slug = _validate_city(city)
    defaults = _default_weather(slug)
    features = {
        **defaults,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    }
    result = city_model_service.predict(city=_display_name(slug), features=features)

    # Record observation for drift monitoring (non-blocking)
    try:
        from app.ml.drift.monitor import get_drift_monitor
        dm = get_drift_monitor()
        if dm is not None:
            import asyncio
            asyncio.create_task(dm.record(slug, features))
    except Exception:
        pass

    return result


@router.get("/{city}/forecast", response_model=Dict[str, Any])
async def city_forecast(city: str, request: Request, response: Response):
    """7-day outlook for *city* (deterministic per-day seed for reproducibility).

    DEPRECATED — use GET /api/v2/cities/{city}/forecast for live WeatherAPI forecasts.
    Sunset: 2026-08-01.
    """
    slug = _validate_city(city)
    logger.warning(
        "Deprecated /cities/%s/forecast called from %s", slug, request.client
    )
    response.headers["Deprecation"] = 'version="v1"; sunset="2026-08-01"'
    response.headers["Link"] = (
        f'</api/v2/cities/{slug}/forecast>; rel="successor-version"'
    )

    base = _default_weather(slug)

    today    = datetime.now(timezone.utc).date()
    seed_str = f"{slug}-{today.isoformat()}"
    rng = random.Random(int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % 2**32)

    month       = today.month
    is_monsoon  = 6 <= month <= 9

    days: List[Dict[str, Any]] = []
    for offset in range(7):
        d = today + timedelta(days=offset)
        prcp_base = base["prcp"]
        if is_monsoon:
            prcp_base *= rng.uniform(0.5, 3.5)
        else:
            prcp_base *= rng.uniform(0.1, 1.8)

        features = {
            **base,
            "prcp":     round(max(prcp_base, 0), 1),
            "humidity": round(base["humidity"] + rng.uniform(-10, 10), 1),
            "pressure": round(base["pressure"] + rng.uniform(-8, 5), 1),
        }
        pred = city_model_service.predict(city=_display_name(slug), features=features)

        days.append({
            "date":        d.isoformat(),
            "day_name":    d.strftime("%A"),
            "prcp":        features["prcp"],
            "tmax":        base["tmax"],
            "tmin":        base["tmin"],
            "risk_level":  pred["risk_level"],
            "hri_score":   pred["hri_score"],
            "is_anomaly":  pred["is_anomaly"],
            "scenario":    _risk_to_scenario(pred["risk_level"]),
        })

    meta = city_model_service.get_metadata(slug) or _meta_for(slug)
    return {
        "city":         meta["name"],
        "province":     meta["province"],
        "forecast":     days,
        "today":        today.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source":       "synthetic",
        "deprecated":   True,
        "migrate_to":   f"/api/v2/cities/{slug}/forecast",
    }


@router.get("/{city}/alerts", response_model=Dict[str, Any])
async def city_alerts(city: str, n: int = 10):
    slug = _validate_city(city)
    alerts = city_model_service.get_recent_alerts(_display_name(slug), min(n, 20))
    return {
        "city":   _display_name(slug),
        "alerts": alerts,
        "count":  len(alerts),
    }


@router.get("/{city}/status", response_model=Dict[str, Any])
async def city_status(city: str):
    slug = _validate_city(city)
    meta = city_model_service.get_metadata(slug) or _meta_for(slug)
    has_model = meta.get("has_model", False)
    has_data  = meta.get("has_data",  False)

    info: Dict[str, Any] = {
        "city":      meta.get("name", _display_name(slug)),
        "city_slug": slug,
        "province":  meta.get("province"),
        "has_model": has_model,
        "has_data":  has_data,
        "source":    "city_model" if has_model else ("trainable" if has_data else "heuristic"),
    }
    if has_model:
        model = city_model_service.get_model(slug)
        if model:
            info.update({
                "input_dim":    model.input_dim,
                "ae_threshold": float(model.ae_threshold),
                "is_built":     model.is_built,
            })
    return info


@router.post("/{city}/train", response_model=Dict[str, Any])
async def city_train(
    city: str,
    body: CityTrainRequest,
    bg: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """Trigger training for one city's hybrid model (Admin only).
    Training runs asynchronously in the background.
    """
    # If the city is in the dataset but not yet in the registry, refresh first
    slug = _slug(city)
    if slug not in city_model_service.list_slugs():
        city_model_service.refresh_registry()
        if slug not in city_model_service.list_slugs():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"City '{city}' not present in the dataset. "
                        f"Add a row with city='{city}' to the master CSV first."),
            )

    meta = city_model_service.get_metadata(slug) or _meta_for(slug)
    if not meta.get("has_data"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"City '{city}' has no rows in the dataset. "
                    f"Cannot train without training data."),
        )

    def _run_training():
        try:
            from scripts.train_city import train_one_city
            train_one_city(
                slug      = slug,
                df_city   = None,   # train_one_city loads its own data
                models_dir= None,   # uses default models directory
                epochs    = body.epochs,
                batch_size= body.batch_size,
                use_tcn   = body.use_tcn,
            )
            logger.info("[%s] Background training completed", slug)
        except Exception as exc:
            logger.error("[%s] Background training failed: %s", slug, exc)

    bg.add_task(_run_training)
    return {
        "status":  "training_started",
        "city":    meta.get("name", _display_name(slug)),
        "config":  body.model_dump(),
        "message": f"Training for {meta.get('name', slug)} started in background.",
    }
