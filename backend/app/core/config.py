"""
HydroGuard-AI — Central Configuration
======================================
Single source of truth for all tunable parameters.
Reads from environment / .env via python-dotenv.

SECURITY: JWT_SECRET_KEY, ADMIN_TOKEN, DATABASE_URL passwords are REQUIRED at
startup. The application will refuse to start with placeholder / default values.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (hydroguard_ai/)
load_dotenv(Path(__file__).parents[3] / ".env")


# ============================================================
#  Paths
# ============================================================

# config.py lives at: hydroguard_ai/backend/app/core/config.py
# parents[0] = .../app/core/
# parents[1] = .../app/
# parents[2] = .../backend/   ← BACKEND_DIR
# parents[3] = .../hydroguard_ai/
BACKEND_DIR:     Path = Path(__file__).parents[2]          # .../backend/
DATA_DIR:        Path = BACKEND_DIR / "data"
MODELS_DIR:      Path = BACKEND_DIR / "saved_models"
CITY_MODELS_DIR: Path = MODELS_DIR / "city_models"
LOGS_DIR:        Path = BACKEND_DIR / "logs"
STATIC_DIR:   Path = BACKEND_DIR.parent / "frontend" / "web_dashboard" / "admin_dashboard"  # served as /static

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
#  Security — ALL values are REQUIRED in production
# ============================================================

# Known insecure placeholder values that must not be deployed
_INSECURE_JWT_PLACEHOLDERS = {
    "CHANGE-ME-generate-with-secrets.token_hex(32)",
    "changeme",
    "secret",
    "your-secret-key",
    "",
}

_INSECURE_ADMIN_PLACEHOLDERS = {
    "changeme-set-in-env",
    "changeme",
    "admin",
    "password",
    "",
}

ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "")

# JWT
JWT_SECRET_KEY:               str = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM:                str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES:  int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS:    int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",   "7"))


def validate_startup_secrets(strict: bool = True) -> list[str]:
    """
    Validate all required secrets are set and are not placeholder values.
    Returns a list of error messages. If strict=True and errors exist, exits.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # JWT_SECRET_KEY — hard requirement
    if not JWT_SECRET_KEY:
        errors.append(
            "JWT_SECRET_KEY is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    elif JWT_SECRET_KEY in _INSECURE_JWT_PLACEHOLDERS:
        errors.append(
            f"JWT_SECRET_KEY is a known placeholder value '{JWT_SECRET_KEY}'. "
            "All JWTs are forgeable. Set a real secret before deploying."
        )
    elif len(JWT_SECRET_KEY) < 32:
        warnings.append(
            f"JWT_SECRET_KEY is only {len(JWT_SECRET_KEY)} chars. "
            "Recommend ≥ 64 chars (32 bytes hex)."
        )

    # ADMIN_TOKEN — warn but don't block startup (legacy clients need it)
    if not ADMIN_TOKEN or ADMIN_TOKEN in _INSECURE_ADMIN_PLACEHOLDERS:
        warnings.append(
            "ADMIN_TOKEN is unset or is a placeholder. "
            "Legacy X-Admin-Token auth is effectively open."
        )

    import logging
    logger = logging.getLogger("hydroguard.config")

    for w in warnings:
        logger.warning("⚠ CONFIG: %s", w)

    if errors:
        for e in errors:
            logger.critical("✗ CONFIG FATAL: %s", e)
        if strict:
            # Security secrets are non-negotiable — exit regardless of DEBUG mode.
            # For local dev, generate a key with:
            #   python -c "import secrets; print(secrets.token_hex(32))"
            # and add JWT_SECRET_KEY=<value> to your .env file.
            sys.exit(
                "\n[HydroGuard-AI] FATAL: Missing or insecure required secrets.\n"
                + "\n".join(f"  • {e}" for e in errors)
                + "\n\nQuick fix for local dev:\n"
                + "  python -c \"import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))\" >> .env\n"
            )

    return errors


# ============================================================
#  TCN buffer warm-up (seeds the rolling window with historical data)
# ============================================================

HYBRID_WARMUP_ENABLED:      bool = os.getenv("HYBRID_WARMUP", "true").lower() in ("true", "1", "yes")
HYBRID_WARMUP_ROWS_PER_CITY: int = int(os.getenv("HYBRID_WARMUP_ROWS", "14"))
HYBRID_WARMUP_CSV: str | None    = os.getenv("HYBRID_WARMUP_CSV")


# ============================================================
#  Weather API — WeatherAPI.com only (no fallback provider)
# ============================================================

WEATHERAPI_KEY:    str = os.getenv("WEATHERAPI_KEY", "")
WEATHER_CACHE_TTL: int = int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "600"))

