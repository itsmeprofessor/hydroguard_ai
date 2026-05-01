"""
HydroGuard-AI — FastAPI Application Factory v3.0
"""

from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import api_router
from app.api.routes import analytics_aliases
from app.api.routes.city_predictions import router as city_router
from app.auth.router import router as auth_router
from app.core.config import APIConfig, LOGGING_CONFIG, STATIC_DIR
from app.db import init_db
from app.realtime import realtime_router
from app.services import anomaly_service
from app.services.city_model_service import city_model_service

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

APP_VERSION = "3.0.0"
APP_TITLE   = "HydroGuard-AI — Weather Anomaly Detection API"

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {APP_TITLE} v{APP_VERSION}")
    init_db()
    info = anomaly_service.get_model_info()
    logger.info(f"Global model status: {info.get('status')} | Type: {info.get('model_type', 'N/A')}")
    status = city_model_service.model_status()
    logger.info(
        f"City models: {status['trained_cities']}/{status['total_cities']} trained "
        f"| Untrained: {status['untrained']}"
    )
    yield
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title    = APP_TITLE,
        version  = APP_VERSION,
        docs_url = "/docs",
        redoc_url= "/redoc",
        lifespan = lifespan,
    )

    # Rate limiter state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS — read from env; never wildcard with credentials
    origins = [o.strip() for o in APIConfig.CORS_ORIGINS if o.strip()]
    if "*" in origins:
        # Dev-only: allow all but disable credentials
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
        )

    # Static files — all assets served from /static/…
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Dashboard entry-point: GET /frontend  →  index.html
    # (index.html uses absolute /static/… paths so it works from any URL)
    @app.get("/frontend", include_in_schema=False)
    async def serve_frontend():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "Frontend not built"}, status_code=404)

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code = exc.status_code,
            content     = {"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code = 500,
            content     = {"error": "Internal server error", "detail": str(exc)},
        )

    # Routers
    app.include_router(auth_router)
    app.include_router(api_router)
    app.include_router(analytics_aliases.router)
    app.include_router(realtime_router)
    app.include_router(city_router)          # City-specific endpoints

    # Citizen app static mount (served at /citizen)
    citizen_dir = STATIC_DIR.parent.parent / "citizen_app"
    if citizen_dir.exists():
        app.mount("/citizen", StaticFiles(directory=str(citizen_dir), html=True), name="citizen")

    @app.get("/citizen-app", include_in_schema=False)
    async def serve_citizen():
        index = citizen_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "Citizen app not found"}, status_code=404)

    return app


app = create_app()
