"""
WebSocket endpoints.
JWT is passed as a query param (?token=...) because browser WebSocket
handshake cannot carry custom Authorization headers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from .manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])


async def _auth_or_close(ws: WebSocket, token: str) -> bool:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        return True
    except Exception as e:
        logger.warning(f"WS auth failed: {e}")
        await ws.close(code=4001, reason="Unauthorized")
        return False


@router.websocket("/anomalies")
async def ws_anomalies(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    if not await _auth_or_close(websocket, token):
        return
    await manager.connect(websocket, "anomalies")
    try:
        while True:
            # Keep connection alive; ignore incoming messages (server-push only)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "anomalies")


@router.websocket("/risk-map")
async def ws_risk_map(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    if not await _auth_or_close(websocket, token):
        return
    await manager.connect(websocket, "risk-map")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "risk-map")


@router.websocket("/health")
async def ws_health(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """Unauthenticated health channel — used by dashboard status panel."""
    await manager.connect(websocket, "health")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "health")
