"""AnomalyRepository — canonical implementation (moved from database.py)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import AnomalyRecord


class AnomalyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        prediction_result: Dict[str, Any],
        weather_data: Dict[str, Any],
    ) -> AnomalyRecord:
        date_raw = prediction_result.get("date")
        try:
            parsed_date = (
                datetime.strptime(date_raw, "%Y-%m-%d")
                if isinstance(date_raw, str)
                else date_raw
            )
        except Exception:
            parsed_date = datetime.utcnow()

        cb = prediction_result.get("cloudburst_risk", {}) or {}

        record = AnomalyRecord(
            city        = prediction_result.get("city"),
            region      = weather_data.get("region"),
            date        = parsed_date,
            tmin        = weather_data.get("tmin"),
            tmax        = weather_data.get("tmax"),
            tavg        = weather_data.get("tavg"),
            prcp        = weather_data.get("prcp"),
            wspd        = weather_data.get("wspd"),
            humidity    = weather_data.get("humidity"),
            pressure    = weather_data.get("pressure"),
            dew_point   = weather_data.get("dew_point"),
            cloud_cover = weather_data.get("cloud_cover"),
            anomaly_score            = prediction_result.get("anomaly_score"),
            threshold                = prediction_result.get("threshold"),
            is_anomaly               = prediction_result.get("is_anomaly"),
            risk_level               = prediction_result.get("risk_level"),
            hri_score                = prediction_result.get("hri_score"),
            hri_label                = prediction_result.get("hri_label"),
            cloudburst_risk_score    = cb.get("risk_score"),
            cloudburst_risk_category = cb.get("risk_category"),
            is_cloudburst_likely     = cb.get("is_cloudburst_likely", False),
            remarks                  = prediction_result.get("remarks"),
            feature_contributions    = prediction_result.get("feature_contributions"),
            detailed_explanation     = prediction_result.get("detailed_explanation"),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, record_id: int) -> Optional[AnomalyRecord]:
        return self.db.query(AnomalyRecord).filter(AnomalyRecord.id == record_id).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        city: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        is_anomaly_only: bool = True,
    ) -> List[AnomalyRecord]:
        q = self.db.query(AnomalyRecord)
        if is_anomaly_only:
            q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
        if city:
            q = q.filter(AnomalyRecord.city == city)
        if risk_level:
            q = q.filter(AnomalyRecord.risk_level == risk_level)
        if start_date:
            q = q.filter(AnomalyRecord.date >= start_date)
        if end_date:
            q = q.filter(AnomalyRecord.date <= end_date)
        return q.order_by(AnomalyRecord.date.desc()).offset(skip).limit(limit).all()

    def list(
        self,
        skip: int = 0,
        limit: int = 100,
        is_anomaly_only: bool = False,
    ) -> List[AnomalyRecord]:
        """Alias used by analytics_aliases.py — returns all records by default."""
        return self.get_all(
            skip=skip,
            limit=limit,
            is_anomaly_only=is_anomaly_only,
        )

    def get_count(
        self,
        city: Optional[str] = None,
        risk_level: Optional[str] = None,
        is_anomaly_only: bool = True,
    ) -> int:
        q = self.db.query(AnomalyRecord)
        if is_anomaly_only:
            q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
        if city:
            q = q.filter(AnomalyRecord.city == city)
        if risk_level:
            q = q.filter(AnomalyRecord.risk_level == risk_level)
        return q.count()

    def get_statistics(self) -> Dict[str, Any]:
        total = self.db.query(func.count(AnomalyRecord.id)).scalar() or 0
        anomalies = (
            self.db.query(func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
            .scalar() or 0
        )
        by_city = dict(
            self.db.query(AnomalyRecord.city, func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
            .group_by(AnomalyRecord.city)
            .all()
        )
        by_risk = dict(
            self.db.query(AnomalyRecord.risk_level, func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
            .group_by(AnomalyRecord.risk_level)
            .all()
        )
        cloudburst = (
            self.db.query(func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_cloudburst_likely == True)  # noqa: E712
            .scalar() or 0
        )
        return {
            "total_records":    total,
            "total_anomalies":  anomalies,
            "anomaly_rate":     round(anomalies / total * 100, 2) if total else 0.0,
            "by_city":          by_city,
            "by_risk_level":    by_risk,
            "cloudburst_alerts": cloudburst,
        }
