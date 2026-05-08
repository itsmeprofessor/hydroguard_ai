"""CalibrationStateRecord repository."""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.models.calibration_state import CalibrationStateRecord


class CalibrationRepo:
    def __init__(self, db: Session):
        self.db = db

    def create(self, record: CalibrationStateRecord) -> CalibrationStateRecord:
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_active(self, city_slug: str) -> Optional[CalibrationStateRecord]:
        return (
            self.db.query(CalibrationStateRecord)
            .filter(
                CalibrationStateRecord.city_slug == city_slug,
                CalibrationStateRecord.is_active == True,  # noqa: E712
            )
            .order_by(CalibrationStateRecord.calibrated_at.desc())
            .first()
        )

    def deactivate_all(self, city_slug: str) -> None:
        """Mark all existing calibrations for a city as inactive."""
        self.db.query(CalibrationStateRecord).filter(
            CalibrationStateRecord.city_slug == city_slug,
        ).update({"is_active": False})
        self.db.commit()

    def get_history(self, city_slug: str, limit: int = 10) -> List[CalibrationStateRecord]:
        return (
            self.db.query(CalibrationStateRecord)
            .filter(CalibrationStateRecord.city_slug == city_slug)
            .order_by(CalibrationStateRecord.calibrated_at.desc())
            .limit(limit)
            .all()
        )
