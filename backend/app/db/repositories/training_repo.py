"""TrainingRepository — moved from database.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.database import TrainingRecord


class TrainingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, training_metadata: Dict[str, Any]) -> TrainingRecord:
        def _dt(s: str) -> datetime:
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return datetime.utcnow()

        ae  = training_metadata.get("autoencoder", {}) or {}
        ast = training_metadata.get("anomaly_stats", {}) or {}

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
