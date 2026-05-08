"""PredictionEvent ORM model -- v2 prediction record with full traceability."""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, Float, JSON, String, func, Text,
)
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class PredictionEvent(Base):
    __tablename__ = "prediction_events"

    inference_id         = Column(String(36),  primary_key=True, default=_uuid)
    city_slug            = Column(String(64),  nullable=False, index=True)
    model_version        = Column(String(64),  nullable=False)
    calibration_version  = Column(String(64),  nullable=False)
    # FK refs stored as strings (no FK constraint -- avoids cross-schema issues)
    weather_api_snapshot_id = Column(String(36), nullable=True)
    feature_snapshot_id     = Column(String(36), nullable=True)

    # Branch outputs
    ae_percentile        = Column(Float, nullable=False)
    tcn_percentile       = Column(Float, nullable=False)
    ae_variance          = Column(Float)
    tcn_variance         = Column(Float)
    model_entropy        = Column(Float)       # H(p) -- Addition A
    dynamics_snapshot    = Column(JSON)        # rolling delta values at inference time

    # Fusion output
    p_event_raw          = Column(Float, nullable=False)   # uncalibrated
    p_event              = Column(Float, nullable=False, index=True)  # calibrated
    ci_lower             = Column(Float, nullable=False)
    ci_upper             = Column(Float, nullable=False)
    uncertainty          = Column(Float, nullable=False)

    # Risk classification
    risk_band            = Column(String(20), nullable=False, index=True)
    is_alert             = Column(Boolean,    nullable=False, index=True)
    alert_threshold      = Column(Float,      nullable=False)

    # Explainability
    shap_values          = Column(JSON)   # top-8 {feature: shap_value}

    # Metadata
    source               = Column(String(20), nullable=False)  # "city_model"|"heuristic"|"ood_guard"
    request_id           = Column(String(64))
    inferred_at          = Column(DateTime(timezone=True), nullable=False)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
