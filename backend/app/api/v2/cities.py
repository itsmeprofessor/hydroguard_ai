"""v2 Cities endpoints."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.deps import require_admin
from app.schemas.v2 import (
    WeatherInputV2, CityPredictBody, PredictionResponseV2, CitiesListV2, CityStatusV2,
    TrainingRequestV2, TrainingRunResponseV2,
)
from app.services.city_model_service import city_model_service, _slug, _display_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cities", tags=["v2 Cities"])


@router.get("", response_model=CitiesListV2)
async def list_cities():
    """List all discovered cities with model availability."""
    cities_raw = city_model_service.list_cities()
    cities     = [
        CityStatusV2(
            slug       = c["slug"],
            name       = c["name"],
            province   = c.get("province", "--"),
            population = c.get("population", "--"),
            lat        = c.get("lat"),
            lon        = c.get("lon"),
            has_data   = c.get("has_data", False),
            has_model  = c.get("has_model", False),
        )
        for c in cities_raw
    ]
    trained = sum(1 for c in cities if c.has_model)
    return CitiesListV2(cities=cities, total=len(cities), trained=trained,
                        untrained=len(cities) - trained)


@router.get("/overview")
async def cities_overview():
    """Risk snapshot for all cities using heuristic or model."""
    results = []
    for c in city_model_service.list_cities():
        slug = c["slug"]
        try:
            result = city_model_service.predict(slug, {"prcp": 0.0, "humidity": 60.0,
                                                        "pressure": 1013.0})
            results.append({
                "slug":        slug,
                "name":        c["name"],
                "risk_band":   result.get("risk_level", "Low"),
                "hri_score":   result.get("hri_score", 0),
                "source":      result.get("source", "unknown"),
            })
        except Exception as exc:
            logger.debug("overview failed for %s: %s", slug, exc)
    return {"cities": results, "count": len(results)}


@router.get("/{city}/risk")
async def city_risk(city: str):
    """Live risk for one city -- fetches WeatherAPI and runs predict_v2."""
    slug = _slug(city)
    if not city_model_service.is_known_city(slug):
        raise HTTPException(404, f"City '{city}' not found.")

    # Try live weather first
    weather: Dict[str, Any] = {}
    try:
        from app.services.weather_api import weather_provider
        if weather_provider is not None:
            snap    = await weather_provider.get_current(city)
            weather = snap.to_feature_dict()
    except Exception as exc:
        logger.debug("WeatherAPI unavailable for %s: %s", slug, exc)
        weather = {"prcp": 0.0, "humidity": 60.0, "pressure": 1013.0}

    result = await city_model_service.predict_v2(slug, weather)
    return result


@router.post("/{city}/predict", response_model=PredictionResponseV2)
async def predict_city(
    city:    str,
    weather: CityPredictBody,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Submit weather data and get a v2 probabilistic prediction.
    City is taken from the URL path; all body fields are optional and
    fall back to climatological defaults when omitted.
    """
    slug = _slug(city)
    if not city_model_service.is_known_city(slug):
        raise HTTPException(404, f"City '{city}' not found.")

    raw = {k: v for k, v in weather.model_dump().items() if v is not None}
    result = await city_model_service.predict_v2(
        city_slug   = slug,
        raw_weather = raw,
        request_id  = request.headers.get("X-Request-ID"),
    )

    # Background: publish event
    background_tasks.add_task(_publish_event, result)

    return PredictionResponseV2(**result)


async def _publish_event(result: Dict[str, Any]) -> None:
    try:
        from app.services.event_bus import get_event_bus
        bus = get_event_bus()
        if bus:
            await bus.publish_prediction(result)
    except Exception as exc:
        logger.debug("Event publish failed: %s", exc)


