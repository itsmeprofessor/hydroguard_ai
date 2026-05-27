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
    """Risk snapshot for all cities using live weather and calibrated predict_v2.

    All city weather fetches run in parallel (asyncio.gather). Falls back to
    zero-fill on any per-city weather failure — non-fatal, logged.
    """
    import asyncio
    from app.services.weather_api import weather_provider

    cities = city_model_service.list_cities()
    slugs  = [c["slug"] for c in cities]

    snaps = await asyncio.gather(
        *[_fetch_weather_safe(slug, weather_provider) for slug in slugs],
        return_exceptions=True,
    )

    results = []
    for c, snap in zip(cities, snaps):
        raw = snap if isinstance(snap, dict) else {}
        try:
            result = await city_model_service.predict_v2(c["slug"], raw)
            results.append({
                "slug":             c["slug"],
                "name":             c["name"],
                "risk_band":        result.get("risk_band", "Low"),
                "hri_score":        result.get("hri_score", 0),
                "event_probability":result.get("event_probability"),
                "alert_tier_label": result.get("alert_tier_label", "NORMAL"),
                "source":           result.get("source", "unknown"),
            })
        except Exception as exc:
            logger.debug("overview predict failed for %s: %s", c["slug"], exc)

    return {"cities": results, "count": len(results), "live_weather": True}


async def _fetch_weather_safe(slug: str, weather_provider) -> dict:
    """Fetch live weather for one city; returns empty dict on any failure."""
    try:
        if weather_provider is None:
            return {}
        snap = await weather_provider.get_current(slug)
        return snap.to_feature_dict()
    except Exception as exc:
        logger.warning("overview_weather_miss city=%s: %s", slug, exc)
        return {}


@router.get("/{city}/risk")
async def city_risk(city: str, background_tasks: BackgroundTasks):
    """Live risk for one city -- fetches real WeatherAPI data and runs predict_v2.

    Persists the result to anomaly_records so analytics charts reflect real
    observations. Only persists when live weather is successfully fetched
    (not fallback defaults) to avoid storing meaningless data.
    """
    slug = _slug(city)
    if not city_model_service.is_known_city(slug):
        raise HTTPException(404, f"City '{city}' not found.")

    # Try live weather first
    weather: Dict[str, Any] = {}
    is_live_weather = False
    try:
        from app.services.weather_api import weather_provider
        if weather_provider is not None:
            snap    = await weather_provider.get_current(city)
            weather = snap.to_feature_dict()
            is_live_weather = True
    except Exception as exc:
        logger.debug("WeatherAPI unavailable for %s: %s", slug, exc)
        weather = {"prcp": 0.0, "humidity": 60.0, "pressure": 1013.0}

    result = await city_model_service.predict_v2(slug, weather)

    # Persist to DB only when we have real live weather (not fallback defaults)
    if is_live_weather:
        background_tasks.add_task(_persist_prediction, result, weather)

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

    # Background: emit through control plane + persist to anomaly_records
    background_tasks.add_task(_emit_result_bg, result)
    background_tasks.add_task(_persist_prediction, result, raw)

    return PredictionResponseV2(**result)


async def _emit_result_bg(result: Dict[str, Any]) -> None:
    from app.runtime import system_runtime as runtime
    await runtime.emit_result(result)


async def _persist_prediction(result: Dict[str, Any], weather: Dict[str, Any]) -> None:
    """Save v2 prediction to anomaly_records table for analytics compatibility.

    Maps v2 field names → v1 AnomalyRepository.create() expectations.
    """
    try:
        from app.db import get_db, AnomalyRepository

        # Build v1-compatible prediction_result from v2 response
        risk_band = result.get("risk_band", "Low")
        v1_result = {
            "city":          result.get("city_slug") or result.get("city"),
            "date":          result.get("inferred_at"),
            "anomaly_score": result.get("event_probability", 0.0),
            "threshold":     0.5,
            "is_anomaly":    result.get("is_alert", False),
            "risk_level":    risk_band,
            "hri_score":     _band_to_hri(risk_band),
            "hri_label":     risk_band,
            "remarks":       f"v2 inference · source={result.get('source')}",
        }
        # Merge weather_inputs from result if weather dict is empty
        w = weather or result.get("weather_inputs") or {}

        with get_db() as db:
            repo = AnomalyRepository(db)
            repo.create(prediction_result=v1_result, weather_data=w)
    except Exception as exc:
        logger.debug("Persist prediction failed: %s", exc)


