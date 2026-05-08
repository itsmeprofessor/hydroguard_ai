"""
Training routes — DEPRECATED in v2.
Redirects to /api/v2/training/{city}.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/train", tags=["Training (Deprecated)"])

_DEPRECATION_NOTE = (
    "This endpoint is deprecated. Use POST /api/v2/training/{city} instead. "
    "Sunset date: 2026-08-01."
)


@router.post("")
async def train_model(request: Request):
    """DEPRECATED — redirects to v2 training endpoint."""
    logger.warning("Deprecated /train endpoint called from %s", request.client)
    return JSONResponse(
        status_code=308,
        content={
            "detail":      _DEPRECATION_NOTE,
            "redirect_to": "/api/v2/training/{city}",
        },
        headers={
            "Location":    "/api/v2/training/all",
            "Deprecation": 'version="v1"; sunset="2026-08-01"',
        },
    )
