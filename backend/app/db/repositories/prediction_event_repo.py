"""PredictionEvent repository."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.prediction_event import PredictionEvent


class PredictionEventRepo:
    def __init__(self, db: Session):
        self.db = db

    def create(self, event: PredictionEvent) -> PredictionEvent:
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def add(self, event: PredictionEvent) -> PredictionEvent:
        """Stage without commit (for batch use)."""
        self.db.add(event)
        return event

    def get_by_id(self, inference_id: str) -> Optional[PredictionEvent]:
        return self.db.query(PredictionEvent).filter(
            PredictionEvent.inference_id == inference_id
        ).first()

    def list_by_city(
        self,
        city_slug:        str,
        limit:            int            = 100,
        offset:           int            = 0,
        is_alert_only:    bool           = False,
        start_date:       Optional[datetime] = None,
        end_date:         Optional[datetime] = None,
        min_probability:  Optional[float] = None,
    ) -> List[PredictionEvent]:
        q = self.db.query(PredictionEvent).filter(
            PredictionEvent.city_slug == city_slug
        )
        if is_alert_only:
            q = q.filter(PredictionEvent.is_alert == True)  # noqa: E712
        if start_date:
            q = q.filter(PredictionEvent.inferred_at >= start_date)
        if end_date:
            q = q.filter(PredictionEvent.inferred_at <= end_date)
        if min_probability is not None:
            q = q.filter(PredictionEvent.p_event >= min_probability)
        return q.order_by(PredictionEvent.inferred_at.desc()).offset(offset).limit(limit).all()

    def recent_for_drift(self, city_slug: str, limit: int = 500) -> List[PredictionEvent]:
        return (
            self.db.query(PredictionEvent)
            .filter(PredictionEvent.city_slug == city_slug)
            .order_by(PredictionEvent.inferred_at.desc())
            .limit(limit)
            .all()
        )

    def count(self, city_slug: Optional[str] = None) -> int:
        q = self.db.query(func.count(PredictionEvent.inference_id))
        if city_slug:
            q = q.filter(PredictionEvent.city_slug == city_slug)
        return q.scalar() or 0

    def statistics(self) -> Dict[str, Any]:
        total   = self.count()
        alerts  = self.db.query(func.count(PredictionEvent.inference_id)).filter(
            PredictionEvent.is_alert == True  # noqa: E712
        ).scalar() or 0
        by_band = dict(
            self.db.query(PredictionEvent.risk_band, func.count(PredictionEvent.inference_id))
            .group_by(PredictionEvent.risk_band)
            .all()
        )
        by_city = dict(
            self.db.query(PredictionEvent.city_slug, func.count(PredictionEvent.inference_id))
            .group_by(PredictionEvent.city_slug)
            .all()
        )
        return {
            "total_predictions": total,
            "total_alerts":      alerts,
            "alert_rate":        round(alerts / total, 4) if total else 0.0,
            "by_risk_band":      by_band,
            "by_city":           by_city,
        }
