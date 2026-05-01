"""
WebSocket Connection Manager.
Push-based: server broadcasts to all connected clients on a channel.
Thread-safe with asyncio — never call from sync code.
"""

from __future__ import annotations

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

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        self._channels.setdefault(channel, set()).add(ws)
        logger.info(f"WS connect: channel={channel} total={len(self._channels[channel])}")

    def disconnect(self, ws: WebSocket, channel: str) -> None:
        self._channels.get(channel, set()).discard(ws)
        logger.debug(f"WS disconnect: channel={channel}")

    async def broadcast(self, channel: str, data: dict) -> None:
        payload = json.dumps({
            "channel": channel,
            "data":    data,
            "ts":      time.time(),
        })
        dead: Set[WebSocket] = set()
        for ws in list(self._channels.get(channel, set())):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._channels.get(channel, set()).discard(ws)

    def connection_counts(self) -> Dict[str, int]:
        return {ch: len(sockets) for ch, sockets in self._channels.items()}


manager = ConnectionManager()
