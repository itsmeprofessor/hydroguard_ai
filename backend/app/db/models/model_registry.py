"""ModelRegistryEntry ORM model -- per-city model lineage tracking."""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, String, Text, func,
)
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class ModelRegistryEntry(Base):
    __tablename__ = "model_registry"

    id               = Column(String(36), primary_key=True, default=_uuid)
    city_slug        = Column(String(64), nullable=False, index=True)
    model_version    = Column(String(64), nullable=False, unique=True)
    is_active        = Column(Boolean,    nullable=False, server_default="0", index=True)

    artifact_path    = Column(Text,       nullable=False)
    ae_path          = Column(Text)
    tcn_path         = Column(Text)
    lgbm_path        = Column(Text)
    calibrator_path  = Column(Text)
    preprocessor_path = Column(Text)

    training_run_id  = Column(String(36))   # FK to training_runs.id (soft ref)
    deployed_at      = Column(DateTime(timezone=True))
    retired_at       = Column(DateTime(timezone=True))

    created_at       = Column(DateTime(timezone=True), server_default=func.now())
