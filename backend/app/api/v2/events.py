"""v2 Prediction Events endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.repositories.prediction_event_repo import PredictionEventRepo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["v2 Events"])


@router.get("")
async def list_events(
    city_slug:       Optional[str]   = Query(None),
    risk_band:       Optional[str]   = Query(None),
    is_alert:        Optional[bool]  = Query(None),
    min_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
    start_date:      Optional[datetime] = Query(None),
    end_date:        Optional[datetime] = Query(None),
    limit:           int             = Query(50, ge=1, le=100),
    offset:          int             = Query(0, ge=0),
):
    """Paginated list of prediction events with filters."""
    try:
        with get_db() as db:
            repo   = PredictionEventRepo(db)
            events = repo.list_by_city(
                city_slug       = city_slug or "",
                limit           = limit,
                offset          = offset,
                is_alert_only   = bool(is_alert),
                start_date      = start_date,
                end_date        = end_date,
                min_probability = min_probability,
            ) if city_slug else []

            # If no city filter, use a generic query
            if not city_slug:
                from sqlalchemy import and_
                q = db.query(__import__("app.db.models.prediction_event",
                             fromlist=["PredictionEvent"]).PredictionEvent)
                if is_alert:
                    q = q.filter_by(is_alert=True)
                if risk_band:
                    q = q.filter_by(risk_band=risk_band)
                events = q.order_by(
                    __import__("app.db.models.prediction_event",
                    fromlist=["PredictionEvent"]).PredictionEvent.inferred_at.desc()
                ).offset(offset).limit(limit).all()

            total = repo.count(city_slug)
        return {
            "events": [_event_to_dict(e) for e in events],
            "total":  total,
            "limit":  limit,
            "offset": offset,
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/statistics")
async def event_statistics():
    """Aggregate prediction event statistics."""
    try:
        with get_db() as db:
            return PredictionEventRepo(db).statistics()
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/{inference_id}")
async def get_event(inference_id: str):
    """Fetch a single prediction event by inference ID."""
    with get_db() as db:
        event = PredictionEventRepo(db).get_by_id(inference_id)
    if not event:
        raise HTTPException(404, f"Event '{inference_id}' not found.")
    return _event_to_dict(event)


def _event_to_dict(e) -> dict:
    return {
        "inference_id":      e.inference_id,
        "city_slug":         e.city_slug,
        "model_version":     e.model_version,
        "event_probability": e.p_event,
        "risk_band":         e.risk_band,
        "is_alert":          e.is_alert,
        "model_entropy":     e.model_entropy,
        "uncertainty":       e.uncertainty,
        "source":            e.source,
        "inferred_at":       e.inferred_at.isoformat() if e.inferred_at else None,
        "shap_values":       e.shap_values,
    }
