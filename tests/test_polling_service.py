import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.polling_service import WeatherPollingService


def _make_service(**kwargs) -> WeatherPollingService:
    defaults = dict(
        weather_provider=AsyncMock(),
        city_model_service=MagicMock(),
        interval_seconds=60,
    )
    defaults.update(kwargs)
    return WeatherPollingService(**defaults)


def test_has_significant_change_empty_prev_returns_true():
    svc = _make_service()
    assert svc._has_significant_change({}, {"prcp": 0.0}) is True


def test_has_significant_change_prcp_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change({"prcp": 1.0}, {"prcp": 2.0}) is True


def test_has_significant_change_prcp_below_threshold():
    svc = _make_service()
    assert svc._has_significant_change({"prcp": 1.0}, {"prcp": 1.3}) is False


def test_has_significant_change_pressure_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "pressure": 1013.0},
        {"prcp": 0.0, "pressure": 1015.0},
    ) is True


def test_has_significant_change_pressure_below_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "pressure": 1013.0},
        {"prcp": 0.0, "pressure": 1013.5},
    ) is False


def test_has_significant_change_humidity_above_threshold():
    svc = _make_service()
    assert svc._has_significant_change(
        {"prcp": 0.0, "humidity": 60.0},
        {"prcp": 0.0, "humidity": 66.0},
    ) is True


async def test_poll_city_skips_when_no_change():
    mock_provider = AsyncMock()
    mock_snap = MagicMock()
    mock_snap.to_feature_dict.return_value = {"prcp": 1.0, "pressure": 1013.0, "humidity": 60.0}
    mock_provider.get_current.return_value = mock_snap

    mock_model_svc = AsyncMock()

    svc = WeatherPollingService(mock_provider, mock_model_svc, interval_seconds=60)
    svc._last_snapshots["karachi"] = {"prcp": 1.0, "pressure": 1013.0, "humidity": 60.0}

    with patch("app.runtime.system_runtime.emit_result", new=AsyncMock()) as mock_emit:
        await svc._poll_city("karachi")
        mock_emit.assert_not_called()
        mock_model_svc.predict_v2.assert_not_called()


async def test_poll_city_runs_inference_on_significant_change():
    mock_provider = AsyncMock()
    mock_snap = MagicMock()
    mock_snap.to_feature_dict.return_value = {"prcp": 5.0, "pressure": 1013.0, "humidity": 60.0}
    mock_provider.get_current.return_value = mock_snap

    mock_model_svc = AsyncMock()
    mock_model_svc.predict_v2.return_value = {
        "is_alert": False, "hri_score": 10, "alert_tier_label": "NORMAL",
    }

    svc = WeatherPollingService(mock_provider, mock_model_svc, interval_seconds=60)
    svc._last_snapshots["karachi"] = {"prcp": 0.0, "pressure": 1013.0, "humidity": 60.0}

    with patch("app.runtime.system_runtime.emit_result", new=AsyncMock()):
        await svc._poll_city("karachi")
        mock_model_svc.predict_v2.assert_called_once_with("karachi", mock_snap.to_feature_dict())
