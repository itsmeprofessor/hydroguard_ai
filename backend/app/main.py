"""
HydroGuard-AI — FastAPI Application Factory v3.2
"""

from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import api_router
from app.api.routes import analytics_aliases
from app.api.routes.city_predictions import router as city_router
from app.auth.router import router as auth_router
from app.core.config import (
    APIConfig, LOGGING_CONFIG, STATIC_DIR,
    validate_startup_secrets,
    REDIS_URL, WEATHERAPI_KEY,
)
from app.core.limiter import limiter   # ← single shared instance
from app.db import init_db
from app.realtime import realtime_router
from app.core.redis_pool import init_redis, close_redis, get_redis
from app.services.city_model_service import city_model_service
from app.services.weather_api import init_weather_provider

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

APP_VERSION = "3.2.0"
APP_TITLE   = "HydroGuard-AI — Adaptive Flood Intelligence API"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting %s v%s ===", APP_TITLE, APP_VERSION)

    # 1. Validate required secrets (exits in production if JWT_SECRET_KEY is missing/placeholder)
    validate_startup_secrets(strict=True)

    # 2. Init database tables
    init_db()

    # 3. Init Redis connection pool
    try:
        await init_redis(REDIS_URL)
        logger.info("Redis connection pool initialised")
    except Exception as exc:
        logger.warning("Redis init failed (non-fatal — some features degraded): %s", exc)

    # 4. Init WeatherAPI provider
    try:
        redis_client = None
        try:
            redis_client = get_redis()
        except RuntimeError:
            pass
        init_weather_provider(redis_client=redis_client)
        logger.info("WeatherAPI provider initialised")
    except Exception as exc:
        logger.warning("WeatherAPI provider init failed (non-fatal): %s", exc)

    # 4.5 Init RollingWindowBuffer
    try:
        from app.services.rolling_window import init_rolling_window
        _rw_redis = None
        try:
            _rw_redis = get_redis()
        except RuntimeError:
            pass
        init_rolling_window(_rw_redis)
        logger.info("RollingWindowBuffer initialised")
    except Exception as exc:
        logger.warning("RollingWindowBuffer init failed: %s", exc)

    # 4.6 Init EventBus
    try:
        from app.services.event_bus import init_event_bus
        _eb_redis = None
        try:
            _eb_redis = get_redis()
        except RuntimeError:
            pass
        init_event_bus(redis_client=_eb_redis)
        logger.info("EventBus initialised")
    except Exception as exc:
        logger.warning("EventBus init failed: %s", exc)

    # 4.7 Init DriftMonitor
    try:
        from app.ml.drift.monitor import init_drift_monitor
        _dm_redis = None
        try:
            _dm_redis = get_redis()
        except RuntimeError:
            pass
        init_drift_monitor(_dm_redis)
    except Exception as exc:
        logger.warning("DriftMonitor init failed: %s", exc)

    # 4.8 Init CalibrationService
    try:
        from app.services.calibration_service import init_calibration_service
        init_calibration_service()
        logger.info("CalibrationService initialised")
    except Exception as exc:
        logger.warning("CalibrationService init failed: %s", exc)

    # 5. City model registry
    status = city_model_service.model_status()
    logger.info(
        "City models: %d/%d trained | Untrained: %s",
        status["trained_cities"], status["total_cities"],
        status["untrained"],
    )

    # 6. DriftMonitor already initialised in step 4.7 above
    try:
        from app.ml.drift.monitor import get_drift_monitor, MONITORED_FEATURES
        dm = get_drift_monitor()
        if dm is not None:
            logger.info("DriftMonitor active (monitoring %d features)", len(MONITORED_FEATURES))
    except Exception as exc:
        logger.warning("DriftMonitor status check failed: %s", exc)

    # 7. Warm up TCN rolling buffers so first predictions are not cold-start zeros
    try:
        await city_model_service.warm_up_tcn_buffers()
    except Exception as exc:
        logger.warning("TCN warm-up failed (non-fatal): %s", exc)

    # 8. Start runtime health collector (non-blocking background ticks)
    _health_collector = None
    try:
        from app.services.health_collector import get_health_collector
        _health_collector = get_health_collector()
        _health_collector.start()
        logger.info("RuntimeHealthCollector started")
    except Exception as exc:
        logger.warning("RuntimeHealthCollector start failed (non-fatal): %s", exc)

    logger.info("=== HydroGuard-AI ready ===")
    yield

    # Shutdown
    if _health_collector is not None:
        try:
            await _health_collector.stop()
        except Exception as exc:
            logger.warning("RuntimeHealthCollector stop error: %s", exc)
    try:
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)
    logger.info("Shutdown complete.")


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers on every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # HSTS only over HTTPS — nginx sets it; FastAPI adds as belt-and-suspenders.
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title    = APP_TITLE,
        version  = APP_VERSION,
        docs_url = "/docs",
        redoc_url= "/redoc",
        lifespan = lifespan,
    )

    # ── Security headers ──────────────────────────────────────────────────────
    app.add_middleware(_SecurityHeadersMiddleware)

    # ── Rate limiter (shared, single instance) ────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS — never wildcard with credentials ────────────────────────────────
    origins = [o.strip() for o in APIConfig.CORS_ORIGINS if o.strip()]
    if "*" in origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins     = ["*"],
            allow_credentials = False,
            allow_methods     = ["*"],
            allow_headers     = ["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins     = origins,
            allow_credentials = True,
            allow_methods     = ["*"],
            allow_headers     = ["*"],
            expose_headers    = ["X-Request-ID"],
        )

    # ── Static files ──────────────────────────────────────────────────────────
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code = exc.status_code,
            content     = {"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code = 500,
            content     = {"error": "Internal server error"},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(api_router)
    app.include_router(analytics_aliases.router)
    app.include_router(realtime_router)
    app.include_router(city_router)

    # ── v2 API ────────────────────────────────────────────────────────────────
    try:
        from app.api.v2.router import v2_router
        app.include_router(v2_router)
        logger.info("v2 API router registered at /api/v2")
    except Exception as exc:
        logger.warning("v2 router unavailable: %s", exc)

    # ── Weather API routes ────────────────────────────────────────────────────
    try:
        from app.api.routes.weather import router as weather_router
        app.include_router(weather_router)
        logger.info("Weather API routes registered")
    except Exception as exc:
        logger.warning("Weather API routes unavailable: %s", exc)

    # ── Citizen app static mount ──────────────────────────────────────────────
    citizen_dir = STATIC_DIR.parent.parent / "citizen_app"
    if citizen_dir.exists():
        app.mount("/citizen", StaticFiles(directory=str(citizen_dir), html=True), name="citizen")

    @app.get("/citizen-app", include_in_schema=False)
    async def serve_citizen():
        index = citizen_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "Citizen app not found"}, status_code=404)

    # ── Flutter citizen app static mount ──────────────────────────────────────
    flutter_dir = STATIC_DIR.parent.parent / "citizen_flutter_app" / "build" / "web"
    if flutter_dir.exists():
        app.mount("/flutter", StaticFiles(directory=str(flutter_dir), html=True), name="flutter")
        logger.info("Flutter citizen app mounted at /flutter")

    @app.get("/flutter-app", include_in_schema=False)
    async def serve_flutter():
        index = flutter_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "Flutter app not built — run: flutter build web"}, status_code=404)

    return app


app = create_app()
