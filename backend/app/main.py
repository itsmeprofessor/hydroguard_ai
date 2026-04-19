"""
HydroGuard-AI — FastAPI Application Factory
============================================
"""

from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import APIConfig, LOGGING_CONFIG, STATIC_DIR
from app.db import init_db
from app.services import anomaly_service

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

APP_VERSION = "2.0.0"
APP_TITLE   = "HydroGuard-AI — Weather Anomaly Detection API"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {APP_TITLE} v{APP_VERSION}")
    init_db()
    info = anomaly_service.get_model_info()
    logger.info(f"Model status: {info.get('status')} | Type: {info.get('model_type', 'N/A')}")
    yield
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title       = APP_TITLE,
        version     = APP_VERSION,
        docs_url    = "/docs",
        redoc_url   = "/redoc",
        lifespan    = lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = APIConfig.CORS_ORIGINS,
        allow_credentials = True,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # Serve built frontend assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(
            status_code = exc.status_code,
            content     = {"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code = 500,
            content     = {"error": "Internal server error", "detail": str(exc)},
        )

    # Routers
    app.include_router(api_router)

    return app


app = create_app()
