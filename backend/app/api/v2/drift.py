"""v2 Drift monitoring endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.db.database import get_db
from app.db.repositories.drift_repo import DriftRepo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/drift", tags=["v2 Drift"])


@router.get("")
async def all_drift_states():
    """Current drift state for all cities."""
    try:
        with get_db() as db:
            records = DriftRepo(db).get_all_latest()
        return {
            "cities": {
                r.city_slug: {
                    "drift_level":       r.drift_level,
                    "max_psi":           r.max_psi,
                    "retrain_triggered": r.retrain_triggered,
                    "checked_at":        r.checked_at.isoformat() if r.checked_at else None,
                }
                for r in records
            },
            "total":      len(records),
            "warn_count": sum(1 for r in records if r.drift_level == "warn"),
            "crit_count": sum(1 for r in records if r.drift_level == "critical"),
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/{city}")
async def city_drift(city: str):
    """Drift state and recent history for a city."""
    from app.services.city_model_service import _slug
    slug = _slug(city)
    try:
        with get_db() as db:
            repo    = DriftRepo(db)
            latest  = repo.get_latest(slug)
            history = repo.get_history(slug, limit=20)
        return {
            "city_slug": slug,
            "latest":    _record_to_dict(latest) if latest else None,
            "history":   [_record_to_dict(r) for r in history],
        }
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/{city}/psi-detail")
async def city_psi_detail(city: str):
    """Per-feature PSI breakdown for the latest drift check."""
    from app.services.city_model_service import _slug
    slug = _slug(city)
    with get_db() as db:
        latest = DriftRepo(db).get_latest(slug)
    if not latest:
        raise HTTPException(404, f"No drift data for '{city}'.")
    return {
        "city_slug":   slug,
        "checked_at":  latest.checked_at.isoformat() if latest.checked_at else None,
        "psi_scores":  latest.psi_scores,
        "drift_level": latest.drift_level,
        "max_psi":     latest.max_psi,
    }


def _record_to_dict(r) -> dict:
    return {
        "city_slug":         r.city_slug,
        "checked_at":        r.checked_at.isoformat() if r.checked_at else None,
        "drift_level":       r.drift_level,
        "max_psi":           r.max_psi,
        "psi_scores":        r.psi_scores,
        "retrain_triggered": r.retrain_triggered,
        "window_size":       r.window_size,
        "reference_rows":    r.reference_rows,
    }
