"""
Prediction routes — DEPRECATED in v2.
These endpoints are tombstoned and redirect to /api/v2/cities/{city}/predict.

Client migration guide:
  POST /predict              → POST /api/v2/cities/{city}/predict
  POST /predict/batch        → POST /api/v2/cities/{city}/predict (per-item)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["Prediction (Deprecated)"])

_DEPRECATION_NOTE = (
    "This endpoint is deprecated. Use POST /api/v2/cities/{city}/predict instead. "
    "Sunset date: 2026-08-01."
)


@router.post("")
async def predict_anomaly(request: Request):
    """
    DEPRECATED — redirects to v2 city prediction endpoint.
    Include 'city' in the request body to get a proper redirect URL.
    """
    logger.warning("Deprecated /predict endpoint called from %s", request.client)
    try:
        body = await request.json()
        city = body.get("city", "islamabad")
    except Exception:
        city = "islamabad"

    redirect_url = f"/api/v2/cities/{city}/predict"
    return JSONResponse(
        status_code=308,
        content={
            "detail": _DEPRECATION_NOTE,
            "redirect_to": redirect_url,
        },
        headers={
            "Location":    redirect_url,
            "Deprecation": 'version="v1"; sunset="2026-08-01"',
        },
    )


@router.post("/batch")
async def predict_batch(request: Request):
    """DEPRECATED — use per-city predict endpoints."""
    logger.warning("Deprecated /predict/batch endpoint called from %s", request.client)
    return JSONResponse(
        status_code=308,
        content={
            "detail":      _DEPRECATION_NOTE,
            "redirect_to": "/api/v2/cities/{city}/predict",
        },
        headers={
            "Location":    "/api/v2/cities/islamabad/predict",
            "Deprecation": 'version="v1"; sunset="2026-08-01"',
        },
    )
