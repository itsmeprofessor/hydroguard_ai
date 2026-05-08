"""
HydroGuard-AI — Pydantic Request/Response Schemas
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
#  Enums
# ============================================================

class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class HRILabel(str, Enum):
    LOW      = "Low"
    GUARDED  = "Guarded"
    ELEVATED = "Elevated"
    SEVERE   = "Severe"


# ============================================================
#  Request Schemas
# ============================================================

class WeatherDataInput(BaseModel):
    date:        Optional[str]   = Field(None, description="Date YYYY-MM-DD")
    year:        Optional[int]   = Field(None, ge=1900, le=2100)
    month:       Optional[int]   = Field(None, ge=1,    le=12)
    day:         Optional[int]   = Field(None, ge=1,    le=31)
    dayofweek:   Optional[int]   = Field(None, ge=0,    le=6)
    is_weekend:  Optional[int]   = Field(None, ge=0,    le=1)
    season:      Optional[str]   = None
    city:        str             = Field(..., description="City name")
    region:      Optional[str]   = None
    latitude:    Optional[float] = Field(None, ge=-90,  le=90)
    longitude:   Optional[float] = Field(None, ge=-180, le=180)
    elevation:   Optional[float] = None
    tmin:        Optional[float] = Field(None, description="Min temperature (°C)")
    tmax:        Optional[float] = Field(None, description="Max temperature (°C)")
    tavg:        Optional[float] = Field(None, description="Avg temperature (°C)")
    prcp:        Optional[float] = Field(None, ge=0, description="Precipitation (mm)")
    wspd:        Optional[float] = Field(None, ge=0, description="Wind speed (km/h)")
    humidity:    Optional[float] = Field(None, ge=0, le=100, description="Humidity (%)")
    pressure:    Optional[float] = Field(None, description="Pressure (hPa)")
    dew_point:   Optional[float] = Field(None, description="Dew point (°C)")
    cloud_cover: Optional[float] = Field(None, ge=0, le=100, description="Cloud cover (%)")
    temp_range:  Optional[float] = Field(None, description="Temperature range (°C)")
    rainfall_intensity: Optional[str] = None
    wind_category:      Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2024-07-15",
                "city": "Islamabad",
                "region": "Punjab",
                "tmin": 25.5, "tmax": 38.2, "tavg": 31.8,
                "prcp": 45.0, "wspd": 15.5,
                "humidity": 85, "pressure": 1002.5,
                "dew_point": 24.3, "cloud_cover": 90,
                "month": 7, "day": 15, "season": "Monsoon",
            }
        }
    }


class BatchWeatherInput(BaseModel):
    data: List[WeatherDataInput] = Field(..., description="List of weather observations")


class TrainingRequest(BaseModel):
    data_path:  Optional[str] = Field(None, description="Path to training CSV")
    use_lstm:   bool          = Field(True)
    epochs:     Optional[int] = Field(None, ge=1, le=1000)
    batch_size: Optional[int] = Field(None, ge=1, le=512)


# ============================================================
#  Response Schemas
# ============================================================

class CloudburstRisk(BaseModel):
    risk_score:          Optional[float] = None
    risk_category:       Optional[str]   = None
    is_cloudburst_likely: Optional[bool] = None


class PredictionResponse(BaseModel):
    city:             str
    date:             Optional[str]
    anomaly_score:    float
    consensus_score:  Optional[float] = None
    threshold:        float
    is_anomaly:       bool
    risk_level:       str
    hri_score:        Optional[int]   = None
    hri_label:        Optional[str]   = None
    hri_components:   Optional[Dict[str, float]] = None
    cloudburst_risk:  Optional[Dict[str, Any]]   = None
    remarks:               Optional[str]  = None
    feature_contributions: Optional[Dict] = None
    detailed_explanation:  Optional[Dict] = None


class BatchPredictionResponse(BaseModel):
    total:           int
    anomalies_found: int
    predictions:     List[PredictionResponse]


class TrainingResponse(BaseModel):
    status:            str
    message:           str
    training_metadata: Optional[Dict[str, Any]] = None


class AnomalyRecordResponse(BaseModel):
    id:            int
    city:          str
    region:        Optional[str]
    date:          str
    weather_data:  Dict[str, Any]
    anomaly_score: float
    threshold:     float
    is_anomaly:    bool
    risk_level:    str
    hri_score:     Optional[int]
    hri_label:     Optional[str]
    cloudburst_risk: Optional[Dict[str, Any]]
    remarks:               Optional[str]
    feature_contributions: Optional[Dict]
    created_at:    str


class AnomalyListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    anomalies: List[AnomalyRecordResponse]


class HealthResponse(BaseModel):
    status:         str
    version:        str
    model_loaded:   bool
    model_type:     Optional[str]
    timestamp:      str
    model_version:  Optional[int]  = None
    ws_connections: Optional[Dict] = None
    # Extended fields (v3.1) — populated by system.py health_check()
    drift:          Optional[Dict] = None
    registry:       Optional[Dict] = None
    city_models:    Optional[Dict] = None

    model_config = {"extra": "allow"}


class ModelInfoResponse(BaseModel):
    status:           str
    model_type:       Optional[str] = None
    is_trained:       Optional[bool] = None
    input_dim:        Optional[int] = None
    threshold:        Optional[float] = None
    features:         Optional[List[str]] = None
    training_metadata: Optional[Dict] = None


class StatisticsResponse(BaseModel):
    total_records:    Optional[int]   = None
    anomaly_count:    Optional[int]   = None
    anomaly_rate:     Optional[float] = None
    by_city:          Optional[Dict]  = None
    by_risk_level:    Optional[Dict]  = None
    by_month:         Optional[Dict]  = None
    cloudburst_count: Optional[int]   = None
    date_range:       Optional[Dict]  = None


class RiskMapEntry(BaseModel):
    city:       str
    region:     str
    latitude:   float
    longitude:  float
    hri_score:  Optional[int]
    risk_level: str
    hri_label:  Optional[str]


class RiskMapResponse(BaseModel):
    entries: List[RiskMapEntry]
    count:   int


class AnalyticsResponse(BaseModel):
    total_anomalies_this_week: int
    alerts_by_risk_level:      Dict[str, int]
    top_cities_by_frequency:   List[Dict[str, Any]]
    total_cloudburst_alerts:   int
    total_records_in_db:       int


class ErrorResponse(BaseModel):
    error:       str
    status_code: int
    detail:      Optional[str] = None
