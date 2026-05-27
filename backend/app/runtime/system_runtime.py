from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.realtime.broadcaster import AbstractBroadcaster

logger = logging.getLogger(__name__)

# ── Runtime state ─────────────────────────────────────────────────────────────

WORKER_MODE: str = "multi" if int(os.getenv("WORKERS", "1")) > 1 else "single"

ACTIVE_BROADCASTER: "AbstractBroadcaster | None" = None

FEATURE_FLAGS: dict[str, Any] = {
    "polling_enabled":  True,
    "redis_ws_enabled": False,
    "polling_sensitivity": {
        "prcp_delta":     0.5,   # mm — minimum precipitation change to trigger inference
        "pressure_delta": 1.5,   # hPa
        "humidity_delta": 5.0,   # %
    },
}

# ── Single event origin ───────────────────────────────────────────────────────

async def emit_result(result: dict[str, Any]) -> None:
    """The ONLY place in the codebase allowed to call ACTIVE_BROADCASTER.broadcast().

    All code paths — HTTP endpoints, polling, background tasks — must call this
    function. Never call ACTIVE_BROADCASTER.broadcast() directly elsewhere.
    """
    if ACTIVE_BROADCASTER is None:
        return
    hri = result.get("hri_score") or 0  # None and 0 both map to 0; both below threshold
    if not result.get("is_alert") and hri < 40:
        return  # skip low-noise NORMAL readings
    try:
        await ACTIVE_BROADCASTER.broadcast("anomalies", result)
    except Exception as exc:
        logger.warning("emit_result broadcast failed: %s", exc)


async def emit_health(payload: dict[str, Any]) -> None:
    """Route health broadcasts through the control plane (health channel).

    Replaces direct manager.broadcast('health', ...) calls so all channels
    flow through ACTIVE_BROADCASTER and gain Redis fan-out automatically.
    """
    if ACTIVE_BROADCASTER is None:
        return
    try:
        await ACTIVE_BROADCASTER.broadcast("health", payload)
    except Exception as exc:
        logger.warning("emit_health broadcast failed: %s", exc)
