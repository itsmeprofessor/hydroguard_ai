"""LabelEvent ORM model -- weak supervision label record."""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, Float, JSON, SmallInteger,
    String, Text, func,
)
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class LabelEvent(Base):
    __tablename__ = "label_events"

    id                   = Column(String(36),  primary_key=True, default=_uuid)
    city_slug            = Column(String(64),  nullable=False, index=True)
    observed_at          = Column(DateTime(timezone=True), nullable=False, index=True)
    feature_snapshot_id  = Column(String(36),  nullable=True)

    # Weak label outcome
    weak_label           = Column(SmallInteger, nullable=False)  # -1 | 0 | 1
    weak_label_conf      = Column(Float,        nullable=False)
    event_type           = Column(String(32))   # "cloudburst"|"flash_flood"|"heavy_rain"|null

    # Rule breakdown
    source               = Column(String(32), nullable=False)   # labeling function name or "engine"
    source_weight        = Column(Float,      nullable=False)
    raw_score            = Column(Float)
    rule_votes           = Column(JSON)   # {"L1":1,"L2":-1,...} -- Addition B

    # Override (future NDMA integration)
    is_verified          = Column(Boolean, server_default="0")
    verified_by          = Column(String(64))
    verified_at          = Column(DateTime(timezone=True))
    notes                = Column(Text)

    created_at           = Column(DateTime(timezone=True), server_default=func.now())