@router.get("/{city}/forecast")
async def city_forecast(city: str, days: int = 7):
    """7-day outlook for a city."""
    slug = _slug(city)
    if not city_model_service.is_known_city(slug):
        raise HTTPException(404, f"City '{city}' not found.")

    try:
        from app.services.weather_api import weather_provider
        if weather_provider is None:
            raise RuntimeError("WeatherAPI not initialised")
        snaps = await weather_provider.get_forecast(city, days=min(days, 7))
        results = []
        for snap in snaps:
            weather = snap.to_feature_dict()
            pred    = await city_model_service.predict_v2(slug, weather)
            results.append({
                "date":             snap.forecast_date,
                "event_probability":pred.get("event_probability"),
                "risk_band":        pred.get("risk_band"),
                "daily_precip_mm":  snap.daily_precip_mm,
                "max_temp_c":       snap.max_temp_c,
                "min_temp_c":       snap.min_temp_c,
                "daily_chance_rain":snap.daily_chance_rain,
            })
        return {"city": _display_name(slug), "forecast": results}
    except Exception as exc:
        raise HTTPException(503, f"Forecast unavailable: {exc}")


@router.get("/{city}/alerts")
async def city_alerts(city: str, n: int = 10):
    """Recent alert events (is_alert=True) for a city."""
    slug    = _slug(city)
    alerts  = city_model_service.get_recent_alerts(slug, min(n, 20))
    return {"city": _display_name(slug), "alerts": alerts, "count": len(alerts)}


@router.get("/{city}/status")
async def city_status(city: str):
    """Model status and version info for a city."""
    slug = _slug(city)
    meta = city_model_service.get_metadata(slug)
    if meta is None:
        raise HTTPException(404, f"City '{city}' not found.")
    model = city_model_service._models.get(slug)
    return {
        "slug":       slug,
        "name":       _display_name(slug),
        "has_model":  meta.get("has_model", False),
        "has_data":   meta.get("has_data",  False),
        "input_dim":  model.input_dim if model else None,
        "ae_threshold": model.ae_threshold if model else None,
        "fusion_model_fitted": slug in city_model_service._fusion_models,
        "calibrator_fitted":   slug in city_model_service._calibrators,
    }


@router.post("/{city}/train", response_model=TrainingRunResponseV2)
async def trigger_training(
    city:             str,
    req:              TrainingRequestV2,
    background_tasks: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """Trigger city-specific training (Admin only). Runs in background."""
    slug = _slug(city)
    run_id = str(__import__("uuid").uuid4())

    background_tasks.add_task(
        _run_training_background,
        run_id=run_id, slug=slug, req=req,
    )

    return TrainingRunResponseV2(
        id           = run_id,
        city_slug    = slug,
        status       = "queued",
        triggered_by = "manual",
    )


async def _run_training_background(run_id: str, slug: str, req: TrainingRequestV2) -> None:
    """Background training task -- calls train_city script logic."""
    import asyncio
    logger.info("[%s] Background training started (run_id=%s)", slug, run_id)
    try:
        from scripts.train_city import train_one_city
        from app.core.config import DATA_DIR, MODELS_DIR
        import pandas as pd

        data_files = list(DATA_DIR.glob("*labeled*.csv")) or list(DATA_DIR.glob("*.csv"))
        if not data_files:
            logger.error("[%s] No data CSV found for training", slug)
            return

        df = pd.read_csv(data_files[0], low_memory=False)
        df_city = df[df["city"].str.lower().str.replace(" ","_") == slug].copy() \
                  if "city" in df.columns else df.copy()

        # Use the configured MODELS_DIR so the path is correct in both dev
        # (running from repo root) and Docker (WORKDIR=/app/backend).
        models_dir = MODELS_DIR / "city_models"
        await asyncio.to_thread(
            train_one_city,
            slug=slug, df_city=df_city, models_dir=models_dir,
            epochs=req.epochs, batch_size=req.batch_size,
            use_tcn=req.use_tcn, force=req.force,
        )
        # Hot-swap model in registry
        city_model_service.refresh_registry()
        logger.info("[%s] Training complete -- registry refreshed", slug)
    except Exception as exc:
        logger.error("[%s] Background training failed: %s", slug, exc, exc_info=True)


@router.post("/refresh", tags=["v2 Admin"])
async def refresh_registry(_admin=Depends(require_admin)):
    """Rescan CSV + disk for new cities/models (Admin only)."""
    reg = city_model_service.refresh_registry()
    return {"refreshed": True, "cities": len(reg)}
