"""Weather snapshot ORM model -- stores raw WeatherAPI responses per city per hour."""
from __future__ import annotations

import uuid
from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"

    id                = Column(String(36), primary_key=True, default=_uuid)
    city_slug         = Column(String(64), nullable=False, index=True)
    fetched_at        = Column(DateTime(timezone=True), nullable=False, index=True)
    provider          = Column(String(16), nullable=False, server_default="weatherapi")
    api_response_hash = Column(String(64))   # SHA-256 for dedup

    # WeatherAPI hourly fields
    temp_c         = Column(Float)
    feelslike_c    = Column(Float)
    humidity       = Column(Float)
    pressure_mb    = Column(Float)
    precip_mm      = Column(Float)
    cloud          = Column(Float)
    wind_kph       = Column(Float)
    dew_point_c    = Column(Float)
    vis_km         = Column(Float)
    uv_index       = Column(Float)
    condition_code = Column(Integer)

    # Derived at ingest time
    precip_mm_1h      = Column(Float)
    precip_mm_3h      = Column(Float)
    precip_mm_6h      = Column(Float)
    pressure_delta_3h = Column(Float)
    pressure_delta_6h = Column(Float)
    humidity_delta_3h = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
