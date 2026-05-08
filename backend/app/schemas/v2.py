"""
HydroGuard-AI -- v2 API Schemas
=================================
Pydantic request/response models for the /api/v2/ endpoint group.

Breaking changes from v1:
  - city, prcp, humidity, pressure are REQUIRED in WeatherInputV2
  - Responses carry event_probability (calibrated float) not anomaly_score
  - New fields: inference_id, confidence_interval, uncertainty, model_entropy,
    risk_band, drivers (SHAP), ood_distance, ood_reason
  - risk_band replaces risk_level: Low | Moderate | High | Severe | Unknown
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ================================================================
#  Request schemas
# ================================================================

class WeatherInputV2(BaseModel):
    """Prediction request -- city + three met variables REQUIRED."""
    city:        str   = Field(..., description="City name or slug (required)")
    prcp:        float = Field(..., ge=0,       description="Precipitation mm (required)")
    humidity:    float = Field(..., ge=0, le=100, description="Relative humidity % (required)")
    pressure:    float = Field(...,              description="Sea-level pressure hPa (required)")
    # Optional enrichment
    tmax:        Optional[float] = Field(None, description="Max temperature C")
    tmin:        Optional[float] = Field(None, description="Min temperature C")
    tavg:        Optional[float] = Field(None, description="Avg temperature C")
    cloud_cover: Optional[float] = Field(None, ge=0, le=100)
    dew_point:   Optional[float] = None
    wspd:        Optional[float] = Field(None, ge=0)
    observed_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "city":        "Islamabad",
                "prcp":        62.0,
                "humidity":    91.0,
                "pressure":    999.5,
                "tmax":        34.1,
                "tmin":        27.8,
                "cloud_cover": 95.0,
            }
        }
    }


class BatchWeatherInputV2(BaseModel):
    """Batch prediction request -- up to 50 observations."""
    data: List[WeatherInputV2] = Field(..., max_length=50)


class TrainingRequestV2(BaseModel):
    """City-specific training trigger."""
    city:       str  = Field(..., description="City name or slug")
    epochs:     int  = Field(150, ge=1, le=500)
    batch_size: int  = Field(64,  ge=8, le=512)
    use_tcn:    bool = True
    force:      bool = Field(False, description="Skip metrics gate (AUC/ECE)")


# ================================================================
#  Prediction response schemas
# ================================================================

class ShapEntry(BaseModel):
    """One SHAP contribution entry."""
    feature: str
    shap:    float
    value:   float


class ComponentScores(BaseModel):
    """Raw branch outputs before fusion and calibration."""
    ae_percentile:  float
    tcn_percentile: float
    p_event_raw:    float
    ae_variance:    float
    tcn_variance:   float


class PredictionResponseV2(BaseModel):
    """
    Full v2 prediction response.

    event_probability: calibrated P(hydro-meteorological event) in [0, 1].
    risk_band: operational tier (Low / Moderate / High / Severe / Unknown).
    drivers: top SHAP contributors from the LightGBM fusion model.
    model_entropy: H(p) = -p*log(p) - (1-p)*log(1-p); high = uncertain classifier.
    """
    inference_id:        str
    city:                str
    city_slug:           str
    inferred_at:         datetime
    model_version:       str
    calibration_version: str
    source:              str   # "city_model" | "heuristic" | "ood_guard"

    # Core probabilistic output
    event_probability:   Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_interval: Optional[List[float]] = None   # [lower, upper]
    uncertainty:         Optional[float]        = None
    model_entropy:       Optional[float]        = None  # Addition A

    # Risk classification
    risk_band: str    # "Low" | "Moderate" | "High" | "Severe" | "Unknown"
    is_alert:  bool

    # Detailed breakdown (omitted for heuristic/OOD sources)
    component_scores: Optional[ComponentScores] = None
    drivers:          Optional[List[ShapEntry]] = None

    # Input echo
    weather_inputs:      Dict[str, Any]           = Field(default_factory=dict)
    climatology_context: Optional[Dict[str, Any]] = None

    # OOD guard fields (populated only when source="ood_guard")
    ood_distance: Optional[float] = None
    ood_reason:   Optional[str]   = None

    model_config = {"extra": "allow"}


# ================================================================
#  Training response schemas
# ================================================================

class TrainingRunResponseV2(BaseModel):
    id:                  str
    city_slug:           str
    status:              str   # "queued" | "running" | "success" | "failed"
    triggered_by:        str
    model_version:       Optional[str]   = None
    lgbm_val_auc:        Optional[float] = None
    lgbm_val_brier:      Optional[float] = None
    calibration_ece:     Optional[float] = None
    calibration_brier:   Optional[float] = None
    ae_val_loss:         Optional[float] = None
    tcn_val_loss:        Optional[float] = None
    positive_label_rate: Optional[float] = None
    started_at:          Optional[datetime] = None
    finished_at:         Optional[datetime] = None
    duration_seconds:    Optional[float] = None
    error_message:       Optional[str]   = None


class TrainingAllStatusV2(BaseModel):
    cities:    List[TrainingRunResponseV2]
    total:     int
    trained:   int
    untrained: int


# ================================================================
#  Drift response schemas
# ================================================================

class DriftStateResponseV2(BaseModel):
    city_slug:         str
    checked_at:        datetime
    drift_level:       str   # "ok" | "warn" | "critical"
    max_psi:           float
    psi_scores:        Dict[str, float]
    retrain_triggered: bool
    window_size:       int
    reference_rows:    int


class AllDriftStatesV2(BaseModel):
    cities:     Dict[str, DriftStateResponseV2]
    total:      int
    warn_count: int
    crit_count: int


# ================================================================
#  Label response schemas
# ================================================================

class LabelEventResponseV2(BaseModel):
    id:              str
    city_slug:       str
    observed_at:     datetime
    weak_label:      int    # -1 | 0 | 1
    weak_label_conf: float
    event_type:      Optional[str] = None
    rule_votes:      Dict[str, int]    # {"L1": 1, "L2": -1, ...}  Addition B
    is_verified:     bool
    verified_by:     Optional[str]      = None
    verified_at:     Optional[datetime] = None

    model_config = {"extra": "allow"}


class LabelStatisticsV2(BaseModel):
    city_slug:         str
    total_labels:      int
    positive_count:    int
    negative_count:    int
    abstain_count:     int
    positive_rate:     float
    by_rule_fire_rate: Dict[str, float]


# ================================================================
#  City / health schemas
# ================================================================

class CityStatusV2(BaseModel):
    slug:            str
    name:            str
    province:        str
    population:      str
    lat:             Optional[float]    = None
    lon:             Optional[float]    = None
    has_data:        bool
    has_model:       bool
    model_version:   Optional[str]      = None
    calibration_ece: Optional[float]    = None
    last_trained_at: Optional[datetime] = None
    vulnerability:   Optional[float]    = None


class CitiesListV2(BaseModel):
    cities:   List[CityStatusV2]
    total:    int
    trained:  int
    untrained: int


class HealthResponseV2(BaseModel):
    status:           str   # "healthy" | "degraded"
    version:          str
    timestamp:        datetime
    city_models:      Dict[str, Any]
    weather_provider: Dict[str, Any]
    redis:            Dict[str, Any]
    drift:            Dict[str, Any]
    ws_connections:   Dict[str, int]

    model_config = {"extra": "allow"}
