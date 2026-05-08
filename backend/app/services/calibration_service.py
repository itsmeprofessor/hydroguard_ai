"""
HydroGuard-AI -- Calibration Service
======================================
Manages IsotonicCalibrator lifecycle per city.
Checks ECE on recent predictions and triggers recalibration if needed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ECE_RECALIBRATE_THRESHOLD = 0.10
MIN_SAMPLES_FOR_CHECK     = 100


class CalibrationService:
    """
    Manages IsotonicCalibrator lifecycle per city.
    Checks ECE degradation on recent predictions and triggers recalibration.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self._models_dir = models_dir or Path("backend/saved_models/city_models")

    def get_calibrator(self, city_slug: str):
        """Return the active IsotonicCalibrator for a city, or None."""
        try:
            from app.services.city_model_service import city_model_service
            return city_model_service._calibrators.get(city_slug)
        except Exception:
            return None

    async def check_and_recalibrate_if_needed(
        self,
        city_slug:     str,
        recent_events: list,
    ) -> bool:
        """
        Check calibration quality on recent predictions.
        Triggers recalibration if ECE > ECE_RECALIBRATE_THRESHOLD.

        Returns True if recalibration was triggered.
        """
        if len(recent_events) < MIN_SAMPLES_FOR_CHECK:
            return False

        calibrator = self.get_calibrator(city_slug)
        if calibrator is None:
            return False

        try:
            import numpy as np
            from app.ml.calibration.isotonic import IsotonicCalibrator

            p_vals = np.array([e.p_event  for e in recent_events if e.p_event is not None])
            y_vals = np.array([float(e.is_alert) for e in recent_events if e.p_event is not None])

            if len(p_vals) < MIN_SAMPLES_FOR_CHECK:
                return False

            ece = IsotonicCalibrator.ece(p_vals, y_vals)
            logger.info(
                "[%s] Calibration ECE=%.4f (threshold=%.2f)",
                city_slug, ece, ECE_RECALIBRATE_THRESHOLD,
            )

            if ece <= ECE_RECALIBRATE_THRESHOLD:
                return False

            logger.warning(
                "[%s] ECE=%.4f > threshold -- triggering recalibration", city_slug, ece
            )
            await self._recalibrate(city_slug, p_vals, y_vals)
            return True

        except Exception as exc:
            logger.debug("[%s] Calibration check failed: %s", city_slug, exc)
            return False

    async def _recalibrate(
        self,
        city_slug: str,
        p_raw:    "np.ndarray",
        y_true:   "np.ndarray",
    ) -> None:
        """Refit IsotonicCalibrator and hot-swap in CityModelService."""
        import asyncio
        try:
            from app.ml.calibration.isotonic import IsotonicCalibrator
            from app.services.city_model_service import city_model_service

            cal = IsotonicCalibrator()
            await asyncio.to_thread(cal.fit, p_raw, y_true)

            cal_path = self._models_dir / city_slug / "calibrator.pkl"
            cal_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(cal.save, cal_path)

            city_model_service._calibrators[city_slug] = cal
            logger.info("[%s] Recalibration complete -> %s", city_slug, cal_path)

        except Exception as exc:
            logger.error("[%s] Recalibration failed: %s", city_slug, exc)


# Singleton
calibration_service: Optional[CalibrationService] = None


def init_calibration_service(
    models_dir: Optional[Path] = None,
) -> CalibrationService:
    """Initialise and return the global CalibrationService singleton."""
    global calibration_service
    calibration_service = CalibrationService(models_dir)
    logger.info("CalibrationService initialised")
    return calibration_service
