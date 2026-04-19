"""Training routes."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import DATA_DIR
from app.db import TrainingRepository, get_db
from app.schemas import TrainingRequest, TrainingResponse
from app.services import anomaly_service
from app.api.deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/train", tags=["Training"])


@router.post("", response_model=TrainingResponse)
async def train_model(
    request: TrainingRequest,
    _admin=Depends(require_admin),
):
    """Train / retrain the model. Requires X-Admin-Token header."""
    data_path = request.data_path
    if not data_path:
        data_files = list(DATA_DIR.glob("*.csv"))
        if data_files:
            data_path = str(sorted(data_files)[0])
        else:
            raise HTTPException(
                status_code=400,
                detail="No training data found. Provide data_path or place a CSV in backend/data/.",
            )

    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {data_path}")

    try:
        result = anomaly_service.train(
            data_path  = data_path,
            use_lstm   = request.use_lstm,
            epochs     = request.epochs,
            batch_size = request.batch_size,
            save_model = True,
        )
        with get_db() as db:
            TrainingRepository(db).create(result["training_metadata"])

        return TrainingResponse(
            status            = result["status"],
            message           = result["message"],
            training_metadata = result["training_metadata"],
        )
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")
