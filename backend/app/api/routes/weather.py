"""
HydroGuard-AI — Live Weather API Routes
=========================================
Endpoints that proxy live weather data from Open-Meteo / OpenWeatherMap,
running city-specific predictions against the live observations.

GET /weather/{city}/current      — live weather + instant risk prediction
GET /weather/{city}/forecast     — 7-day forecast with per-day risk
GET /weather/overview            — all cities, live conditions + risk
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Path

from app.services.city_model_service import city_model_service, _slug
from app.services import weather_api

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/weather", tags=["Live Weather"])


# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

def _ensure_city(city: str) -> str:
    slug = _slug(city)
    if not city_model_service.is_known_city(slug):
        raise HTTPException(
            status_code=404,
            detail=f"City '{city}' not found. Available: {sorted(city_model_service.list_slugs())}",
        )
    return slug


def _merge_prediction(weather: Dict[str, Any], slug: str) -> Dict[str, Any]:
    """Run a city prediction against live weather data."""
    try:
        pred = city_model_service.predict(slug, weather)
        weather.update(pred)
    except Exception as exc:
        logger.warning("Prediction failed for %s: %s", slug, exc)
        weather["risk_level"]    = "Unknown"
        weather["anomaly_score"] = None
        weather["hri_score"]     = None
    return weather


# ──────────────────────────────────────────────────────────
#  Routes
# ──────────────────────────────────────────────────────────

@router.get("/{city}/current")
async def weather_current(city: str = Path(..., description="City name or slug")):
    """
    Live current weather observations for a city with instant risk prediction.

    Returns the current weather from Open-Meteo (or OpenWeatherMap if configured)
    merged with the city's ML risk assessment.
    """
    slug = _ensure_city(city)

    if weather_api.weather_service is None:
        raise HTTPException(status_code=503, detail="Weather provider not initialised")

    obs = await weather_api.weather_service.get_current(slug)
    if obs is None:
        raise HTTPException(
            status_code=503,
            detail=f"Weather data unavailable for '{city}'. "
                   "Check WEATHER_API_PROVIDER and network connectivity.",
        )

    obs_dict = obs.to_feature_dict() if hasattr(obs, "to_feature_dict") else dict(obs)
    return _merge_prediction(obs_dict, slug)


@router.get("/{city}/forecast")
async def weather_forecast(
    city: str = Path(..., description="City name or slug"),
    days: int = 7,
):
    """
    7-day weather forecast with per-day risk predictions.

    Each day includes weather variables + ML risk level from the city's model.
    """
    if days < 1 or days > 14:
        raise HTTPException(status_code=400, detail="days must be between 1 and 14")

    slug = _ensure_city(city)

    if weather_api.weather_service is None:
        raise HTTPException(status_code=503, detail="Weather provider not initialised")

    fc_days = await weather_api.weather_service.get_forecast(slug, days=days)

    if not fc_days:
        raise HTTPException(
            status_code=503,
            detail=f"Forecast unavailable for '{city}'.",
        )

    # Run prediction for each day. Each day is a WeatherSnapshot — convert to
    # a feature dict so the city model has the keys it expects.
    result: List[Dict[str, Any]] = []
    for day_data in fc_days:
        day_dict = day_data.to_feature_dict() if hasattr(day_data, "to_feature_dict") else dict(day_data)
        if hasattr(day_data, "forecast_date"):
            day_dict["date"] = day_data.forecast_date
        enriched = _merge_prediction(day_dict, slug)
        result.append(enriched)

    return {"city": slug, "days": len(result), "forecast": result}


@router.get("/overview")
async def weather_overview():
    """
    Live weather snapshot for all registered cities with risk predictions.
    Fetches all cities in parallel.
    """
    slugs = sorted(city_model_service.list_slugs())

    if weather_api.weather_service is None:
        raise HTTPException(status_code=503, detail="Weather provider not initialised")

    # Parallel fetch
    weather_map = await weather_api.weather_service.get_current_for_all_cities(slugs)

    result: List[Dict[str, Any]] = []
    for slug in slugs:
        obs = weather_map.get(slug)
        meta = city_model_service.get_metadata(slug) or {}
        if obs is None:
            result.append({
                "city_slug":  slug,
                "name":       meta.get("name", slug),
                "error":      "weather_unavailable",
                "risk_level": "Unknown",
            })
            continue
        obs_dict = obs.to_feature_dict() if hasattr(obs, "to_feature_dict") else dict(obs)
        enriched = _merge_prediction(obs_dict, slug)
        enriched["name"] = meta.get("name", slug)
        result.append(enriched)

    return {"cities": len(result), "data": result}
