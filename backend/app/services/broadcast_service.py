"""
Broadcast Service — called after each prediction to push results to WS clients.
Only broadcasts when the result is actually interesting (anomaly or elevated HRI).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.realtime.manager import manager

logger = logging.getLogger(__name__)


async def emit_anomaly(result: Dict[str, Any]) -> None:
    """Broadcast a prediction result on the anomalies channel."""
    try:
        hri = result.get("hri_score") or 0
        if not result.get("is_anomaly") and hri < 40:
            return  # skip low-noise normal readings

        await manager.broadcast("anomalies", {
            "city":             result.get("city"),
            "date":             result.get("date"),
            "anomaly_score":    result.get("anomaly_score"),
            "risk_level":       result.get("risk_level"),
            "hri_score":        hri,
            "hri_label":        result.get("hri_label"),
            "is_anomaly":       result.get("is_anomaly"),
            "cloudburst_likely": result.get("cloudburst_risk", {}).get("is_cloudburst_likely", False),
            "remarks":          result.get("remarks"),
        })
    except Exception as e:
        logger.warning(f"broadcast emit_anomaly failed: {e}")


async def emit_risk_map(entries: List[Dict[str, Any]]) -> None:
    """Broadcast updated city risk scores on the risk-map channel."""
    try:
        await manager.broadcast("risk-map", {"entries": entries})
    except Exception as e:
        logger.warning(f"broadcast emit_risk_map failed: {e}")


async def emit_health(status: Dict[str, Any]) -> None:
    """Broadcast system health update on the health channel."""
    try:
        await manager.broadcast("health", status)
    except Exception as e:
        logger.warning(f"broadcast emit_health failed: {e}")
