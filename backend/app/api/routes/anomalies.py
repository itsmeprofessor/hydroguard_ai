"""Anomaly retrieval and statistics routes."""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import DATA_DIR
from sqlalchemy import func
from app.db import AnomalyRepository,AnomalyRecord, get_db
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
    """DB-backed statistics. Falls back to CSV only if DB is empty."""
    try:
        with get_db() as db:
            repo = AnomalyRepository(db)
            stats = repo.get_statistics()

            # Optional: apply filters when provided
            q = db.query(func.count(AnomalyRecord.id)).filter(
                AnomalyRecord.is_anomaly == True  # noqa: E712
            )
            if city:
                q = q.filter(AnomalyRecord.city == city)
            if start_date:
                q = q.filter(AnomalyRecord.date >= start_date)
            if end_date:
                q = q.filter(AnomalyRecord.date <= end_date)
            filtered_count = q.scalar() or 0

            # by_month aggregate
            by_month_rows = (
                db.query(func.strftime("%m", AnomalyRecord.date),
                         func.count(AnomalyRecord.id))
                  .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
                  .group_by(func.strftime("%m", AnomalyRecord.date))
                  .all()
            )
            by_month = {m: c for m, c in by_month_rows if m}

            # date range in DB
            dmin = db.query(func.min(AnomalyRecord.date)).scalar()
            dmax = db.query(func.max(AnomalyRecord.date)).scalar()

        # DB-empty fallback: try CSV (only if model is trained)
        if stats["total_records"] == 0 and anomaly_service.is_trained:
            data_files = sorted(DATA_DIR.glob("*.csv"))
            if data_files:
                csv_stats = anomaly_service.get_anomaly_statistics(
                    data_path  = str(data_files[0]),
                    start_date = str(start_date) if start_date else None,
                    end_date   = str(end_date)   if end_date   else None,
                    city       = city,
                )
                return StatisticsResponse(
                    total_records    = csv_stats.get("total_records"),
                    anomaly_count    = csv_stats.get("total_anomalies"),
                    anomaly_rate     = csv_stats.get("anomaly_percentage"),
                    by_city          = csv_stats.get("anomalies_by_city"),
                    by_risk_level    = csv_stats.get("risk_distribution"),
                    by_month         = csv_stats.get("anomalies_by_month"),
                    cloudburst_count = 0,
                    date_range       = None,
                )

        return StatisticsResponse(
            total_records    = stats["total_records"],
            anomaly_count    = filtered_count if (city or start_date or end_date) else stats["total_anomalies"],
            anomaly_rate     = stats["anomaly_rate"],
            by_city          = stats["by_city"],
            by_risk_level    = stats["by_risk_level"],
            by_month         = by_month,
            cloudburst_count = stats["cloudburst_alerts"],
            date_range       = {
                "start": dmin.isoformat() if dmin else None,
                "end":   dmax.isoformat() if dmax else None,
            },
        )
    except Exception as e:
        logger.error(f"statistics failed: {e}", exc_info=True)
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
