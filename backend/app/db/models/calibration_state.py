"""CalibrationStateRecord ORM model -- calibration curve snapshot."""
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class CalibrationStateRecord(Base):
    __tablename__ = "calibration_state"

    id               = Column(String(36), primary_key=True, default=_uuid)
    city_slug        = Column(String(64), nullable=False, index=True)
    model_version    = Column(String(64), nullable=False)
    calibrated_at    = Column(DateTime(timezone=True), nullable=False)
    is_active        = Column(Boolean, nullable=False, server_default="0", index=True)

    n_calibration_samples = Column(Integer)
    brier_score_before    = Column(Float)
    brier_score_after     = Column(Float)
    ece_before            = Column(Float)
    ece_after             = Column(Float)

    artifact_path    = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
