from fastapi import APIRouter

from app.api.routes import anomalies, prediction, risk_analytics, system, training

api_router = APIRouter()

api_router.include_router(system.router)
api_router.include_router(training.router)
api_router.include_router(prediction.router)
api_router.include_router(anomalies.router)
api_router.include_router(risk_analytics.router)
