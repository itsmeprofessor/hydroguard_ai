"""Feature display name mapping layer.

Internal ML feature names and model artifacts are NEVER renamed.
This mapping is applied only to the `drivers` field in predict_v2 output.
"""
from __future__ import annotations

FEATURE_DISPLAY_MAP: dict[str, str] = {
    "pressure_delta_3h":    "pressure_delta_1step (daily resolution)",
    "pressure_delta_6h":    "pressure_delta_2step (daily resolution)",
    "rain_rate_1h":         "rain_rate_1step (daily resolution)",
    "rain_accumulation_3h": "rain_accumulation_3step (daily resolution)",
    "cloud_jump_3h":        "cloud_jump_3step (daily resolution)",
}


def display_name(feature: str) -> str:
    """Map internal ML feature name to human-readable label for API output only.

    Internal FUSION_FEATURES names and model artifacts are NEVER renamed.
    This mapping is applied only to the `drivers` field in predict_v2 output.

    Args:
        feature: Internal ML feature name

    Returns:
        Human-readable display label, or the original feature name if not mapped.
    """
    return FEATURE_DISPLAY_MAP.get(feature, feature)
