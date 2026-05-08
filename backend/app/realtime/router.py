"""
WebSocket endpoints.

Authentication strategy:
  • /ws/anomalies  — requires JWT access token (?token=...)
  • /ws/risk-map   — requires JWT access token (?token=...)
  • /ws/health     — PUBLIC (no auth required, used by dashboard status panel)

JWT is passed as a query param because browsers cannot send custom
Authorization headers during the WebSocket handshake.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from .manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])


async def _auth_or_close(ws: WebSocket, token: str) -> bool:
    """Validate JWT and close socket with 4001 if invalid."""
    from datetime import datetime, timezone
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        # Belt-and-suspenders expiry check (jose already validates, but be explicit)
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise ValueError("Token expired")
        return True
    except Exception as e:
        logger.warning("WS auth failed: %s", e)
        await ws.close(code=4001, reason="Unauthorized")
        return False


@router.websocket("/anomalies")
async def ws_anomalies(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """Authenticated WebSocket: server pushes anomaly events."""
    if not await _auth_or_close(websocket, token):
        return
    await manager.connect(websocket, "anomalies")
    try:
        while True:
            # Server-push only; ignore any incoming messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "anomalies")


@router.websocket("/risk-map")
async def ws_risk_map(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """Authenticated WebSocket: server pushes risk-map updates."""
    if not await _auth_or_close(websocket, token):
        return
    await manager.connect(websocket, "risk-map")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "risk-map")


@router.websocket("/health")
async def ws_health(websocket: WebSocket):
    """
    PUBLIC WebSocket — no authentication required.
    Used by the dashboard status panel to display service health.
    Token parameter intentionally absent.
    """
    await manager.connect(websocket, "health")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, "health")
