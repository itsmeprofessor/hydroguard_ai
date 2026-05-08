"""
WebSocket Connection Manager.
Push-based: server broadcasts to all connected clients on a channel.
Uses asyncio.Lock to prevent race conditions during concurrent
connect/disconnect/broadcast operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

CHANNELS = ("anomalies", "risk-map", "health")


class ConnectionManager:
    def __init__(self):
        self._channels: Dict[str, Set[WebSocket]] = {ch: set() for ch in CHANNELS}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)
        logger.info("WS connect: channel=%s total=%d", channel, len(self._channels[channel]))

    async def disconnect(self, ws: WebSocket, channel: str) -> None:
        async with self._lock:
            self._channels.get(channel, set()).discard(ws)
        logger.debug("WS disconnect: channel=%s", channel)

    async def broadcast(self, channel: str, data: dict) -> None:
        payload = json.dumps({
            "channel": channel,
            "data":    data,
            "ts":      time.time(),
        })
        # Snapshot under lock, then release before sending
        async with self._lock:
            targets = list(self._channels.get(channel, set()))

        dead: Set[WebSocket] = set()
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels.get(channel, set()).discard(ws)

    def connection_counts(self) -> Dict[str, int]:
        return {ch: len(sockets) for ch, sockets in self._channels.items()}


manager = ConnectionManager()
