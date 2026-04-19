"""
HydroGuard-AI — Central Configuration
======================================
Single source of truth for all tunable parameters.
Reads from environment / .env via python-dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (hydroguard_ai/)
load_dotenv(Path(__file__).parents[2] / ".env")


# ============================================================
#  Paths
# ============================================================

BACKEND_DIR:  Path = Path(__file__).parents[1]          # .../backend/
DATA_DIR:     Path = BACKEND_DIR / "data"
MODELS_DIR:   Path = BACKEND_DIR / "saved_models"
LOGS_DIR:     Path = BACKEND_DIR / "logs"
STATIC_DIR:   Path = BACKEND_DIR.parent / "frontend"    # served as /static

for _d in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ============================================================
#  Database
# ============================================================

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BACKEND_DIR / 'weather_anomalies.db'}",
)


# ============================================================
#  Security
# ============================================================

ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "changeme-set-in-env")


# ============================================================
#  Hybrid LSTM warm-up
# ============================================================

HYBRID_WARMUP_ENABLED:      bool = os.getenv("HYBRID_WARMUP", "true").lower() in ("true", "1", "yes")
HYBRID_WARMUP_ROWS_PER_CITY: int = int(os.getenv("HYBRID_WARMUP_ROWS", "14"))
HYBRID_WARMUP_CSV: str | None    = os.getenv("HYBRID_WARMUP_CSV")


# ============================================================
#  API
# ============================================================

class APIConfig:
    HOST:  str  = os.getenv("API_HOST", "127.0.0.1")
    PORT:  int  = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    CORS_ORIGINS:          list[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    MAX_ANOMALIES_PER_PAGE: int       = 100


# ============================================================
#  Model Hyperparameters
# ============================================================

class ModelConfig:
    """Autoencoder + LSTM configuration — flood-signal-weighted."""

    PRIMARY_FEATURES:   list[str] = ["prcp", "humidity", "pressure", "cloud_cover"]
    SECONDARY_FEATURES: list[str] = ["dew_point", "wspd"]
    CONTEXT_FEATURES:   list[str] = ["tmin", "tmax", "tavg", "temp_range"]
    NUMERICAL_FEATURES: list[str] = PRIMARY_FEATURES + SECONDARY_FEATURES + CONTEXT_FEATURES

    # Flood-focus weights applied before standard-scaling
    FEATURE_WEIGHTS: dict[str, float] = {
        "prcp":        3.0,
        "humidity":    2.0,
        "pressure":    2.0,
        "cloud_cover": 1.5,
        "dew_point":   1.0,
        "wspd":        1.0,
        "tmin":        0.1,
        "tmax":        0.1,
        "tavg":        0.1,
        "temp_range":  0.1,
    }

    CATEGORICAL_FEATURES: list[str] = ["season", "city", "region"]
    TEMPORAL_FEATURES:    list[str] = ["month", "day", "dayofweek", "is_weekend"]

    ENCODING_DIM:   int   = 6
    HIDDEN_LAYERS:  list  = [32, 16, 8]
    DROPOUT_RATE:   float = 0.2

    LSTM_UNITS:      int = 32
    SEQUENCE_LENGTH: int = 7

    BATCH_SIZE:                int   = int(os.getenv("MODEL_BATCH_SIZE", "64"))
    EPOCHS:                    int   = int(os.getenv("MODEL_EPOCHS",     "100"))
    LEARNING_RATE:             float = 0.001
    VALIDATION_SPLIT:          float = 0.2
    EARLY_STOPPING_PATIENCE:   int   = 15

    THRESHOLD_K: float = float(os.getenv("THRESHOLD_K", "2.5"))

    RISK_THRESHOLDS: dict[str, float] = {
        "LOW":      0.50,
        "MEDIUM":   0.70,
        "HIGH":     0.85,
        "CRITICAL": 0.95,
    }

    # HRI composite weights (must sum to 1.0)
    HRI_WEIGHTS: dict[str, float] = {
        "anomaly_score":          0.40,
        "rainfall_intensity":     0.35,
        "regional_vulnerability": 0.25,
    }

    # Per-city flood vulnerability scores (0–1)
    REGIONAL_VULNERABILITY: dict[str, float] = {
        "Islamabad":  0.80,
        "Rawalpindi": 0.85,
        "Peshawar":   0.80,
        "Lahore":     0.75,
        "Karachi":    0.70,
        "Gilgit":     0.90,
        "Quetta":     0.65,
        "Faisalabad": 0.65,
        "Multan":     0.60,
        "Hyderabad":  0.70,
        "DEFAULT":    0.60,
    }


# ============================================================
#  Cloudburst Rule Engine
# ============================================================

class CloudburstConfig:
    """Thresholds and weights for the physics-based rule engine."""

    # Precipitation (mm)
    LIGHT_RAIN:      int = 10
    MODERATE_RAIN:   int = 30
    HEAVY_RAIN:      int = 50
    VERY_HEAVY_RAIN: int = 75
    CLOUDBURST:      int = 100

    # Pressure (hPa)
    NORMAL_PRESSURE:   int = 1013
    LOW_PRESSURE:      int = 1005
    VERY_LOW_PRESSURE: int = 995

    # Humidity (%)
    HIGH_HUMIDITY:      int = 80
    VERY_HIGH_HUMIDITY: int = 90
    CRITICAL_HUMIDITY:  int = 95

    # Cloud cover (%)
    OVERCAST:      int = 80
    FULL_OVERCAST: int = 95

    # Wind speed (km/h)
    STRONG_WIND: int = 30
    STORM_WIND:  int = 50

    WEIGHTS: dict[str, float] = {
        "precipitation": 0.45,
        "pressure":      0.25,
        "humidity":      0.20,
        "cloud_cover":   0.10,
    }

    RISK_CATEGORIES: dict[str, tuple] = {
        "LOW":      (0.00, 0.30),
        "MODERATE": (0.30, 0.50),
        "HIGH":     (0.50, 0.70),
        "CRITICAL": (0.70, 1.00),
    }

    MONSOON_MONTHS:           list[int] = [6, 7, 8, 9]
    MONSOON_SENSITIVITY_BOOST: float    = 1.2

    FLASH_FLOOD_PRONE_CITIES: list[str] = [
        "Islamabad", "Rawalpindi", "Peshawar", "Lahore", "Karachi",
    ]

    ALERT_CONDITIONS: dict[str, float] = {
        "precipitation_threshold": 50.0,
        "humidity_threshold":      85.0,
        "pressure_threshold":      1000.0,
        "cloud_cover_threshold":   80.0,
    }


# ============================================================
#  Logging
# ============================================================

LOGGING_CONFIG: dict = {
    "version":                  1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format":  "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "level":     "INFO",
            "formatter": "standard",
            "stream":    "ext://sys.stdout",
        },
        "file": {
            "class":       "logging.handlers.RotatingFileHandler",
            "level":       "DEBUG",
            "formatter":   "standard",
            "filename":    str(LOGS_DIR / "hydroguard.log"),
            "maxBytes":    10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "encoding":    "utf-8",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level":    "INFO",
    },
    "loggers": {
        "uvicorn.error":     {"level": "INFO"},
        "uvicorn.access":    {"level": "WARNING"},
        "sqlalchemy.engine": {"level": "WARNING"},
    },
}