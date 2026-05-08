"""v2 Label management endpoints (Admin only)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.db.database import get_db
from app.db.repositories.label_repo import LabelRepo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/labels", tags=["v2 Labels"])


@router.get("/{city}")
async def get_city_labels(
    city:   str,
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0,   ge=0),
    _admin=Depends(require_admin),
):
    """List label events for a city (Admin only)."""
    from app.services.city_model_service import _slug
    slug = _slug(city)
    with get_db() as db:
        labels = LabelRepo(db).get_by_city(slug, limit=limit, offset=offset)
    return {
        "city_slug": slug,
        "labels": [
            {
                "id":              l.id,
                "observed_at":     l.observed_at.isoformat() if l.observed_at else None,
                "weak_label":      l.weak_label,
                "weak_label_conf": l.weak_label_conf,
                "event_type":      l.event_type,
                "rule_votes":      l.rule_votes,
                "is_verified":     l.is_verified,
            }
            for l in labels
        ],
        "count": len(labels),
    }


@router.get("/{city}/statistics")
async def city_label_statistics(city: str, _admin=Depends(require_admin)):
    """Positive rate and rule fire statistics for a city (Admin only)."""
    from app.services.city_model_service import _slug
    with get_db() as db:
        stats = LabelRepo(db).statistics(_slug(city))
    return stats


@router.put("/{label_id}")
async def override_label(
    label_id:  str,
    new_label: int,
    notes:     str = "",
    _admin=Depends(require_admin),
):
    """Override a weak label with a verified label (NDMA/PMD verification) (Admin only)."""
    from app.api.deps import get_current_user
    if new_label not in (-1, 0, 1):
        raise HTTPException(400, "new_label must be -1, 0, or 1")
    with get_db() as db:
        updated = LabelRepo(db).override(label_id, "admin", new_label, notes)
    if not updated:
        raise HTTPException(404, f"Label '{label_id}' not found.")
    return {"id": label_id, "new_label": new_label, "is_verified": True}
