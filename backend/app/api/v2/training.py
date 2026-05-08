"""v2 Training management endpoints (Admin only)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.schemas.v2 import TrainingRequestV2, TrainingRunResponseV2

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/training", tags=["v2 Training"])


@router.post("/{city}", response_model=TrainingRunResponseV2)
async def trigger_city_training(
    city:  str,
    req:   TrainingRequestV2 = TrainingRequestV2(city="placeholder"),
    _admin=Depends(require_admin),
):
    """Trigger background training for a city (Admin only)."""
    from app.api.v2.cities import _run_training_background, trigger_training
    from fastapi import BackgroundTasks
    from app.services.city_model_service import _slug
    import uuid

    slug   = _slug(city)
    run_id = str(uuid.uuid4())
    req    = TrainingRequestV2(city=city, epochs=req.epochs, batch_size=req.batch_size,
                               use_tcn=req.use_tcn, force=req.force)

    import asyncio
    asyncio.create_task(_run_training_background(run_id=run_id, slug=slug, req=req))

    return TrainingRunResponseV2(
        id=run_id, city_slug=slug, status="queued", triggered_by="manual"
    )


@router.get("/{city}/status")
async def training_status(city: str, _admin=Depends(require_admin)):
    """Latest training run status for a city (Admin only)."""
    from app.services.city_model_service import _slug, city_model_service
    slug = _slug(city)
    metrics_path = __import__("pathlib").Path(
        f"backend/saved_models/city_models/{slug}/training_metrics.json"
    )
    if not metrics_path.exists():
        return {"city_slug": slug, "status": "never_trained"}
    import json
    return json.loads(metrics_path.read_text())


@router.get("/all-status")
async def all_training_status(_admin=Depends(require_admin)):
    """Training status for all cities (Admin only)."""
    from app.services.city_model_service import city_model_service
    return city_model_service.model_status()
