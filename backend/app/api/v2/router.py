"""v2 API router -- mounts all sub-routers under /api/v2."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v2.cities   import router as cities_router
from app.api.v2.events   import router as events_router
from app.api.v2.labels   import router as labels_router
from app.api.v2.training import router as training_router
from app.api.v2.drift    import router as drift_router

v2_router = APIRouter(prefix="/api/v2", tags=["v2"])

v2_router.include_router(cities_router)
v2_router.include_router(events_router)
v2_router.include_router(labels_router)
v2_router.include_router(training_router)
v2_router.include_router(drift_router)
