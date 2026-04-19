"""System / health routes."""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import STATIC_DIR
from app.schemas import HealthResponse, ModelInfoResponse
from app.services import anomaly_service

router = APIRouter(tags=["System"])

APP_VERSION = "2.0.0"
APP_TITLE   = "HydroGuard-AI — Weather Anomaly Detection API"


@router.get("/")
async def root():
    return {
        "name":    APP_TITLE,
        "version": APP_VERSION,
        "status":  "running",
        "endpoints": {
            "docs":      "/docs",
            "health":    "/health",
            "frontend":  "/frontend",
            "predict":   "/predict",
            "risk_map":  "/risk-map",
            "analytics": "/analytics",
        },
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    info = anomaly_service.get_model_info()
    return HealthResponse(
        status       = "healthy",
        version      = APP_VERSION,
        model_loaded = anomaly_service.is_trained,
        model_type   = info.get("model_type") if anomaly_service.is_trained else None,
        timestamp    = datetime.utcnow().isoformat() + "Z",
    )


@router.get("/model/info", response_model=ModelInfoResponse, tags=["Model"])
async def get_model_info():
    return ModelInfoResponse(**anomaly_service.get_model_info())


@router.get("/frontend", include_in_schema=False)
@router.get("/dashboard",  include_in_schema=False)
async def serve_frontend():
    f = STATIC_DIR / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return JSONResponse(status_code=404, content={"detail": "Frontend not deployed."})
