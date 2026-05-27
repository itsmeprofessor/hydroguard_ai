import os
import pytest
from unittest.mock import AsyncMock

import app.runtime.system_runtime as runtime


@pytest.fixture(autouse=True)
def reset_broadcaster():
    original = runtime.ACTIVE_BROADCASTER
    yield
    runtime.ACTIVE_BROADCASTER = original


async def test_emit_result_calls_broadcaster_for_is_alert():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": True, "hri_score": 75})
    mock.broadcast.assert_called_once_with("anomalies", {"is_alert": True, "hri_score": 75})


async def test_emit_result_calls_broadcaster_for_high_hri():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": False, "hri_score": 45})
    mock.broadcast.assert_called_once()


async def test_emit_result_skips_normal_low_hri():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_result({"is_alert": False, "hri_score": 10})
    mock.broadcast.assert_not_called()


async def test_emit_result_noop_when_no_broadcaster():
    runtime.ACTIVE_BROADCASTER = None
    # Must not raise
    await runtime.emit_result({"is_alert": True, "hri_score": 90})


async def test_emit_health_routes_to_health_channel():
    mock = AsyncMock()
    runtime.ACTIVE_BROADCASTER = mock
    await runtime.emit_health({"status": "ok", "latency_ms": 12})
    mock.broadcast.assert_called_once_with("health", {"status": "ok", "latency_ms": 12})


async def test_emit_health_noop_when_no_broadcaster():
    runtime.ACTIVE_BROADCASTER = None
    await runtime.emit_health({"status": "ok"})


def test_feature_flags_has_polling_enabled():
    assert "polling_enabled" in runtime.FEATURE_FLAGS


def test_feature_flags_has_polling_sensitivity():
    s = runtime.FEATURE_FLAGS["polling_sensitivity"]
    assert "prcp_delta" in s
    assert "pressure_delta" in s
    assert "humidity_delta" in s
