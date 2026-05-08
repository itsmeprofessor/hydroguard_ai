"""
HydroGuard-AI -- Event Bus
============================
Redis pub/sub fan-out + WebSocket broadcast wrapper.
Replaces direct broadcast_service.emit_* calls.

Channels:
  "prediction"  -> WS "anomalies" channel
  "drift_alert" -> WS "health" channel
  "risk_map"    -> WS "risk-map" channel

publish() is fire-and-forget: errors are logged, never re-raised.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# WS channel mapping
_EVENT_TO_WS = {
    "prediction":  "anomalies",
    "drift_alert": "health",
    "risk_map":    "risk-map",
}

# Redis pub/sub channel names
_REDIS_CHANNEL_PREFIX = "hg:events:"


class EventBus:
    """
    Dual-path event publisher:
      1. Redis pub/sub (for cross-worker fan-out, future use)
      2. WebSocket broadcast via ConnectionManager (current worker)

    Both paths are best-effort; failures are logged at WARNING level.
    """

    def __init__(self, redis_client=None, ws_manager=None):
        self._redis   = redis_client
        self._manager = ws_manager

    async def publish(
        self,
        event_type: str,
        data:       Dict[str, Any],
    ) -> None:
        """
        Publish an event to Redis + WebSocket.

        Parameters
        ----------
        event_type : "prediction" | "drift_alert" | "risk_map"
        data       : event payload dict (must be JSON-serialisable)
        """
        ws_channel = _EVENT_TO_WS.get(event_type, "health")

        # ---- 1. Redis pub/sub ----
        if self._redis is not None:
            try:
                payload = json.dumps({
                    "event_type": event_type,
                    "data":       data,
                    "ts":         time.time(),
                })
                await self._redis.publish(
                    f"{_REDIS_CHANNEL_PREFIX}{event_type}", payload
                )
            except Exception as exc:
                logger.debug("EventBus Redis publish failed: %s", exc)

        # ---- 2. WebSocket broadcast ----
        if self._manager is not None:
            try:
                await self._manager.broadcast(ws_channel, data)
            except Exception as exc:
                logger.warning("EventBus WS broadcast failed: %s", exc)

    async def publish_prediction(self, event_dict: Dict[str, Any]) -> None:
        """Convenience wrapper for prediction events."""
        # Only broadcast if is_alert or high probability
        p = event_dict.get("event_probability") or 0.0
        if not event_dict.get("is_alert") and p < 0.40:
            return   # skip low-signal events
        await self.publish("prediction", {
            "inference_id":      event_dict.get("inference_id"),
            "city":              event_dict.get("city"),
            "city_slug":         event_dict.get("city_slug"),
            "event_probability": p,
            "risk_band":         event_dict.get("risk_band"),
            "is_alert":          event_dict.get("is_alert"),
            "inferred_at":       event_dict.get("inferred_at"),
        })

    async def publish_drift_alert(
        self,
        city_slug: str,
        max_psi:   float,
        level:     str,
    ) -> None:
        """Convenience wrapper for drift alert events."""
        await self.publish("drift_alert", {
            "city_slug": city_slug,
            "max_psi":   max_psi,
            "level":     level,
        })


# Singleton -- set in lifespan
event_bus: Optional[EventBus] = None


def init_event_bus(redis_client=None, ws_manager=None) -> EventBus:
    """Initialise and return the global EventBus singleton."""
    global event_bus
    from app.realtime.manager import manager as _manager
    event_bus = EventBus(
        redis_client = redis_client,
        ws_manager   = ws_manager or _manager,
    )
    logger.info("EventBus initialised")
    return event_bus


def get_event_bus() -> Optional[EventBus]:
    return event_bus
