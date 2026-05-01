"""Prediction routes — single and batch."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

_limiter = Limiter(key_func=get_remote_address)

from app.api.deps import get_current_user
from app.db import AnomalyRepository, get_db
from app.schemas import (
    BatchPredictionResponse,
    BatchWeatherInput,
    PredictionResponse,
    WeatherDataInput,
)
from app.services import anomaly_service
from app.services.broadcast_service import emit_anomaly

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["Prediction"])


def _model_guard():
    if not anomaly_service.is_trained:
        raise HTTPException(status_code=400, detail="Model not trained. POST /train first.")


@router.post("", response_model=PredictionResponse)
@_limiter.limit("60/minute")
async def predict_anomaly(
    request:      Request,
    weather_data: WeatherDataInput,
    _user:        dict = Depends(get_current_user),
):
    _model_guard()
    try:
        result = anomaly_service.predict(weather_data.model_dump())
        with get_db() as db:
            AnomalyRepository(db).create(result, weather_data.model_dump())
        await emit_anomaly(result)
        return PredictionResponse(**result)
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


@router.post("/batch", response_model=BatchPredictionResponse)
@_limiter.limit("20/minute")
async def predict_batch(
    request:    Request,
    batch_data: BatchWeatherInput,
    _user:      dict = Depends(get_current_user),
):
    _model_guard()
    try:
        predictions:       list = []
        records_to_save:   list = []

        for wd in batch_data.data:
            result = anomaly_service.predict(wd.model_dump())
            predictions.append(result)
            records_to_save.append((result, wd.model_dump()))
            await emit_anomaly(result)

        anomalies_found = sum(1 for r in predictions if r["is_anomaly"])

        with get_db() as db:
            repo = AnomalyRepository(db)
            for res, raw in records_to_save:
                repo.create(res, raw)

        return BatchPredictionResponse(
            total           = len(predictions),
            anomalies_found = anomalies_found,
            predictions     = [PredictionResponse(**p) for p in predictions],
        )
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {e}")
