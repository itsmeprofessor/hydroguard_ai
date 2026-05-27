import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.realtime.broadcaster import (
    AbstractBroadcaster,
    LocalBroadcaster,
    RedisBroadcaster,
)


def test_abstract_broadcaster_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractBroadcaster()


async def test_local_broadcaster_delegates_to_manager():
    mock_manager = AsyncMock()
    broadcaster = LocalBroadcaster(mock_manager)
    await broadcaster.broadcast("anomalies", {"city": "karachi"})
    mock_manager.broadcast.assert_called_once_with("anomalies", {"city": "karachi"})


async def test_local_broadcaster_close_is_noop():
    mock_manager = AsyncMock()
    broadcaster = LocalBroadcaster(mock_manager)
    await broadcaster.close()  # must not raise


def test_local_broadcaster_is_abstract_broadcaster():
    assert isinstance(LocalBroadcaster(AsyncMock()), AbstractBroadcaster)


async def test_redis_broadcaster_publishes_to_correct_key():
    mock_redis = AsyncMock()
    broadcaster = RedisBroadcaster(mock_redis)
    await broadcaster.broadcast("anomalies", {"city": "lahore"})
    mock_redis.publish.assert_called_once_with(
        "hg:ws:anomalies",
        json.dumps({"city": "lahore"}),
    )


async def test_redis_broadcaster_close_cancels_tasks():
    mock_redis = AsyncMock()
    broadcaster = RedisBroadcaster(mock_redis)
    # No tasks started — close should be safe with empty list
    await broadcaster.close()
