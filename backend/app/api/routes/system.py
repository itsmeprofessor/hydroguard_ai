"""System / health routes."""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import STATIC_DIR
from app.realtime.manager import manager
from app.schemas import HealthResponse, ModelInfoResponse
from app.services import anomaly_service

router = APIRouter(tags=["System"])

APP_VERSION = "3.0.0"
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
            "predict":   "/predict",
            "risk_map":  "/risk-map",
            "analytics": "/analytics",
            "auth":      "/auth/login",
            "ws":        "/ws/anomalies",
        },
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    info = anomaly_service.get_model_info()

    # Model manifest (version info)
    from app.core.config import MODELS_DIR
    import json
    manifest = None
    manifest_path = MODELS_DIR / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    ws_counts = manager.connection_counts()

    return HealthResponse(
        status       = "healthy",
        version      = APP_VERSION,
        model_loaded = anomaly_service.is_trained,
        model_type   = info.get("model_type") if anomaly_service.is_trained else None,
        timestamp    = datetime.utcnow().isoformat() + "Z",
        model_version     = manifest.get("version") if manifest else None,
        ws_connections    = ws_counts,
    )


@router.get("/model/info", response_model=ModelInfoResponse, tags=["Model"])
async def get_model_info():
    return ModelInfoResponse(**anomaly_service.get_model_info())


@router.get("/model/versions", tags=["Model"])
async def get_model_versions():
    from app.core.config import MODELS_DIR
    import json
    manifest_path = MODELS_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"current": None, "archived": []}
    current = json.loads(manifest_path.read_text())
    archive_dir = MODELS_DIR / "archive"
    archived = []
    if archive_dir.exists():
        for v in sorted(archive_dir.iterdir()):
            mp = v / "manifest.json"
            if mp.exists():
                try:
                    archived.append(json.loads(mp.read_text()))
                except Exception:
                    pass
    return {"current": current, "archived": archived}


@router.get("/frontend", include_in_schema=False)
@router.get("/dashboard",  include_in_schema=False)
async def serve_frontend():
    f = STATIC_DIR / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return JSONResponse(status_code=404, content={"detail": "Frontend not deployed."})
