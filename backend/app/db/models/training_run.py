"""TrainingRun ORM model -- richer replacement for TrainingRecord."""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, JSON,
    String, Text, func,
)
from app.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id                = Column(String(36), primary_key=True, default=_uuid)
    city_slug         = Column(String(64), nullable=False, index=True)
    triggered_by      = Column(String(32), nullable=False)   # "manual"|"drift"|"schedule"
    triggered_by_user = Column(String(64))

    status            = Column(String(16), nullable=False, server_default="queued")
    error_message     = Column(Text)

    # Data provenance
    dataset_hash      = Column(String(64))
    data_rows         = Column(Integer)
    data_date_start   = Column(Date)
    data_date_end     = Column(Date)
    label_rows_used   = Column(Integer)
    positive_label_rate = Column(Float)

    # Architecture snapshot
    architecture      = Column(JSON)
    hyperparameters   = Column(JSON)
    git_commit        = Column(String(40))
    model_version     = Column(String(64))

    # Metrics
    ae_train_loss     = Column(Float)
    ae_val_loss       = Column(Float)
    tcn_train_loss    = Column(Float)
    tcn_val_loss      = Column(Float)
    lgbm_val_auc      = Column(Float)
    lgbm_val_brier    = Column(Float)
    calibration_ece   = Column(Float)
    calibration_brier = Column(Float)

    # Timing
    started_at        = Column(DateTime(timezone=True))
    finished_at       = Column(DateTime(timezone=True))
    duration_seconds  = Column(Float)

    created_at        = Column(DateTime(timezone=True), server_default=func.now())
