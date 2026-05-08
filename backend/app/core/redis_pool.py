"""
HydroGuard-AI — Shared async Redis client pool.
Initialised once in lifespan; injected everywhere via get_redis().
"""
from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import REDIS_URL, REDIS_PASSWORD

logger = logging.getLogger(__name__)

# Module-level singleton — set by init_redis()
_redis_client: Optional[aioredis.Redis] = None


async def init_redis(url: str | None = None, password: str | None = None) -> None:
    """Initialise the shared Redis client. Call once from lifespan."""
    global _redis_client
    _url      = url      or REDIS_URL
    _password = password or REDIS_PASSWORD or None
    _redis_client = aioredis.from_url(
        _url,
        password=_password,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    try:
        await _redis_client.ping()
        logger.info("Redis connected: %s", _url)
    except Exception as exc:
        logger.warning("Redis ping failed (non-fatal): %s", exc)


def get_redis() -> aioredis.Redis:
    """Return the shared Redis client. Raises RuntimeError if not initialised."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialised. Call init_redis() in lifespan first.")
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool. Call in lifespan shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed.")
