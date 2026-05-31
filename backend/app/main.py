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
)
from app.core.limiter import limiter   # ← single shared instance
from app.realtime import realtime_router

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

APP_VERSION = "3.3.0"
APP_TITLE   = "HydroGuard-AI — Adaptive Flood Intelligence API"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting %s v%s ===", APP_TITLE, APP_VERSION)
    from app.runtime import bootstrap
    await bootstrap.run(app)
    yield
    await bootstrap.shutdown()


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

    # ── Flutter citizen app static mount ──────────────────────────────────────
    flutter_dir = STATIC_DIR  # frontend/citizen_flutter_app/build/web (set in config.py)
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
