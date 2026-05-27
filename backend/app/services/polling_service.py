"""
WeatherPollingService — background weather polling for all discovered cities.

Responsibility: schedule, fetch, trigger, forward.
NOT responsible for: alert classification, DB persistence logic,
broadcaster selection, inference behaviour, notification policy.

Persistence rule: only ADVISORY and ALERT tier results write to DB.
NORMAL readings are not persisted to prevent analytics noise.

Event emission: calls runtime.emit_result() — the single event origin.
Never calls broadcaster directly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WeatherPollingService:
    def __init__(
        self,
        weather_provider,
        city_model_service,
        *,
        interval_seconds: int = 900,
    ) -> None:
        self._weather = weather_provider
        self._models  = city_model_service
        self._interval = interval_seconds
        self._last_snapshots: dict[str, dict] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="weather_polling")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_all()

    async def _poll_all(self) -> None:
        slugs = self._models.list_slugs()
        results = await asyncio.gather(
            *[self._poll_city(s) for s in slugs],
            return_exceptions=True,
        )
        for slug, result in zip(slugs, results):
            if isinstance(result, Exception):
                logger.error("polling_failed city=%s error=%s", slug, result)

    async def _poll_city(self, slug: str) -> None:
        snap = await self._weather.get_current(slug, force_refresh=True)
        if snap is None:
            return

        raw = snap.to_feature_dict()
        prev = self._last_snapshots.get(slug, {})
        if not self._has_significant_change(prev, raw):
            return

        result = await self._models.predict_v2(slug, raw)

        from app.runtime import system_runtime as runtime
        await runtime.emit_result(result)

        if result.get("alert_tier_label") != "NORMAL":
            asyncio.create_task(
                _persist_result_background(result, raw),
                name=f"persist_{slug}",
            )

        self._last_snapshots[slug] = raw
        logger.info(
            "polling_updated city=%s tier=%s p=%.3f",
            slug,
            result.get("alert_tier_label", "?"),
            result.get("event_probability", 0.0),
        )

    def _has_significant_change(self, prev: dict, curr: dict) -> bool:
        if not prev:
            return True
        try:
            from app.runtime.system_runtime import FEATURE_FLAGS
            sens = FEATURE_FLAGS.get("polling_sensitivity", {})
        except Exception:
            sens = {}
        prcp_delta     = sens.get("prcp_delta", 0.5)
        pressure_delta = sens.get("pressure_delta", 1.5)
        humidity_delta = sens.get("humidity_delta", 5.0)

        return (
            abs(curr.get("prcp", 0) - prev.get("prcp", 0)) > prcp_delta
            or abs(curr.get("pressure_mb", 1013) - prev.get("pressure_mb", 1013)) > pressure_delta
            or abs(curr.get("humidity", 60) - prev.get("humidity", 60)) > humidity_delta
        )


async def _persist_result_background(result: dict[str, Any], weather: dict[str, Any]) -> None:
    """Best-effort DB persistence from polling. Only called for ADVISORY/ALERT tier."""
    try:
        from app.db import get_db, AnomalyRepository
        risk_band = result.get("risk_band", "Low")
        v1_result = {
            "city":          result.get("city_slug") or result.get("city"),
            "date":          result.get("inferred_at"),
            "anomaly_score": result.get("event_probability", 0.0),
            "threshold":     0.5,
            "is_anomaly":    result.get("is_alert", False),
            "risk_level":    risk_band,
            "hri_score":     {"Low": 12, "Moderate": 40, "High": 68, "Severe": 88}.get(risk_band, 12),
            "hri_label":     risk_band,
            "remarks":       f"polling · tier={result.get('alert_tier_label')} · source={result.get('source')}",
        }
        with get_db() as db:
            AnomalyRepository(db).create(prediction_result=v1_result, weather_data=weather)
    except Exception as exc:
        logger.debug("polling persist failed: %s", exc)
