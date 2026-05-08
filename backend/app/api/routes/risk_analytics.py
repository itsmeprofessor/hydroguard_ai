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

PAKISTAN_CITIES = [
    {"name": "Islamabad",  "region": "Punjab",           "lat": 33.6844, "lon": 73.0479},
    {"name": "Rawalpindi", "region": "Punjab",           "lat": 33.5651, "lon": 73.0169},
    {"name": "Lahore",     "region": "Punjab",           "lat": 31.5204, "lon": 74.3587},
    {"name": "Karachi",    "region": "Sindh",            "lat": 24.8607, "lon": 67.0011},
    {"name": "Peshawar",   "region": "KPK",              "lat": 34.0151, "lon": 71.5249},
    {"name": "Quetta",     "region": "Balochistan",      "lat": 30.1798, "lon": 66.9750},
    {"name": "Gilgit",     "region": "Gilgit-Baltistan", "lat": 35.9208, "lon": 74.3144},
    {"name": "Faisalabad", "region": "Punjab",           "lat": 31.4504, "lon": 73.1350},
    {"name": "Multan",     "region": "Punjab",           "lat": 30.1575, "lon": 71.5249},
    {"name": "Hyderabad",  "region": "Sindh",            "lat": 25.3960, "lon": 68.3578},
]


@router.get("/risk-map", response_model=RiskMapResponse)
async def get_risk_map():
    """
    Return current HRI risk levels for all major Pakistan cities.
    Uses city_model_service (v2 inference path).
    """
    import asyncio
    entries: List[RiskMapEntry] = []
    now = datetime.now(timezone.utc)

    for city_info in PAKISTAN_CITIES:
        slug = _slug(city_info["name"])
        payload = {
            "city":     city_info["name"],
            "region":   city_info["region"],
            "date":     now.strftime("%Y-%m-%d"),
            "month":    now.month,
            "day":      now.day,
            "prcp":     0.0,
            "humidity": 60.0,
            "pressure": 1013.0,
        }
        try:
            result = city_model_service.predict(slug, payload)
            # Map v1-style risk_level to hri fields for backward compat
            risk = result.get("risk_level", "Low")
            hri  = result.get("hri_score", 0)
            entries.append(RiskMapEntry(
                city       = city_info["name"],
                region     = city_info["region"],
                latitude   = city_info["lat"],
                longitude  = city_info["lon"],
                hri_score  = hri,
                risk_level = risk,
                hri_label  = "Low" if hri < 25 else "Guarded" if hri < 50 else "Elevated" if hri < 75 else "Severe",
            ))
        except Exception as e:
            logger.warning("risk-map predict failed for %s: %s", city_info["name"], e)

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
