"""Risk map and admin analytics routes."""

import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from app.api.deps import require_admin
from app.db import AnomalyRecord, AnomalyRepository, get_db
from app.schemas import AnalyticsResponse, RiskMapEntry, RiskMapResponse
from app.services import anomaly_service

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
    Flutter app uses this to colour map markers.
    """
    if not anomaly_service.is_trained:
        raise HTTPException(status_code=400, detail="Model not trained.")

    entries: List[RiskMapEntry] = []
    now = datetime.now()

    for city_info in PAKISTAN_CITIES:
        payload = {
            "city":   city_info["name"],
            "region": city_info["region"],
            "date":   now.strftime("%Y-%m-%d"),
            "month":  now.month,
            "day":    now.day,
        }
        try:
            result = anomaly_service.predict(payload)
            entries.append(RiskMapEntry(
                city       = city_info["name"],
                region     = city_info["region"],
                latitude   = city_info["lat"],
                longitude  = city_info["lon"],
                hri_score  = result["hri_score"],
                risk_level = result["risk_level"],
                hri_label  = result["hri_label"],
            ))
        except Exception as e:
            logger.warning(f"risk-map predict failed for {city_info['name']}: {e}")

    return RiskMapResponse(entries=entries, count=len(entries))


@router.get("/admin/analytics", response_model=AnalyticsResponse, tags=["Admin"])
async def get_admin_analytics(_admin=Depends(require_admin)):
    """Admin analytics — requires X-Admin-Token header."""
    try:
        with get_db() as db:
            repo  = AnomalyRepository(db)
            stats = repo.get_statistics()

        with get_db() as db2:
            cutoff = datetime.utcnow() - timedelta(days=7)
            weekly = db2.query(func.count(AnomalyRecord.id)).filter(
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


@router.get("/database/statistics", tags=["System"])
async def get_database_statistics():
    try:
        with get_db() as db:
            return AnomalyRepository(db).get_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
