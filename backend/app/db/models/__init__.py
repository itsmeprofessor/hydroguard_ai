"""
HydroGuard-AI -- ORM Models Package
All SQLAlchemy models. Import from here for convenience.
"""
from app.db.models.user               import User
from app.db.models.feature_snapshot   import FeatureSnapshot
from app.db.models.weather_snapshot   import WeatherSnapshot
from app.db.models.prediction_event   import PredictionEvent
from app.db.models.label_event        import LabelEvent
from app.db.models.training_run       import TrainingRun
from app.db.models.model_registry     import ModelRegistryEntry
from app.db.models.drift_state        import DriftStateRecord
from app.db.models.calibration_state  import CalibrationStateRecord

__all__ = [
    "User",
    "FeatureSnapshot", "WeatherSnapshot",
    "PredictionEvent", "LabelEvent",
    "TrainingRun", "ModelRegistryEntry",
    "DriftStateRecord", "CalibrationStateRecord",
]
