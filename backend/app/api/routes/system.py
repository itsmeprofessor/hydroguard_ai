"""System / health routes."""

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import STATIC_DIR
from app.realtime.manager import manager
from app.schemas import HealthResponse, ModelInfoResponse

router = APIRouter(tags=["System"])

APP_VERSION = "3.2.0"
APP_TITLE   = "HydroGuard-AI — Adaptive Flood Intelligence API"


@router.get("/")
async def root():
    return {
        "name":    APP_TITLE,
        "version": APP_VERSION,
        "status":  "running",
        "endpoints": {
            "docs":         "/docs",
            "health":       "/health",
            "predict":      "/predict",
            "risk_map":     "/risk-map",
            "analytics":    "/analytics",
            "cities":       "/cities",
            "weather":      "/weather",
            "auth":         "/auth/login",
            "ws_anomalies": "/ws/anomalies",
            "ws_health":    "/ws/health",
            "registry":     "/model/registry",
        },
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    import json
    from app.core.config import MODELS_DIR
    manifest = None
    manifest_path = MODELS_DIR / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    ws_counts = manager.connection_counts()

    # Drift state summary (from DB via v2 DriftRepo)
    drift_summary: dict = {}
    try:
        from app.db.database import get_db
        from app.db.repositories.drift_repo import DriftRepo
        with get_db() as db:
            records = DriftRepo(db).get_all_latest()
        drift_summary = {
            "monitored_cities": len(records),
            "critical_cities":  [r.city_slug for r in records if r.drift_level == "critical"],
            "warn_cities":      [r.city_slug for r in records if r.drift_level == "warn"],
        }
    except Exception:
        pass

    # Model registry summary
    registry_summary: dict = {}
    try:
        from app.services.model_registry import model_registry
        registry_summary = model_registry.summary()
    except Exception:
        pass

    # City model status
    city_status: dict = {}
    try:
        from app.services.city_model_service import city_model_service
        city_status = city_model_service.model_status()
    except Exception:
        pass

    # Derive model_loaded from city model registry
    try:
        from app.services.city_model_service import city_model_service as _cms
        _city_status = city_model_service.model_status() if 'city_model_service' in dir() else _cms.model_status()
        _model_loaded = _city_status.get("trained_cities", 0) > 0
    except Exception:
        _model_loaded = False
    model_loaded = _model_loaded
    model_type = "city_hybrid_v2"

    return HealthResponse(
        status        = "healthy",
        version       = APP_VERSION,
        model_loaded  = model_loaded,
        model_type    = model_type,
        timestamp     = datetime.now(timezone.utc).isoformat(),
        model_version = manifest.get("version") if manifest else None,
        ws_connections = ws_counts,
        # Extended fields — attached as extra in response
        drift         = drift_summary,
        registry      = registry_summary,
        city_models   = city_status,
    )


@router.get("/model/info", response_model=ModelInfoResponse, tags=["Model"])
async def get_model_info():
    try:
        from app.services.city_model_service import city_model_service
        status = city_model_service.model_status()
        return ModelInfoResponse(
            status     = "active",
            model_type = "city_hybrid_v2",
            is_trained = status.get("trained_cities", 0) > 0,
        )
    except Exception as exc:
        return ModelInfoResponse(status="error", model_type=None, is_trained=False)


@router.get("/model/versions", tags=["Model"])
async def get_model_versions():
    import json
    from app.core.config import MODELS_DIR
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


@router.get("/model/registry", tags=["Model"])
async def get_registry():
    """Full model registry — all cities, all versions."""
    try:
        from app.services.model_registry import model_registry
        return model_registry.all_entries()
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/model/registry/{city_slug}", tags=["Model"])
async def get_registry_city(city_slug: str):
    """Registry history for a specific city."""
    try:
        from app.services.model_registry import model_registry
        history = model_registry.get_history(city_slug)
        if not history:
            return JSONResponse(status_code=404, content={"detail": f"No registry for '{city_slug}'"})
        return {"city_slug": city_slug, "history": history}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/drift", tags=["Monitoring"])
async def get_drift_state():
    """Drift state -- use /api/v2/drift for full data."""
    return {
        "message":  "Use /api/v2/drift for drift state data",
        "redirect": "/api/v2/drift",
    }


@router.get("/drift/{city_slug}", tags=["Monitoring"])
async def get_drift_city(city_slug: str):
    """Drift state for a city -- use /api/v2/drift/{city} for full data."""
    return {
        "message":  f"Use /api/v2/drift/{city_slug} for drift data",
        "redirect": f"/api/v2/drift/{city_slug}",
    }


@router.get("/frontend", include_in_schema=False)
@router.get("/dashboard",  include_in_schema=False)
async def serve_frontend():
    f = STATIC_DIR / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return JSONResponse(status_code=404, content={"detail": "Frontend not deployed."})
