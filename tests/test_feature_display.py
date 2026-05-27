"""Test feature display name mapping layer."""
from app.config.feature_display import display_name, FEATURE_DISPLAY_MAP


def test_known_feature_returns_display_label():
    assert display_name("pressure_delta_3h") == "pressure_delta_1step (daily resolution)"


def test_unknown_feature_passthrough():
    assert display_name("ae_percentile") == "ae_percentile"


def test_all_mapped_features_differ_from_internal_name():
    for internal, label in FEATURE_DISPLAY_MAP.items():
        assert internal != label
