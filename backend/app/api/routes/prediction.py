"""Prediction routes — single and batch."""

import logging

from fastapi import APIRouter, HTTPException

from app.db import AnomalyRepository, get_db
from app.schemas import (
    BatchPredictionResponse,
    BatchWeatherInput,
    PredictionResponse,
    WeatherDataInput,
)
from app.services import anomaly_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["Prediction"])


def _model_guard():
    if not anomaly_service.is_trained:
        raise HTTPException(status_code=400, detail="Model not trained. POST /train first.")


@router.post("", response_model=PredictionResponse)
async def predict_anomaly(weather_data: WeatherDataInput):
    """Detect anomaly in a single weather observation."""
    _model_guard()
    try:
        result = anomaly_service.predict(weather_data.model_dump())
        if result["is_anomaly"]:
            with get_db() as db:
                AnomalyRepository(db).create(result, weather_data.model_dump())
        return PredictionResponse(**result)
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


@router.post("/batch", response_model=BatchPredictionResponse)
async def predict_batch(batch_data: BatchWeatherInput):
    """Detect anomalies in multiple observations. Uses a single DB session for efficiency."""
    _model_guard()
    try:
        predictions: list      = []
        anomalies_to_save: list = []

        for wd in batch_data.data:
            result = anomaly_service.predict(wd.model_dump())
            predictions.append(result)
            if result["is_anomaly"]:
                anomalies_to_save.append((result, wd.model_dump()))

        if anomalies_to_save:
            with get_db() as db:
                repo = AnomalyRepository(db)
                for res, raw in anomalies_to_save:
                    repo.create(res, raw)

        return BatchPredictionResponse(
            total           = len(predictions),
            anomalies_found = len(anomalies_to_save),
            predictions     = [PredictionResponse(**p) for p in predictions],
        )
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {e}")
