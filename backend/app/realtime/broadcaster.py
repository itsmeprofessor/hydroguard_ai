from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.realtime.manager import ConnectionManager

logger = logging.getLogger(__name__)


class AbstractBroadcaster(ABC):
    @abstractmethod
    async def broadcast(self, channel: str, data: dict) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class LocalBroadcaster(AbstractBroadcaster):
    """Single-worker broadcaster. Wraps ConnectionManager — untouched."""

    def __init__(self, manager: "ConnectionManager") -> None:
        self._manager = manager

    async def broadcast(self, channel: str, data: dict) -> None:
        await self._manager.broadcast(channel, data)

    async def close(self) -> None:
        pass  # ConnectionManager has no teardown


class RedisBroadcaster(AbstractBroadcaster):
    """Multi-worker broadcaster. Dormant unless WORKER_MODE='multi'.

    Publishes events to Redis pub/sub. Subscriber tasks (started by bootstrap,
    not at import time) listen on Redis channels and forward to the local
    ConnectionManager for each worker's WS clients.

    Subscribers are transport-pure: they forward payloads unchanged.
    No business logic, no payload mutation, no inference triggering.
    """

    CHANNEL_PREFIX = "hg:ws:"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._subscriber_tasks: list[asyncio.Task] = []

    async def broadcast(self, channel: str, data: dict) -> None:
        await self._redis.publish(
            f"{self.CHANNEL_PREFIX}{channel}",
            json.dumps(data),
        )

    async def start_subscribers(self, manager: "ConnectionManager") -> None:
        """Start one forwarding task per WS channel.

        Called by bootstrap.run() — never at import time.
        Tasks are owned by this broadcaster instance; cancelled in close().
        """
        # Determine the WS channels — try to import CHANNELS from manager,
        # fall back to the known set if not defined there.
        try:
            from app.realtime.manager import CHANNELS
            channels = CHANNELS
        except ImportError:
            channels = ["anomalies", "risk-map", "health"]

        for channel in channels:
            task = asyncio.create_task(
                self._subscribe_and_forward(channel, manager),
                name=f"redis_sub_{channel}",
            )
            self._subscriber_tasks.append(task)
        logger.info("RedisBroadcaster: %d subscriber tasks started", len(channels))

    async def _subscribe_and_forward(
        self, channel: str, manager: "ConnectionManager"
    ) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"{self.CHANNEL_PREFIX}{channel}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(channel, data)
                except Exception as exc:
                    logger.warning("redis_forward error channel=%s: %s", channel, exc)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"{self.CHANNEL_PREFIX}{channel}")
            raise

    async def close(self) -> None:
        for task in self._subscriber_tasks:
            task.cancel()
        await asyncio.gather(*self._subscriber_tasks, return_exceptions=True)
        self._subscriber_tasks.clear()
