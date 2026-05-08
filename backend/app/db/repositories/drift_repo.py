"""DriftStateRecord repository."""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.models.drift_state import DriftStateRecord


class DriftRepo:
    def __init__(self, db: Session):
        self.db = db

    def create(self, record: DriftStateRecord) -> DriftStateRecord:
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_latest(self, city_slug: str) -> Optional[DriftStateRecord]:
        return (
            self.db.query(DriftStateRecord)
            .filter(DriftStateRecord.city_slug == city_slug)
            .order_by(DriftStateRecord.checked_at.desc())
            .first()
        )

    def get_history(self, city_slug: str, limit: int = 50) -> List[DriftStateRecord]:
        return (
            self.db.query(DriftStateRecord)
            .filter(DriftStateRecord.city_slug == city_slug)
            .order_by(DriftStateRecord.checked_at.desc())
            .limit(limit)
            .all()
        )

    def get_all_latest(self) -> List[DriftStateRecord]:
        """Latest drift record for every city."""
        from sqlalchemy import func
        subq = (
            self.db.query(
                DriftStateRecord.city_slug,
                func.max(DriftStateRecord.checked_at).label("max_checked"),
            )
            .group_by(DriftStateRecord.city_slug)
            .subquery()
        )
        return (
            self.db.query(DriftStateRecord)
            .join(subq, (DriftStateRecord.city_slug == subq.c.city_slug) &
                        (DriftStateRecord.checked_at == subq.c.max_checked))
            .all()
        )
