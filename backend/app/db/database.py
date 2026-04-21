"""
HydroGuard-AI — Database Models & Repositories
================================================
SQLAlchemy ORM + repository pattern.

Key design decisions:
  - init_db() called explicitly from lifespan, NOT at import time.
  - SQLite connect_args ensures thread safety.
  - Repositories encapsulate all query logic; routers never touch the ORM directly.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, JSON, String, Text, create_engine, func,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine       = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


# ============================================================
#  ORM Models
# ============================================================

class AnomalyRecord(Base):
    """Persisted anomaly detection result."""

    __tablename__ = "anomaly_records"

    id     = Column(Integer, primary_key=True, index=True)
    city   = Column(String(100), index=True)
    region = Column(String(100), index=True)
    date   = Column(DateTime, index=True)

    tmin        = Column(Float, nullable=True)
    tmax        = Column(Float, nullable=True)
    tavg        = Column(Float, nullable=True)
    prcp        = Column(Float, nullable=True)
    wspd        = Column(Float, nullable=True)
    humidity    = Column(Float, nullable=True)
    pressure    = Column(Float, nullable=True)
    dew_point   = Column(Float, nullable=True)
    cloud_cover = Column(Float, nullable=True)

    anomaly_score = Column(Float, nullable=False)
    threshold     = Column(Float, nullable=False)
    is_anomaly    = Column(Boolean, nullable=False)
    risk_level    = Column(String(20), index=True)

    hri_score = Column(Integer, nullable=True)
    hri_label = Column(String(20), nullable=True)

    cloudburst_risk_score    = Column(Float, nullable=True)
    cloudburst_risk_category = Column(String(20), nullable=True)
    is_cloudburst_likely     = Column(Boolean, default=False)

    remarks               = Column(Text, nullable=True)
    feature_contributions = Column(JSON, nullable=True)
    detailed_explanation  = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":     self.id,
            "city":   self.city,
            "region": self.region,
            "date":   self.date.isoformat() if self.date else None,
            "weather_data": {
                "tmin": self.tmin, "tmax": self.tmax, "tavg": self.tavg,
                "prcp": self.prcp, "wspd": self.wspd, "humidity": self.humidity,
                "pressure": self.pressure, "dew_point": self.dew_point,
                "cloud_cover": self.cloud_cover,
            },
            "anomaly_score": self.anomaly_score,
            "threshold":     self.threshold,
            "is_anomaly":    self.is_anomaly,
            "risk_level":    self.risk_level,
            "hri_score":     self.hri_score,
            "hri_label":     self.hri_label,
            "cloudburst_risk": {
                "score":    self.cloudburst_risk_score,
                "category": self.cloudburst_risk_category,
                "is_likely": self.is_cloudburst_likely,
            },
            "remarks":               self.remarks,
            "feature_contributions": self.feature_contributions,
            "created_at":            self.created_at.isoformat() if self.created_at else None,
        }


class TrainingRecord(Base):
    """Training session audit log."""

    __tablename__ = "training_records"

    id = Column(Integer, primary_key=True, index=True)

    training_started          = Column(DateTime, nullable=False)
    training_completed        = Column(DateTime, nullable=True)
    training_duration_seconds = Column(Float, nullable=True)

    total_samples      = Column(Integer)
    train_samples      = Column(Integer)
    validation_samples = Column(Integer)
    num_cities         = Column(Integer)
    cities             = Column(JSON)
    date_range_start   = Column(DateTime)
    date_range_end     = Column(DateTime)

    final_loss          = Column(Float)
    final_val_loss      = Column(Float)
    epochs_trained      = Column(Integer)
    threshold           = Column(Float)

    lstm_enabled        = Column(Boolean, default=False)
    lstm_final_loss     = Column(Float, nullable=True)
    lstm_epochs_trained = Column(Integer, nullable=True)

    total_anomalies_detected = Column(Integer)
    anomaly_percentage       = Column(Float)

    status        = Column(String(50), default="completed")
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


# ============================================================
#  DB Helpers
# ============================================================

def init_db() -> None:
    """Create all tables. Call explicitly from lifespan — never at import time."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised.")


