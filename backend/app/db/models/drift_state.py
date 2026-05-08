"""DriftStateRecord ORM model -- persisted PSI drift check results."""
from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, func
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class DriftStateRecord(Base):
    __tablename__ = "drift_state"

    id             = Column(String(36), primary_key=True, default=_uuid)
    city_slug      = Column(String(64), nullable=False, index=True)
    checked_at     = Column(DateTime(timezone=True), nullable=False)
    window_size    = Column(Integer, nullable=False)
    reference_rows = Column(Integer, nullable=False)

    psi_scores         = Column(JSON,    nullable=False)  # {feature: psi_value}
    max_psi            = Column(Float,   nullable=False, index=True)
    drift_level        = Column(String(16), nullable=False)  # "ok"|"warn"|"critical"
    retrain_triggered  = Column(Boolean, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
