"""
Initialization sequence for HydroGuard-AI.

bootstrap.run(app) replaces the inline lifespan sequence in main.py.
bootstrap.shutdown() tears down in safe order: polling → health → broadcaster → redis.

Each step is non-fatal unless marked CRITICAL.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_polling_service = None
_health_collector = None


async def run(app: Any) -> None:  # noqa: ARG001
    global _polling_service, _health_collector

    # 1. Validate secrets (CRITICAL — exits in production if JWT_SECRET_KEY missing)
    from app.core.config import validate_startup_secrets
    validate_startup_secrets(strict=True)

    # 2. Alembic migrations → create_all safety net
    _run_migrations()
    from app.db import init_db
    init_db()

    # 3. Redis
    from app.core.config import REDIS_URL
    try:
        from app.core.redis_pool import init_redis
        await init_redis(REDIS_URL)
        logger.info("Redis connection pool initialised")
    except Exception as exc:
        logger.warning("Redis init failed (non-fatal): %s", exc)

    # 4. WeatherAPI
    try:
        from app.core.redis_pool import get_redis
        from app.services.weather_api import init_weather_provider
        _redis = None
        try:
            _redis = get_redis()
        except RuntimeError:
            pass
        init_weather_provider(redis_client=_redis)
        logger.info("WeatherAPI provider initialised")
    except Exception as exc:
        logger.warning("WeatherAPI init failed (non-fatal): %s", exc)

    # 5. Supporting services
    for _fn in (_init_rolling_window, _init_event_bus, _init_drift_monitor, _init_calibration_service):
        try:
            _fn()
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", _fn.__name__, exc)

    # 6. Broadcaster (selects Local or Redis based on WORKER_MODE)
    try:
        await _init_broadcaster()
    except Exception as exc:
        logger.warning("Broadcaster init failed (non-fatal): %s", exc)

    # 7. City model registry + TCN warm-up
    from app.services.city_model_service import city_model_service
    status = city_model_service.model_status()
    logger.info(
        "City models: %d/%d trained | Untrained: %s",
        status["trained_cities"], status["total_cities"], status["untrained"],
    )
    try:
        await city_model_service.warm_up_tcn_buffers()
    except Exception as exc:
        logger.warning("TCN warm-up failed (non-fatal): %s", exc)

    # 8. Alert tiers loaded inside _load_v2_artifacts() — no separate step needed.

    # 9. Weather polling (after models and warm-up are ready)
    try:
        _polling_service = _start_polling()
    except Exception as exc:
        logger.warning("WeatherPollingService start failed (non-fatal): %s", exc)

    # 10. Runtime health collector
    try:
        from app.services.health_collector import get_health_collector
        _health_collector = get_health_collector()
        _health_collector.start()
        logger.info("RuntimeHealthCollector started")
    except Exception as exc:
        logger.warning("RuntimeHealthCollector start failed (non-fatal): %s", exc)

    logger.info("=== HydroGuard-AI bootstrap complete ===")


async def shutdown() -> None:
    global _polling_service, _health_collector

    # Stop event sources before closing transport
    if _polling_service is not None:
        try:
            await _polling_service.stop()
            logger.info("WeatherPollingService stopped")
        except Exception as exc:
            logger.warning("PollingService stop error: %s", exc)

    if _health_collector is not None:
        try:
            await _health_collector.stop()
        except Exception as exc:
            logger.warning("HealthCollector stop error: %s", exc)

    # Close broadcaster after no more events can be generated
    import app.runtime.system_runtime as runtime
    if runtime.ACTIVE_BROADCASTER is not None:
        try:
            await runtime.ACTIVE_BROADCASTER.close()
        except Exception as exc:
            logger.warning("Broadcaster close error: %s", exc)

    try:
        from app.core.redis_pool import close_redis
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)

    logger.info("Shutdown complete.")


# ── Private helpers ───────────────────────────────────────────────────────────

def _run_migrations() -> None:
    try:
        from alembic import command
        from alembic.config import Config
        cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
        if not cfg_path.exists():
            logger.warning("alembic.ini not found at %s — skipping migrations", cfg_path)
            return
        command.upgrade(Config(str(cfg_path)), "head")
        logger.info("Alembic: schema up to date")
    except Exception as exc:
        logger.warning("Alembic migration failed (create_all will handle schema): %s", exc)


async def _init_broadcaster() -> None:
    import app.runtime.system_runtime as runtime
    from app.realtime.manager import manager
    from app.realtime.broadcaster import LocalBroadcaster, RedisBroadcaster

    if runtime.WORKER_MODE == "multi":
        try:
            from app.core.redis_pool import get_redis
            broadcaster = RedisBroadcaster(get_redis())
            await broadcaster.start_subscribers(manager)
            runtime.ACTIVE_BROADCASTER = broadcaster
            runtime.FEATURE_FLAGS["redis_ws_enabled"] = True
            logger.info("RedisBroadcaster activated (multi-worker mode)")
            return
        except Exception as exc:
            logger.warning("RedisBroadcaster failed, falling back to LocalBroadcaster: %s", exc)

    runtime.ACTIVE_BROADCASTER = LocalBroadcaster(manager)
    logger.info("LocalBroadcaster activated (single-worker mode)")


def _start_polling():
    from app.core.config import WEATHERAPI_KEY
    from app.services.weather_api import weather_provider
    from app.services.city_model_service import city_model_service
    from app.services.polling_service import WeatherPollingService

    if not WEATHERAPI_KEY:
        logger.warning("WEATHERAPI_KEY not set — weather polling disabled")
        return None

    interval = int(os.getenv("POLLING_INTERVAL_SECONDS", "900"))
    svc = WeatherPollingService(
        weather_provider=weather_provider,
        city_model_service=city_model_service,
        interval_seconds=interval,
    )
    svc.start()
    logger.info("WeatherPollingService started (interval=%ds)", interval)
    return svc


def _init_rolling_window() -> None:
    from app.services.rolling_window import init_rolling_window
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_rolling_window(_r)
    logger.info("RollingWindowBuffer initialised")


def _init_event_bus() -> None:
    from app.services.event_bus import init_event_bus
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_event_bus(redis_client=_r)
    logger.info("EventBus initialised")


def _init_drift_monitor() -> None:
    from app.ml.drift.monitor import init_drift_monitor
    _r = None
    try:
        from app.core.redis_pool import get_redis
        _r = get_redis()
    except RuntimeError:
        pass
    init_drift_monitor(_r)
    logger.info("DriftMonitor initialised")


def _init_calibration_service() -> None:
    from app.services.calibration_service import init_calibration_service
    init_calibration_service()
    logger.info("CalibrationService initialised")
