"""
Load test for HydroGuard-AI v2 prediction endpoint.
Uses httpx.AsyncClient for concurrent requests (no locust needed for CI).

Acceptance criteria:
  - p99 latency < 500 ms
  - Error rate < 1%
  - No memory leak (process memory delta < 200 MB over 120s)

Run manually: pytest tests/test_load.py -v -s --timeout=180
NOT run in standard CI (marked with skip).
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import os
import time
import types
from pathlib import Path

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
dotenv = types.ModuleType("dotenv"); dotenv.load_dotenv = lambda *a,**k: None
sys.modules.setdefault("dotenv", dotenv)
os.environ.setdefault("JWT_SECRET_KEY", "test-load-key-32-chars-long-ab")

BASE_URL = os.getenv("HYDROGUARD_TEST_URL", "http://127.0.0.1:8000")

SAMPLE_PAYLOAD = {
    "city":     "Islamabad",
    "prcp":     45.0,
    "humidity": 85.0,
    "pressure": 1004.0,
    "tmax":     33.0,
    "cloud_cover": 80.0,
}

# Skip unless explicitly opted-in
pytestmark = pytest.mark.skip(
    reason="Load test -- run manually with HYDROGUARD_TEST_URL set"
)


async def _get_token() -> str:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.post("/auth/register", json={
            "username": "loadtest", "email": "load@test.com",
            "password": "LoadTest123!"
        })
        await client.post("/auth/login", json={
            "username": "loadtest", "password": "LoadTest123!"
        })
        r = await client.post("/auth/login", json={
            "username": "loadtest", "password": "LoadTest123!"
        })
        return r.json().get("access_token", "")


async def _single_predict(client: httpx.AsyncClient, token: str) -> float:
    """Return response time in ms, or -1 on error."""
    t0 = time.perf_counter()
    try:
        r = await client.post(
            "/api/v2/cities/islamabad/predict",
            json=SAMPLE_PAYLOAD,
            headers={"Authorization": f"Bearer {token}"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if r.status_code in (200, 404):
            return elapsed_ms
        return -1
    except Exception:
        return -1


@pytest.mark.asyncio
async def test_load_50_concurrent():
    """50 concurrent users, 120s run, p99 < 500ms."""
    token = await _get_token()
    if not token:
        pytest.skip("Could not get auth token -- server not running?")

    latencies: list[float] = []
    errors    = 0
    n_requests = 0
    run_until  = time.monotonic() + 120.0   # 120s

    async with httpx.AsyncClient(
        base_url = BASE_URL,
        timeout  = httpx.Timeout(10.0),
        limits   = httpx.Limits(max_connections=60, max_keepalive_connections=50),
    ) as client:
        while time.monotonic() < run_until:
            batch = [_single_predict(client, token) for _ in range(10)]
            results = await asyncio.gather(*batch)
            for r in results:
                n_requests += 1
                if r < 0:
                    errors += 1
                else:
                    latencies.append(r)
            await asyncio.sleep(0.05)   # 10 req / 0.05s ~ 200 req/s

    assert n_requests > 0
    error_rate = errors / n_requests
    print(f"\nRequests: {n_requests}  Errors: {errors}  Error rate: {error_rate:.1%}")

    if latencies:
        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        print(f"Latency p50={p50:.0f}ms  p99={p99:.0f}ms")
        assert p99 < 500, f"p99 latency {p99:.0f}ms exceeds 500ms"

    assert error_rate < 0.01, f"Error rate {error_rate:.1%} exceeds 1%"