def _band_to_hri(band: str) -> int:
    return {"Low": 12, "Moderate": 40, "High": 68, "Severe": 88, "Evac": 95}.get(band, 12)


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
            risk_band = pred.get("risk_band", "Low")
            results.append({
                "date":             snap.forecast_date,
                "event_probability":pred.get("event_probability"),
                "risk_band":        risk_band,
                "hri_score":        pred.get("hri_score") or _band_to_hri(risk_band),
                "is_alert":         pred.get("is_alert", False),
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
    """Model status, version info, and persisted evaluation metrics for a city."""
    slug = _slug(city)
    meta = city_model_service.get_metadata(slug)
    if meta is None:
        raise HTTPException(404, f"City '{city}' not found.")
    model = city_model_service._models.get(slug)

    # Load persisted training_metrics.json if available
    from app.core.config import MODELS_DIR
    metrics_path = MODELS_DIR / "city_models" / slug / "training_metrics.json"
    training_metrics = None
    if metrics_path.exists():
        import json as _json
        try:
            training_metrics = _json.loads(metrics_path.read_text())
        except Exception:
            pass

    return {
        "slug":       slug,
        "name":       _display_name(slug),
        "has_model":  meta.get("has_model", False),
        "has_data":   meta.get("has_data",  False),
        "input_dim":  model.input_dim if model else None,
        "ae_threshold": model.ae_threshold if model else None,
        "fusion_model_fitted": slug in city_model_service._fusion_models,
        "calibrator_fitted":   slug in city_model_service._calibrators,
        "training_metrics":    training_metrics,
    }


@router.get("/metrics/summary")
async def all_cities_metrics():
    """Aggregated holdout evaluation metrics across all trained cities."""
    from app.core.config import MODELS_DIR
    import json as _json

    results = []
    models_dir = MODELS_DIR / "city_models"
    if not models_dir.exists():
        return {"cities": [], "summary": {}}

    for city_dir in sorted(models_dir.iterdir()):
        if not city_dir.is_dir() or city_dir.name.startswith(".") or city_dir.name.endswith(".bak"):
            continue
        slug = city_dir.name
        m_path = city_dir / "training_metrics.json"
        if not m_path.exists():
            results.append({"slug": slug, "has_metrics": False})
            continue
        try:
            m = _json.loads(m_path.read_text())
            results.append({
                "slug":               slug,
                "has_metrics":        True,
                "training_date":      m.get("training_date"),
                "holdout_auc":        m.get("holdout_auc"),
                "holdout_recall":     m.get("holdout_recall"),
                "holdout_precision":  m.get("holdout_precision"),
                "holdout_f1":         m.get("holdout_f1"),
                "calibration_error":  m.get("calibration_error"),
                "confusion_matrix":   m.get("confusion_matrix"),
                "threshold_used":     m.get("threshold_used"),
                "holdout_rows":       m.get("holdout_rows"),
                "holdout_strategy":   m.get("holdout_strategy"),
                "git_commit":         m.get("git_commit"),
                "dataset_hash":       m.get("dataset_hash"),
            })
        except Exception as exc:
            results.append({"slug": slug, "has_metrics": True, "error": str(exc)})

    aucs     = [r["holdout_auc"]    for r in results if isinstance(r.get("holdout_auc"), float)]
    recalls  = [r["holdout_recall"] for r in results if isinstance(r.get("holdout_recall"), float)]

    return {
        "cities": results,
        "summary": {
            "total_cities":       len(results),
            "cities_with_metrics": sum(1 for r in results if r.get("has_metrics")),
            "mean_holdout_auc":   round(sum(aucs)    / len(aucs),    4) if aucs    else None,
            "min_holdout_auc":    round(min(aucs),    4)                if aucs    else None,
            "mean_holdout_recall":round(sum(recalls) / len(recalls),  4) if recalls else None,
            "min_holdout_recall": round(min(recalls), 4)                if recalls else None,
        },
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
