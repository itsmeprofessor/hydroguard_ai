"""Risk map and admin analytics routes."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from app.api.deps import require_admin
from app.db import AnomalyRecord, AnomalyRepository, get_db
from app.schemas import AnalyticsResponse, RiskMapEntry, RiskMapResponse
from app.services.city_model_service import city_model_service, _slug

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Risk & Analytics"])


@router.get("/risk-map", response_model=RiskMapResponse)
async def get_risk_map():
    """
    Return current HRI risk levels for all registered cities.
    City list is dynamic — derived from CITY_REGISTRY (CSV + saved models).
    """
    from app.api.routes.city_predictions import _default_weather
    entries: List[RiskMapEntry] = []
    now = datetime.now(timezone.utc)

    for meta in city_model_service.list_cities():
        slug   = meta["slug"]
        name   = meta["name"]
        region = meta.get("province", "")
        lat    = meta.get("lat", 0.0)
        lon    = meta.get("lon", 0.0)

        # Use climatological defaults rather than all-zeros
        weather_defaults = _default_weather(slug)
        payload = {
            "city":    name,
            "date":    now.strftime("%Y-%m-%d"),
            "month":   now.month,
            "day":     now.day,
            **weather_defaults,
        }
        try:
            result = city_model_service.predict(slug, payload)
            risk = result.get("risk_level", "Low")
            hri  = result.get("hri_score", 0)
            entries.append(RiskMapEntry(
                city       = name,
                region     = region,
                latitude   = lat,
                longitude  = lon,
                hri_score  = hri,
                risk_level = risk,
                hri_label  = "Low" if hri < 25 else "Guarded" if hri < 50 else "Elevated" if hri < 75 else "Severe",
            ))
        except Exception as e:
            logger.warning("risk-map predict failed for %s: %s", name, e)

    return RiskMapResponse(entries=entries, count=len(entries))


@router.get("/admin/analytics", response_model=AnalyticsResponse, tags=["Admin"])
async def get_admin_analytics(_admin=Depends(require_admin)):
    """Admin analytics — requires X-Admin-Token header."""
    try:
        with get_db() as db:
            repo   = AnomalyRepository(db)
            stats  = repo.get_statistics()
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            weekly = db.query(func.count(AnomalyRecord.id)).filter(
                AnomalyRecord.is_anomaly == True,  # noqa: E712
                AnomalyRecord.created_at >= cutoff,
            ).scalar()

        top_cities = [
            {"city": k, "count": v}
            for k, v in sorted(stats["by_city"].items(), key=lambda x: -x[1])[:5]
        ]

        return AnalyticsResponse(
            total_anomalies_this_week = weekly,
            alerts_by_risk_level      = stats["by_risk_level"],
            top_cities_by_frequency   = top_cities,
            total_cloudburst_alerts   = stats["cloudburst_alerts"],
            total_records_in_db       = stats["total_records"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: /database/statistics is served by analytics_aliases.router (registered
# after this router in main.py) with richer stats.  This duplicate is removed
# to prevent FastAPI registering the route twice and silently ignoring one.
# See app/api/routes/analytics_aliases.py for the authoritative implementation.