@contextmanager
def get_db():
    """Yield a scoped DB session, ensuring cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
#  Repositories
# ============================================================

# class AnomalyRepository:
#     def __init__(self, db: Session):
#         self.db = db

#     def create(
#         self,
#         prediction_result: Dict[str, Any],
#         weather_data: Dict[str, Any],
#     ) -> AnomalyRecord:
#         date_raw = prediction_result.get("date")
#         try:
#             parsed_date = (
#                 datetime.strptime(date_raw, "%Y-%m-%d")
#                 if isinstance(date_raw, str)
#                 else date_raw
#             )
#         except Exception:
#             parsed_date = datetime.utcnow()

#         cb = prediction_result.get("cloudburst_risk", {})

#         record = AnomalyRecord(
#             city        = prediction_result.get("city"),
#             region      = weather_data.get("region"),
#             date        = parsed_date,
#             tmin        = weather_data.get("tmin"),
#             tmax        = weather_data.get("tmax"),
#             tavg        = weather_data.get("tavg"),
#             prcp        = weather_data.get("prcp"),
#             wspd        = weather_data.get("wspd"),
#             humidity    = weather_data.get("humidity"),
#             pressure    = weather_data.get("pressure"),
#             dew_point   = weather_data.get("dew_point"),
#             cloud_cover = weather_data.get("cloud_cover"),
#             anomaly_score            = prediction_result.get("anomaly_score"),
#             threshold                = prediction_result.get("threshold"),
#             is_anomaly               = prediction_result.get("is_anomaly"),
#             risk_level               = prediction_result.get("risk_level"),
#             hri_score                = prediction_result.get("hri_score"),
#             hri_label                = prediction_result.get("hri_label"),
#             cloudburst_risk_score    = cb.get("risk_score"),
#             cloudburst_risk_category = cb.get("risk_category"),
#             is_cloudburst_likely     = cb.get("is_cloudburst_likely", False),
#             remarks                  = prediction_result.get("remarks"),
#             feature_contributions    = prediction_result.get("feature_contributions"),
#             detailed_explanation     = prediction_result.get("detailed_explanation"),
#         )
#         self.db.add(record)
#         self.db.commit()
#         self.db.refresh(record)
#         return record

#     def get_by_id(self, record_id: int) -> Optional[AnomalyRecord]:
#         return self.db.query(AnomalyRecord).filter(AnomalyRecord.id == record_id).first()

#     def get_all(
#         self,
#         skip: int = 0,
#         limit: int = 100,
#         city: Optional[str] = None,
#         risk_level: Optional[str] = None,
#         start_date: Optional[datetime] = None,
#         end_date:   Optional[datetime] = None,
#         is_anomaly_only: bool = True,
#     ) -> List[AnomalyRecord]:
#         q = self.db.query(AnomalyRecord)
#         if is_anomaly_only:
#             q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
#         if city:
#             q = q.filter(AnomalyRecord.city == city)
#         if risk_level:
#             q = q.filter(AnomalyRecord.risk_level == risk_level)
#         if start_date:
#             q = q.filter(AnomalyRecord.date >= start_date)
#         if end_date:
#             q = q.filter(AnomalyRecord.date <= end_date)
#         return q.order_by(AnomalyRecord.date.desc()).offset(skip).limit(limit).all()

#     def get_count(
#         self,
#         city: Optional[str] = None,
#         risk_level: Optional[str] = None,
#         is_anomaly_only: bool = True,
#     ) -> int:
#         q = self.db.query(AnomalyRecord)
#         if is_anomaly_only:
#             q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
#         if city:
#             q = q.filter(AnomalyRecord.city == city)
#         if risk_level:
#             q = q.filter(AnomalyRecord.risk_level == risk_level)
#         return q.count()

#     def get_statistics(self) -> Dict[str, Any]:
#         total     = self.db.query(func.count(AnomalyRecord.id)).scalar()
#         anomalies = self.db.query(func.count(AnomalyRecord.id)).filter(
#             AnomalyRecord.is_anomaly == True  # noqa: E712
#         ).scalar()
#         by_city = dict(
#             self.db.query(AnomalyRecord.city, func.count(AnomalyRecord.id))
#             .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
#             .group_by(AnomalyRecord.city).all()
#         )
#         by_risk = dict(
#             self.db.query(AnomalyRecord.risk_level, func.count(AnomalyRecord.id))
#             .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
#             .group_by(AnomalyRecord.risk_level).all()
#         )
#         cloudburst = self.db.query(func.count(AnomalyRecord.id)).filter(
#             AnomalyRecord.is_cloudburst_likely == True  # noqa: E712
#         ).scalar()

#         return {
#             "total_records":    total,
#             "total_anomalies":  anomalies,
#             "anomaly_rate":     round(anomalies / total * 100, 2) if total else 0.0,
#             "by_city":          by_city,
#             "by_risk_level":    by_risk,
#             "cloudburst_alerts": cloudburst,
#         }


class TrainingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, training_metadata: Dict[str, Any]) -> TrainingRecord:
        def _dt(s: str) -> datetime:
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return datetime.utcnow()

        ae   = training_metadata.get("autoencoder", {})
        lstm = training_metadata.get("lstm") or {}
        ast  = training_metadata.get("anomaly_stats", {})

        record = TrainingRecord(
            training_started          = datetime.utcnow(),
            training_completed        = datetime.utcnow(),
            training_duration_seconds = training_metadata.get("training_time_seconds"),
            total_samples             = training_metadata.get("total_samples"),
            train_samples             = training_metadata.get("train_samples"),
            validation_samples        = training_metadata.get("validation_samples"),
            num_cities                = training_metadata.get("num_cities"),
            cities                    = training_metadata.get("cities"),
            date_range_start          = _dt(training_metadata.get("date_range", {}).get("start", "2000-01-01")),
            date_range_end            = _dt(training_metadata.get("date_range", {}).get("end",   "2024-01-01")),
            final_loss                = ae.get("final_loss"),
            final_val_loss            = ae.get("final_val_loss"),
            epochs_trained            = ae.get("epochs_trained"),
            threshold                 = ae.get("threshold"),
            lstm_enabled              = bool(lstm),
            lstm_final_loss           = lstm.get("final_loss"),
            lstm_epochs_trained       = lstm.get("epochs_trained"),
            total_anomalies_detected  = ast.get("total_anomalies_detected"),
            anomaly_percentage        = ast.get("anomaly_percentage"),
            status                    = "completed",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_latest(self) -> Optional[TrainingRecord]:
        return (
            self.db.query(TrainingRecord)
            .order_by(TrainingRecord.created_at.desc())
            .first()
        )