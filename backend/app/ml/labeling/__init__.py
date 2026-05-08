"""HydroGuard-AI — Weak Supervision Labeling Package"""
from app.ml.labeling.engine import LabelEngine, LabelOutput, RULE_WEIGHTS
from app.ml.labeling.rules  import (
    rule_rainfall_intensity, rule_pressure_drop, rule_humidity,
    rule_cloud_concentration, rule_tdew_spread, rule_persistence,
    rule_historical_extreme,
)

__all__ = [
    "LabelEngine", "LabelOutput", "RULE_WEIGHTS",
    "rule_rainfall_intensity", "rule_pressure_drop", "rule_humidity",
    "rule_cloud_concentration", "rule_tdew_spread", "rule_persistence",
    "rule_historical_extreme",
]
