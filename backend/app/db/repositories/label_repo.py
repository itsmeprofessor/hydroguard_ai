"""LabelEvent repository."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.label_event import LabelEvent


class LabelRepo:
    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, labels: List[LabelEvent]) -> int:
        """Insert many label events. Returns count inserted."""
        for lbl in labels:
            self.db.add(lbl)
        self.db.commit()
        return len(labels)

    def get_by_city(
        self,
        city_slug: str,
        limit:     int = 100,
        offset:    int = 0,
    ) -> List[LabelEvent]:
        return (
            self.db.query(LabelEvent)
            .filter(LabelEvent.city_slug == city_slug)
            .order_by(LabelEvent.observed_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_positive_rate(self, city_slug: str) -> float:
        total = self.db.query(func.count(LabelEvent.id)).filter(
            LabelEvent.city_slug == city_slug,
            LabelEvent.weak_label != -1,
        ).scalar() or 0
        if total == 0:
            return 0.0
        pos = self.db.query(func.count(LabelEvent.id)).filter(
            LabelEvent.city_slug == city_slug,
            LabelEvent.weak_label == 1,
        ).scalar() or 0
        return round(pos / total, 4)

    def override(
        self,
        label_id:    str,
        verified_by: str,
        new_label:   int,
        notes:       str = "",
    ) -> Optional[LabelEvent]:
        lbl = self.db.query(LabelEvent).filter(LabelEvent.id == label_id).first()
        if not lbl:
            return None
        lbl.weak_label   = new_label
        lbl.is_verified  = True
        lbl.verified_by  = verified_by
        lbl.verified_at  = datetime.now(__import__("datetime").timezone.utc)
        lbl.notes        = notes
        self.db.commit()
        self.db.refresh(lbl)
        return lbl

    def statistics(self, city_slug: str) -> Dict:
        rows = self.db.query(
            LabelEvent.weak_label, func.count(LabelEvent.id)
        ).filter(LabelEvent.city_slug == city_slug).group_by(LabelEvent.weak_label).all()
        counts = {label: cnt for label, cnt in rows}
        total  = sum(counts.values())
        return {
            "city_slug":      city_slug,
            "total":          total,
            "positive":       counts.get(1,  0),
            "negative":       counts.get(0,  0),
            "abstain":        counts.get(-1, 0),
            "positive_rate":  round(counts.get(1, 0) / max(total, 1), 4),
        }
