"""
HydroGuard-AI — Database Engine, ORM Models & Session Utilities
===============================================================
Key design decisions:
  - init_db() called explicitly from lifespan, NOT at import time.
  - SQLite connect_args guard is only applied when the driver is SQLite.
  - Repositories live in app/db/repositories/ — not here.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, JSON, String, Text,
    create_engine, func,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine        = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)
SessionLocal  = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base          = declarative_base()


# ============================================================
#  ORM Models
# ============================================================

class AnomalyRecord(Base):
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

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # v2 traceability fields — added in migration 001; nullable for legacy rows
    inference_id  = Column(String(36), nullable=True)
    model_version = Column(String(64), nullable=True)

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
                "score":     self.cloudburst_risk_score,
                "category":  self.cloudburst_risk_category,
                "is_likely": self.is_cloudburst_likely,
            },
            "remarks":               self.remarks,
            "feature_contributions": self.feature_contributions,
            "created_at":            self.created_at.isoformat() if self.created_at else None,
        }


class TrainingRecord(Base):
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

    total_anomalies_detected = Column(Integer)
    anomaly_percentage       = Column(Float)

    status        = Column(String(50), default="completed")
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ============================================================
#  DB Helpers
# ============================================================

def init_db() -> None:
    """Create all tables. Called from lifespan — never at import time."""
    # Import from canonical location so users table is registered on Base.metadata
    from app.db.models.user import User  # noqa: F401 — ensures users table registered
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised.")


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
