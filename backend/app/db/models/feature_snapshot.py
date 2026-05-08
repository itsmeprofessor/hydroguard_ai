"""Feature snapshot ORM model -- persists enriched feature vectors per prediction."""
from __future__ import annotations

import uuid
from sqlalchemy import Column, DateTime, Float, String, Text, func

from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id          = Column(String(36), primary_key=True, default=_uuid)
    city_slug   = Column(String(64), nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    data_source = Column(String(20), nullable=False)   # "weatherapi" | "user_submitted"

    # Raw inputs
    prcp        = Column(Float)
    humidity    = Column(Float)
    pressure    = Column(Float)
    cloud_cover = Column(Float)
    tmin        = Column(Float)
    tmax        = Column(Float)
    tavg        = Column(Float)
    temp_range  = Column(Float)
    dew_point   = Column(Float)
    wspd        = Column(Float)

    # Derived features
    pressure_delta_3h    = Column(Float)
    pressure_delta_6h    = Column(Float)
    humidity_delta_3h    = Column(Float)
    rain_rate_1h         = Column(Float)
    rain_accumulation_3h = Column(Float)
    rain_accumulation_6h = Column(Float)
    tdew_spread          = Column(Float)
    moisture_flux        = Column(Float)
    cloud_jump_3h        = Column(Float)

    # Climatological
    prcp_climo_pct     = Column(Float)
    pressure_climo_z   = Column(Float)
    humidity_climo_pct = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
