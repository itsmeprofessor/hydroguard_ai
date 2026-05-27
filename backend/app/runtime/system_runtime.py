from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.realtime.broadcaster import AbstractBroadcaster

logger = logging.getLogger(__name__)

# Increment when emit_result_event / emit_health_event field schema changes.
# Consumers must check this before parsing structured log lines.
EMIT_EVENT_SCHEMA_VERSION = "1.0"

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

async def emit_result(result: dict[str, Any], *, origin: str = "unknown") -> None:
    """The ONLY place in the codebase allowed to call ACTIVE_BROADCASTER.broadcast().

    All code paths — HTTP endpoints, polling, background tasks — must call this
    function. Never call ACTIVE_BROADCASTER.broadcast() directly elsewhere.

    Emits a structured audit event to the log before every broadcast so that
    every emission is reconstructable: who triggered it, what the model said,
    which thresholds were active, and what tier decision was produced.
    """
    if ACTIVE_BROADCASTER is None:
        return
    hri = result.get("hri_score") or 0  # None and 0 both map to 0; both below threshold
    if not result.get("is_alert") and hri < 40:
        return  # skip low-noise NORMAL readings

    # Structured audit trace — schema-versioned, machine-consumable.
    # IMPORTANT: field names are a versioned contract. Do not rename without
    # bumping EMIT_EVENT_SCHEMA_VERSION and updating any log consumers.
    audit = {
        "schema_version":          EMIT_EVENT_SCHEMA_VERSION,
        "event_id":                str(uuid.uuid4()),
        "ts":                      datetime.now(timezone.utc).isoformat(),
        "origin":                  origin,
        "city_slug":               result.get("city_slug") or result.get("city"),
        "model_version":           result.get("model_version"),
        "probability_calibrated":  result.get("event_probability"),
        "hri_score":               result.get("hri_score"),
        "alert_tier_label":        result.get("alert_tier_label"),
        "push_notification":       result.get("push_notification"),
        "is_alert":                result.get("is_alert"),
        "advisory_threshold":      result.get("advisory_tier_threshold"),
        "alert_threshold":         result.get("alert_tier_threshold"),
        "threshold_source":        result.get("threshold_source"),
    }
    logger.info("emit_result_event %s", json.dumps(audit))

    try:
        await ACTIVE_BROADCASTER.broadcast("anomalies", result)
    except Exception as exc:
        logger.warning("emit_result broadcast failed: %s", exc)


async def emit_health(payload: dict[str, Any], *, origin: str = "health_collector") -> None:
    """Route health broadcasts through the control plane (health channel).

    Replaces direct manager.broadcast('health', ...) calls so all channels
    flow through ACTIVE_BROADCASTER and gain Redis fan-out automatically.
    """
    if ACTIVE_BROADCASTER is None:
        return

    audit = {
        "schema_version": EMIT_EVENT_SCHEMA_VERSION,
        "event_id":       str(uuid.uuid4()),
        "ts":             datetime.now(timezone.utc).isoformat(),
        "origin":         origin,
        "channel":        "health",
    }
    logger.debug("emit_health_event %s", json.dumps(audit))

    try:
        await ACTIVE_BROADCASTER.broadcast("health", payload)
    except Exception as exc:
        logger.warning("emit_health broadcast failed: %s", exc)