# Legacy keys kept for config file backward compat — not used in v2
WEATHER_API_KEY:      str = os.getenv("OPENWEATHER_API_KEY", "")
WEATHER_API_PROVIDER: str = os.getenv("WEATHER_API_PROVIDER", "weatherapi")

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL:      str = os.getenv("REDIS_URL",      "redis://localhost:6379/0")
REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")


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
#  Feature weights (module-level so class body can reference them)
# ============================================================
# Raw flood-focus weights; sum = 10.9
_RAW_FEATURE_WEIGHTS: dict[str, float] = {
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
_RAW_WEIGHT_SUM = sum(_RAW_FEATURE_WEIGHTS.values())   # 10.9
# Normalised so they sum to exactly 1.0
_NORMALISED_FEATURE_WEIGHTS: dict[str, float] = {
    k: v / _RAW_WEIGHT_SUM for k, v in _RAW_FEATURE_WEIGHTS.items()
}


# ============================================================
#  Model Hyperparameters
# ============================================================

class ModelConfig:
    """Model configuration — flood-signal-weighted. TCN replaces LSTM (v3.2+)."""

    PRIMARY_FEATURES:   list[str] = ["prcp", "humidity", "pressure", "cloud_cover"]
    SECONDARY_FEATURES: list[str] = ["dew_point", "wspd"]
    CONTEXT_FEATURES:   list[str] = ["tmin", "tmax", "tavg", "temp_range"]
    NUMERICAL_FEATURES: list[str] = PRIMARY_FEATURES + SECONDARY_FEATURES + CONTEXT_FEATURES

    # References the module-level normalised dict (avoids class-scope lookup issue)
    FEATURE_WEIGHTS: dict[str, float] = _NORMALISED_FEATURE_WEIGHTS

    CATEGORICAL_FEATURES: list[str] = ["season", "city", "region"]
    TEMPORAL_FEATURES:    list[str] = ["month", "day", "dayofweek", "is_weekend"]

    ENCODING_DIM:   int   = 12      # Raised from 6 — less aggressive compression
    HIDDEN_LAYERS:  list  = [64, 32, 16]  # Aligned with city_hybrid.py
    DROPOUT_RATE:   float = 0.2

    # TCN sequence length is defined in app/ml/models/tcn.py::TCN_SEQ_LEN (= 30)
    # LSTM is fully removed from v3.2 onward — no LSTM references remain.

    BATCH_SIZE:                int   = int(os.getenv("MODEL_BATCH_SIZE", "64"))
    EPOCHS:                    int   = int(os.getenv("MODEL_EPOCHS",     "100"))
    LEARNING_RATE:             float = 0.001
    VALIDATION_SPLIT:          float = 0.2
    EARLY_STOPPING_PATIENCE:   int   = 15

    THRESHOLD_K: float = float(os.getenv("THRESHOLD_K", "2.5"))

    # Per-month anomaly threshold multiplier (monsoon months get higher tolerance)
    SEASONAL_THRESHOLD_MULTIPLIER: dict[int, float] = {
        1: 1.0,  2: 1.0,  3: 1.0,  4: 1.1,  5: 1.2,
        6: 1.4,  7: 1.5,  8: 1.5,  9: 1.3,  10: 1.1,
        11: 1.0, 12: 1.0,
    }

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
#  Drift Detection
# ============================================================

class DriftConfig:
    """PSI-based feature drift configuration."""
    # Features monitored for drift
    MONITORED_FEATURES: list[str] = ["prcp", "humidity", "pressure", "cloud_cover"]
    PSI_WARN_THRESHOLD:  float = 0.10   # log warning
    PSI_CRIT_THRESHOLD:  float = 0.20   # trigger retraining recommendation
    # Check drift every N predictions (per city)
    CHECK_EVERY_N:       int   = 100
    # Rolling window size for reference distribution
    REFERENCE_WINDOW:    int   = 500


# ============================================================
#  Monte Carlo Dropout Inference
# ============================================================

class MCInferenceConfig:
    """Configuration for parallel MC Dropout inference in predict_v2().

    All values are read from environment variables so they can be
    tuned per-deployment without code changes.
    """
    # Feature flag — set to false to revert to deterministic model.predict()
    ENABLED: bool = os.getenv("ENABLE_MC_INFERENCE", "true").lower() in ("true", "1", "yes")
    # Stochastic forward passes per branch per request
    DROPOUT_SAMPLES: int = int(os.getenv("MC_DROPOUT_SAMPLES", "3"))
    # Wall-clock timeout for asyncio.gather; fallback triggers on exceed
    INFERENCE_TIMEOUT_MS: int = int(os.getenv("MC_INFERENCE_TIMEOUT_MS", "3000"))
    # Uncertainty merge weights (heuristic blend; sum should equal 1.0)
    AE_UNCERTAINTY_WEIGHT: float = float(os.getenv("MC_AE_UNCERTAINTY_WEIGHT", "0.60"))
    TCN_UNCERTAINTY_WEIGHT: float = float(os.getenv("MC_TCN_UNCERTAINTY_WEIGHT", "0.40"))
    # Clip bounds applied after CoV computation
    UNCERTAINTY_MIN: float = float(os.getenv("MC_UNCERTAINTY_MIN", "0.0"))
    UNCERTAINTY_MAX: float = float(os.getenv("MC_UNCERTAINTY_MAX", "1.0"))
    # prediction_stability tier boundaries
    STABILITY_THRESHOLD_MODERATE: float = float(os.getenv("MC_STABILITY_THRESHOLD_MODERATE", "0.25"))
    STABILITY_THRESHOLD_HIGH: float = float(os.getenv("MC_STABILITY_THRESHOLD_HIGH", "0.55"))
    # Semaphore bound on concurrent TF thread-pool workers across all city requests
    MAX_CONCURRENT_THREADS: int = int(os.getenv("MAX_CONCURRENT_MC_THREADS", "4"))
    # Uncertainty strategy name (logged in response; extensible for future strategies)
    UNCERTAINTY_STRATEGY: str = os.getenv("MC_UNCERTAINTY_STRATEGY", "weighted_blend")
    # Bin count for ECE computation in calibration audit
    CALIBRATION_ECE_BINS: int = int(os.getenv("CALIBRATION_ECE_BINS", "15"))


# ============================================================
#  Runtime Health Collector
# ============================================================

class HealthCollectorConfig:
    """Configuration for the three background health-tick tasks.

    All values are env-var driven — no hardcoded thresholds.
    """
    # Background tick cadences (seconds)
    HEALTH_TICK_INTERVAL_S:     int   = int(os.getenv("HEALTH_TICK_INTERVAL_S",    "30"))
    DRIFT_TICK_INTERVAL_S:      int   = int(os.getenv("DRIFT_TICK_INTERVAL_S",     "300"))
    CONFIDENCE_TICK_INTERVAL_S: int   = int(os.getenv("CONFIDENCE_TICK_INTERVAL_S", "3600"))

    # Rolling window sizes (number of requests)
    MC_WINDOW_SIZE:             int   = int(os.getenv("HEALTH_MC_WINDOW_SIZE",     "100"))
    EPISTEMIC_BUFFER_SIZE:      int   = int(os.getenv("HEALTH_EPISTEMIC_BUFFER",   "200"))

    # MC success rate thresholds — fraction of recent requests that completed MC
    # (1.0 = all requests used MC dropout; lower = more timeouts/fallbacks)
    MC_DEGRADED_THRESHOLD:      float = float(os.getenv("HEALTH_MC_DEGRADED",      "0.90"))
    MC_CRITICAL_THRESHOLD:      float = float(os.getenv("HEALTH_MC_CRITICAL",      "0.70"))

    # Preprocessing failure rate thresholds — fraction of calls where feature
    # extraction raised an exception
    PREPROCESS_FAIL_DEGRADED:   float = float(os.getenv("HEALTH_FAIL_DEGRADED",    "0.05"))
    PREPROCESS_FAIL_CRITICAL:   float = float(os.getenv("HEALTH_FAIL_CRITICAL",    "0.20"))

    # Epistemic warmup: minimum successful MC inferences before 2σ/3σ stability
    # bands can be computed. City shows "warming_up" until this count is reached.
    EPISTEMIC_WARMUP_MIN_SAMPLES: int = int(os.getenv("HEALTH_EPISTEMIC_WARMUP",   "50"))


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
        "json": {
            "()": "logging.Formatter",
            "fmt": '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
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
