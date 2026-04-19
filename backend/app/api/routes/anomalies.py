"""Anomaly retrieval and statistics routes."""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import DATA_DIR
from app.db import AnomalyRepository, get_db
from app.schemas import (
    AnomalyListResponse,
    AnomalyRecordResponse,
    StatisticsResponse,
)
from app.services import anomaly_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


def _build_record_response(r) -> AnomalyRecordResponse:
    return AnomalyRecordResponse(
        id       = r.id,
        city     = r.city,
        region   = r.region,
        date     = r.date.isoformat() if r.date else "",
        weather_data = {
            "tmin": r.tmin, "tmax": r.tmax, "tavg": r.tavg,
            "prcp": r.prcp, "wspd": r.wspd, "humidity": r.humidity,
            "pressure": r.pressure, "dew_point": r.dew_point,
            "cloud_cover": r.cloud_cover,
        },
        anomaly_score         = r.anomaly_score,
        threshold             = r.threshold,
        is_anomaly            = r.is_anomaly,
        risk_level            = r.risk_level,
        hri_score             = getattr(r, "hri_score", None),
        hri_label             = getattr(r, "hri_label", None),
        cloudburst_risk       = {
            "score":     r.cloudburst_risk_score,
            "category":  r.cloudburst_risk_category,
            "is_likely": r.is_cloudburst_likely,
        },
        remarks               = r.remarks,
        feature_contributions = r.feature_contributions,
        created_at            = r.created_at.isoformat() if r.created_at else "",
    )


@router.get("", response_model=AnomalyListResponse)
async def get_anomalies(
    skip:           int           = Query(0, ge=0),
    limit:          int           = Query(50, ge=1, le=100),
    city:           Optional[str] = Query(None),
    risk_level:     Optional[str] = Query(None),
    start_date:     Optional[date] = Query(None),
    end_date:       Optional[date] = Query(None),
    anomalies_only: bool           = Query(True),
):
    try:
        with get_db() as db:
            repo    = AnomalyRepository(db)
            records = repo.get_all(
                skip            = skip,
                limit           = limit,
                city            = city,
                risk_level      = risk_level,
                start_date      = datetime.combine(start_date, datetime.min.time()) if start_date else None,
                end_date        = datetime.combine(end_date,   datetime.max.time()) if end_date   else None,
                is_anomaly_only = anomalies_only,
            )
            total = repo.get_count(city=city, risk_level=risk_level, is_anomaly_only=anomalies_only)

        return AnomalyListResponse(
            total     = total,
            page      = skip // limit + 1,
            page_size = limit,
            anomalies = [_build_record_response(r) for r in records],
        )
    except Exception as e:
        logger.error(f"Failed to retrieve anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=StatisticsResponse)
async def get_anomaly_statistics(
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
    city:       Optional[str]  = Query(None),
):
    if not anomaly_service.is_trained:
        raise HTTPException(status_code=400, detail="Model not trained.")

    data_files = list(DATA_DIR.glob("*.csv"))
    if not data_files:
        raise HTTPException(status_code=404, detail="No CSV found in data/ directory.")

    try:
        stats = anomaly_service.get_anomaly_statistics(
            data_path  = str(sorted(data_files)[0]),
            start_date = str(start_date) if start_date else None,
            end_date   = str(end_date)   if end_date   else None,
            city       = city,
        )
        return StatisticsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{anomaly_id}", response_model=AnomalyRecordResponse)
async def get_anomaly_by_id(anomaly_id: int):
    try:
        with get_db() as db:
            record = AnomalyRepository(db).get_by_id(anomaly_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found.")
        return _build_record_response(record)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
