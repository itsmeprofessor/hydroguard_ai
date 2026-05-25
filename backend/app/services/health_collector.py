"""
HydroGuard-AI — Runtime Health Collector
==========================================
Three asyncio background tasks sample in-memory counters and the DriftMonitor,
then broadcast a SystemHealthSnapshot to /ws/health every HEALTH_TICK_INTERVAL_S.

No DB writes. No Redis writes. All state is in-memory; resets on restart.
"""
from __future__ import annotations

import asyncio
import logging
import math
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import HealthCollectorConfig
from app.schemas.health import CityHealthSnapshot, SystemHealthSnapshot

logger = logging.getLogger(__name__)


def _import_city_model_service() -> Any:
    """
    Return the city_model_service module, preferring whichever path is already
    in sys.modules (avoids double-import when tests use ``backend.app.*`` path).
    """
    for candidate in (
        "backend.app.services.city_model_service",
        "app.services.city_model_service",
    ):
        if candidate in sys.modules:
            return sys.modules[candidate]
    # Neither loaded yet — import via the canonical production path.
    import importlib
    return importlib.import_module("app.services.city_model_service")


class RuntimeHealthCollector:
    """
    Coordinates three asyncio tick tasks and merges their outputs into a
    single SystemHealthSnapshot broadcast on every inference tick.
    """

    def __init__(self) -> None:
        self._inference_state:  Dict[str, dict] = {}
        self._drift_state:      Dict[str, dict] = {}
        self._confidence_state: Dict[str, dict] = {}
        # Per-city epistemic warmup baseline: {slug: (warmup_mean, warmup_std)}
        self._epistemic_baseline: Dict[str, Tuple[float, float]] = {}
        self._tasks: List[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._tasks = [
            asyncio.ensure_future(self._loop_inference_health()),
            asyncio.ensure_future(self._loop_drift_health()),
            asyncio.ensure_future(self._loop_confidence_health()),
        ]
        logger.info(
            "RuntimeHealthCollector started (ticks: %ds / %ds / %ds)",
            HealthCollectorConfig.HEALTH_TICK_INTERVAL_S,
            HealthCollectorConfig.DRIFT_TICK_INTERVAL_S,
            HealthCollectorConfig.CONFIDENCE_TICK_INTERVAL_S,
        )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("RuntimeHealthCollector stopped")

    # ------------------------------------------------------------------
    # Tick loops
    # ------------------------------------------------------------------

    async def _loop_inference_health(self) -> None:
        while True:
            try:
                self._tick_inference_health()
                snapshot = self._build_snapshot()
                from app.services.broadcast_service import emit_health
                await emit_health(snapshot.model_dump(mode="json"))
            except Exception:
                logger.exception("Health collector inference tick failed")
            await asyncio.sleep(HealthCollectorConfig.HEALTH_TICK_INTERVAL_S)

    async def _loop_drift_health(self) -> None:
        while True:
            try:
                self._tick_drift_health()
            except Exception:
                logger.exception("Health collector drift tick failed")
            await asyncio.sleep(HealthCollectorConfig.DRIFT_TICK_INTERVAL_S)

    async def _loop_confidence_health(self) -> None:
        while True:
            try:
                self._tick_confidence_health()
            except Exception:
                logger.exception("Health collector confidence tick failed")
            await asyncio.sleep(HealthCollectorConfig.CONFIDENCE_TICK_INTERVAL_S)

    # ------------------------------------------------------------------
    # Domain 1 — Inference health (drives the 30s broadcast)
    # ------------------------------------------------------------------

    def _tick_inference_health(self) -> None:
        cms = _import_city_model_service()
        city_model_service    = cms.city_model_service
        get_mc_success_rate   = cms.get_mc_success_rate
        get_timeout_rate      = cms.get_timeout_rate
        get_preprocess_fail_rate = cms.get_preprocess_fail_rate
        cfg   = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            mc_rate   = get_mc_success_rate(slug)
            t_rate    = get_timeout_rate(slug)
            fail_rate = get_preprocess_fail_rate(slug)

            if mc_rate is None and fail_rate is None:
                health = "unknown"
            elif (
                (mc_rate  is not None and mc_rate  < cfg.MC_CRITICAL_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_CRITICAL)
            ):
                health = "critical"
            elif (
                (mc_rate  is not None and mc_rate  < cfg.MC_DEGRADED_THRESHOLD)
                or (fail_rate is not None and fail_rate > cfg.PREPROCESS_FAIL_DEGRADED)
            ):
                health = "degraded"
            else:
                health = "ok"

            state[slug] = {
                "mc_success_rate":      mc_rate,
                "timeout_rate":         t_rate,
                "preprocess_fail_rate": fail_rate,
                "inference_health":     health,
            }

        self._inference_state = state

    # ------------------------------------------------------------------
    # Domain 2 — Drift health (runs every 5 min)
    # ------------------------------------------------------------------

    def _tick_drift_health(self) -> None:
        from app.ml.drift.monitor import get_drift_monitor, PSI_WARN, PSI_CRIT
        city_model_service = _import_city_model_service().city_model_service

        monitor = get_drift_monitor()
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            if monitor is None:
                state[slug] = {"psi_max": None, "psi_status": "unknown", "top_drifted_feature": None}
                continue

            psi_results: dict = dict(getattr(monitor, "_latest_psi", {}).get(slug, {}))

            if not psi_results:
                state[slug] = {"psi_max": None, "psi_status": "unknown", "top_drifted_feature": None}
                continue

            psi_max  = max(psi_results.values())
            top_feat = max(psi_results, key=psi_results.__getitem__)

            if psi_max >= PSI_CRIT:
                psi_status = "critical"
            elif psi_max >= PSI_WARN:
                psi_status = "warn"
            else:
                psi_status = "ok"

            state[slug] = {
                "psi_max":             psi_max,
                "psi_status":          psi_status,
                "top_drifted_feature": top_feat,
            }

        self._drift_state = state

    # ------------------------------------------------------------------
    # Domain 3 — Epistemic confidence stability (runs every 60 min)
    # ------------------------------------------------------------------

    def _tick_confidence_health(self) -> None:
        cms = _import_city_model_service()
        city_model_service          = cms.city_model_service
        get_epistemic_buffer_snapshot = cms.get_epistemic_buffer_snapshot
        cfg   = HealthCollectorConfig
        state: Dict[str, dict] = {}

        for slug in city_model_service.list_slugs():
            buf = get_epistemic_buffer_snapshot(slug)

            if len(buf) < cfg.EPISTEMIC_WARMUP_MIN_SAMPLES:
                state[slug] = {
                    "epistemic_mean":      None,
                    "epistemic_std":       None,
                    "epistemic_drift":     None,
                    "epistemic_stability": "warming_up",
                    "baseline_ready":      False,
                }
                continue

            ep_mean = sum(buf) / len(buf)
            ep_var  = sum((x - ep_mean) ** 2 for x in buf) / len(buf)
            ep_std  = math.sqrt(ep_var) if ep_var > 0 else 1e-9

            # Establish baseline once from first EPISTEMIC_WARMUP_MIN_SAMPLES values
            if slug not in self._epistemic_baseline:
                warmup = buf[:cfg.EPISTEMIC_WARMUP_MIN_SAMPLES]
                wm     = sum(warmup) / len(warmup)
                wv     = sum((x - wm) ** 2 for x in warmup) / len(warmup)
                ws     = math.sqrt(wv) if wv > 0 else 1e-9
                self._epistemic_baseline[slug] = (wm, ws)

            wm, ws = self._epistemic_baseline[slug]
            drift  = abs(ep_mean - wm) / ws

            # 2σ/3σ bands derived from warmup distribution — no hardcoded values
            if drift < 2.0:
                stability = "stable"
            elif drift < 3.0:
                stability = "drifting"
            else:
                stability = "anomalous"

            state[slug] = {
                "epistemic_mean":      ep_mean,
                "epistemic_std":       ep_std,
                "epistemic_drift":     drift,
                "epistemic_stability": stability,
                "baseline_ready":      True,
            }

        self._confidence_state = state

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------

    def _build_snapshot(self) -> SystemHealthSnapshot:
        city_model_service = _import_city_model_service().city_model_service
        cities: Dict[str, CityHealthSnapshot] = {}

        for slug in city_model_service.list_slugs():
            inf  = self._inference_state.get(slug, {})
            dft  = self._drift_state.get(slug, {})
            conf = self._confidence_state.get(slug, {})

            cities[slug] = CityHealthSnapshot(
                city_slug=slug,
                mc_success_rate=inf.get("mc_success_rate"),
                timeout_rate=inf.get("timeout_rate"),
                preprocess_fail_rate=inf.get("preprocess_fail_rate"),
                inference_health=inf.get("inference_health", "unknown"),
                psi_max=dft.get("psi_max"),
                psi_status=dft.get("psi_status", "unknown"),
                top_drifted_feature=dft.get("top_drifted_feature"),
                epistemic_mean=conf.get("epistemic_mean"),
                epistemic_std=conf.get("epistemic_std"),
                epistemic_drift=conf.get("epistemic_drift"),
                epistemic_stability=conf.get("epistemic_stability", "warming_up"),
                baseline_ready=conf.get("baseline_ready", False),
            )

        statuses = [c.inference_health for c in cities.values()]
        non_unknown = [s for s in statuses if s != "unknown"]
        if "critical" in statuses:
            global_status = "critical"
        elif "degraded" in statuses:
            global_status = "degraded"
        elif non_unknown and all(s == "ok" for s in non_unknown):
            global_status = "ok"
        else:
            global_status = "unknown"

        return SystemHealthSnapshot(
            snapshot_at=datetime.now(timezone.utc),
            cities=cities,
            global_status=global_status,
            active_city_count=len(cities),
        )


# Module-level singleton
_collector: Optional[RuntimeHealthCollector] = None


def get_health_collector() -> RuntimeHealthCollector:
    global _collector
    if _collector is None:
        _collector = RuntimeHealthCollector()
    return _collector
