"""
HydroGuard-AI — WeatherAPI.com Service (v2)
============================================
Single provider: WeatherAPI.com (https://www.weatherapi.com)
No fallback provider. Fail loudly on errors.

Features:
  - Circuit breaker: 5 failures / 60s → OPEN for 120s
  - Retry: exponential backoff × 3 (0.5s, 1.5s, 4.5s) on timeout / 5xx
  - Redis cache: hg:weather:current:{city_slug}, TTL = WEATHER_CACHE_TTL
  - Hard timeout: 5s connect + 5s read
  - Structured error types

Usage:
    from app.services.weather_api import weather_provider, get_weather_provider
    obs = await weather_provider.get_current("Islamabad")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import WEATHERAPI_KEY, WEATHER_CACHE_TTL
from app.services.city_model_service import CITY_METADATA, _slug

logger = logging.getLogger(__name__)

WEATHERAPI_BASE = "https://api.weatherapi.com/v1"


# ──────────────────────────────────────────────────────────
#  Structured error types
# ──────────────────────────────────────────────────────────

class HydroGuardWeatherError(Exception):
    """Base class for all weather provider errors."""


class WeatherAPIUnavailableError(HydroGuardWeatherError):
    def __init__(self, city: str, status_code: int | None = None):
        self.city        = city
        self.status_code = status_code
        super().__init__(f"WeatherAPI unavailable for '{city}' (status={status_code})")


class WeatherAPITimeoutError(HydroGuardWeatherError):
    def __init__(self, city: str, elapsed: float):
        self.city    = city
        self.elapsed = elapsed
        super().__init__(f"WeatherAPI timed out for '{city}' after {elapsed:.1f}s")


class WeatherAPISchemaError(HydroGuardWeatherError):
    def __init__(self, city: str, field_name: str):
        self.city       = city
        self.field_name = field_name
        super().__init__(f"WeatherAPI response missing field '{field_name}' for '{city}'")


# ──────────────────────────────────────────────────────────
#  Response data model
# ──────────────────────────────────────────────────────────

@dataclass
class WeatherSnapshot:
    city_slug:      str
    fetched_at:     datetime
    provider:       str  = "weatherapi"
    temp_c:         Optional[float] = None
    feelslike_c:    Optional[float] = None
    humidity:       Optional[float] = None
    pressure_mb:    Optional[float] = None
    precip_mm:      Optional[float] = None
    cloud:          Optional[float] = None
    wind_kph:       Optional[float] = None
    dew_point_c:    Optional[float] = None
    condition_code: Optional[int]   = None
    vis_km:         Optional[float] = None
    uv_index:       Optional[float] = None
    # 7-day forecast fields (populated by get_forecast)
    forecast_date:  Optional[str]   = None
    max_temp_c:     Optional[float] = None
    min_temp_c:     Optional[float] = None
    daily_precip_mm: Optional[float] = None
    daily_chance_rain: Optional[int] = None

    def to_feature_dict(self) -> dict[str, Any]:
        """Map WeatherAPI fields → HydroGuard feature names for inference."""
        temp = self.temp_c
        return {
            "prcp":        self.precip_mm        or 0.0,
            "humidity":    self.humidity          or 50.0,
            "pressure":    self.pressure_mb       or 1013.0,
            "cloud_cover": self.cloud             or 0.0,
            "tmax":        self.max_temp_c or temp or 25.0,
            "tmin":        self.min_temp_c or temp or 20.0,
            "tavg":        temp                   or 22.5,
            "dew_point":   self.dew_point_c       or 10.0,
            "wspd":        self.wind_kph          or 0.0,
            "temp_range":  ((self.max_temp_c or temp or 25.0)
                           - (self.min_temp_c or temp or 20.0)),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "city_slug":    self.city_slug,
            "fetched_at":   self.fetched_at.isoformat(),
            "provider":     self.provider,
            "temp_c":       self.temp_c,
            "feelslike_c":  self.feelslike_c,
            "humidity":     self.humidity,
            "pressure_mb":  self.pressure_mb,
            "precip_mm":    self.precip_mm,
            "cloud":        self.cloud,
            "wind_kph":     self.wind_kph,
            "dew_point_c":  self.dew_point_c,
            "condition_code": self.condition_code,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WeatherSnapshot":
        d = dict(d)
        d["fetched_at"] = datetime.fromisoformat(d["fetched_at"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ──────────────────────────────────────────────────────────
#  Circuit breaker
# ──────────────────────────────────────────────────────────

class _CircuitBreaker:
    """Simple count-based circuit breaker."""
    FAILURE_THRESHOLD  = 5
    OPEN_DURATION_S    = 120
    OBSERVATION_WINDOW = 60

    def __init__(self):
        self._failures:    list[float] = []   # timestamps
        self._open_until:  float       = 0.0
        self._state:       str         = "CLOSED"   # CLOSED | OPEN | HALF_OPEN

    @property
    def state(self) -> str:
        now = time.monotonic()
        if self._state == "OPEN":
            if now >= self._open_until:
                self._state = "HALF_OPEN"
                logger.info("Circuit breaker → HALF_OPEN (probing)")
        return self._state

    def record_success(self) -> None:
        self._failures = []
        if self._state in ("OPEN", "HALF_OPEN"):
            logger.info("Circuit breaker → CLOSED (success)")
        self._state = "CLOSED"

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures = [t for t in self._failures
                          if now - t < self.OBSERVATION_WINDOW]
        self._failures.append(now)
        if len(self._failures) >= self.FAILURE_THRESHOLD:
            self._state      = "OPEN"
            self._open_until = now + self.OPEN_DURATION_S
            logger.warning(
                "Circuit breaker → OPEN (%d failures in %ds). Resets in %ds.",
                len(self._failures), self.OBSERVATION_WINDOW, self.OPEN_DURATION_S,
            )

    def is_open(self) -> bool:
        return self.state == "OPEN"

    def status(self) -> dict:
        return {
            "state":        self.state,
            "failure_count": len(self._failures),
            "open_until":   datetime.fromtimestamp(
                self._open_until, tz=timezone.utc
            ).isoformat() if self._state == "OPEN" else None,
        }


# ──────────────────────────────────────────────────────────
#  City coordinate lookup
# ──────────────────────────────────────────────────────────

def _city_coords(city: str) -> Optional[tuple[float, float]]:
    s = _slug(city)
    if s in CITY_METADATA:
        m = CITY_METADATA[s]
        if m.get("lat") and m.get("lon"):
            return m["lat"], m["lon"]
    return None


def _city_query(city: str) -> str:
    """Return lat,lon string if known, otherwise city name for WeatherAPI q= param."""
    coords = _city_coords(city)
    if coords:
        return f"{coords[0]},{coords[1]}"
    return city


# ──────────────────────────────────────────────────────────
#  WeatherAPI provider
# ──────────────────────────────────────────────────────────

class WeatherAPIProvider:
    """
    Fetches weather from WeatherAPI.com. Single provider, no fallback.

    Circuit breaker: 5 failures/60s → OPEN 120s → HALF_OPEN probe.
    Retry: up to 3 attempts with delays [0.5, 1.5, 4.5]s.
      Retry only on: httpx.TimeoutException, 5xx responses.
      Never retry: 4xx responses.
    Cache: Redis key hg:weather:current:{city_slug}, TTL=WEATHER_CACHE_TTL.
    Timeout: 5s connect + 5s read.
    """

    RETRY_DELAYS = [0.5, 1.5, 4.5]

    def __init__(
        self,
        api_key: str,
        redis_client=None,
        timeout_s: float = 5.0,
    ):
        self._key     = api_key
        self._redis   = redis_client
        self._timeout = httpx.Timeout(timeout_s, connect=timeout_s)
        self._cb      = _CircuitBreaker()
        # Metrics
        self.request_count   = 0
        self.error_count     = 0
        self.cache_hit_count = 0

    # ── Public API ──────────────────────────────────────────

    async def get_current(self, city: str, force_refresh: bool = False) -> WeatherSnapshot:
        """Fetch current conditions. Raises HydroGuardWeatherError on failure."""
        slug = _slug(city)

        if not force_refresh:
            cached = await self._cache_get(f"hg:weather:current:{slug}")
            if cached:
                self.cache_hit_count += 1
                return WeatherSnapshot.from_dict(cached)

        data = await self._request(
            "/current.json",
            params={"q": _city_query(city), "aqi": "no"},
            city=city,
        )
        snap = self._parse_current(data, slug)
        await self._cache_set(
            f"hg:weather:current:{slug}",
            snap.to_dict(),
            ttl=WEATHER_CACHE_TTL,
        )
        return snap

    async def get_current_for_all_cities(
        self, slugs: list[str]
    ) -> dict[str, Optional[WeatherSnapshot]]:
        """Fetch current conditions for many cities in parallel.

        Returns a dict mapping each input slug to its WeatherSnapshot, or
        None if that city's fetch failed (so one bad city doesn't drop the
        whole response).
        """
        async def _safe_get(slug: str) -> tuple[str, Optional[WeatherSnapshot]]:
            try:
                snap = await self.get_current(slug)
                return slug, snap
            except HydroGuardWeatherError as exc:
                logger.warning("Overview fetch failed for %s: %s", slug, exc)
                return slug, None

        results = await asyncio.gather(*(_safe_get(s) for s in slugs))
        return dict(results)

    async def get_forecast(self, city: str, days: int = 7) -> list[WeatherSnapshot]:
        """Fetch N-day forecast. Returns list of WeatherSnapshot (one per day)."""
        slug = _slug(city)
        cache_key = f"hg:weather:forecast:{slug}:{days}"

        cached = await self._cache_get(cache_key)
        if cached and isinstance(cached, list):
            return [WeatherSnapshot.from_dict(d) for d in cached]

        data = await self._request(
            "/forecast.json",
            params={"q": _city_query(city), "days": days, "aqi": "no", "alerts": "no"},
            city=city,
        )
        snaps = self._parse_forecast(data, slug)
        await self._cache_set(cache_key, [s.to_dict() for s in snaps], ttl=WEATHER_CACHE_TTL)
        return snaps

    async def get_historical(self, city: str, target_date: date) -> WeatherSnapshot:
        """Fetch historical conditions for a specific date."""
        slug      = _slug(city)
        date_str  = target_date.isoformat()
        cache_key = f"hg:weather:historical:{slug}:{date_str}"

        cached = await self._cache_get(cache_key)
        if cached:
            self.cache_hit_count += 1
            return WeatherSnapshot.from_dict(cached)

        data = await self._request(
            "/history.json",
            params={"q": _city_query(city), "dt": date_str},
            city=city,
        )
        # Historical has same forecast structure, take first day
        snaps = self._parse_forecast(data, slug)
        snap  = snaps[0] if snaps else self._empty_snapshot(slug)
        await self._cache_set(cache_key, snap.to_dict(), ttl=3600 * 24)  # 24h for history
        return snap

    async def health(self) -> dict:
        """Return circuit breaker status + request metrics."""
        return {
            "provider":       "weatherapi",
            "api_key_set":    bool(self._key),
            "circuit_breaker": self._cb.status(),
            "metrics": {
                "requests":   self.request_count,
                "errors":     self.error_count,
                "cache_hits": self.cache_hit_count,
            },
        }

    # ── Internal helpers ────────────────────────────────────

    async def _request(
        self,
        endpoint: str,
        params: dict,
        city: str,
    ) -> dict[str, Any]:
        if self._cb.is_open():
            raise WeatherAPIUnavailableError(city, status_code=None)

        if not self._key:
            raise WeatherAPIUnavailableError(city, status_code=None)

        params["key"] = self._key
        url            = WEATHERAPI_BASE + endpoint
        last_exc: Exception | None = None

        for attempt, delay in enumerate(self.RETRY_DELAYS, start=1):
            self.request_count += 1
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)

                elapsed = time.monotonic() - t0

                if resp.status_code == 200:
                    self._cb.record_success()
                    return resp.json()

                if resp.status_code < 500:
                    # 4xx — do NOT retry
                    self.error_count += 1
                    self._cb.record_failure()
                    raise WeatherAPIUnavailableError(city, resp.status_code)

                # 5xx — retry
                logger.warning(
                    "WeatherAPI %s returned %d (attempt %d/%d)",
                    endpoint, resp.status_code, attempt, len(self.RETRY_DELAYS),
                )
                last_exc = WeatherAPIUnavailableError(city, resp.status_code)

            except httpx.TimeoutException:
                elapsed  = time.monotonic() - t0
                last_exc = WeatherAPITimeoutError(city, elapsed)
                logger.warning(
                    "WeatherAPI timeout for '%s' after %.1fs (attempt %d/%d)",
                    city, elapsed, attempt, len(self.RETRY_DELAYS),
                )

            except (WeatherAPIUnavailableError, WeatherAPITimeoutError):
                raise   # already handled above

            except Exception as exc:
                last_exc = exc

            if attempt < len(self.RETRY_DELAYS):
                await asyncio.sleep(delay)

        self.error_count += 1
        self._cb.record_failure()
        raise last_exc or WeatherAPIUnavailableError(city)

    def _parse_current(self, data: dict, slug: str) -> WeatherSnapshot:
        cur = data.get("current", {})
        if not cur:
            raise WeatherAPISchemaError(slug, "current")
        return WeatherSnapshot(
            city_slug      = slug,
            fetched_at     = datetime.now(timezone.utc),
            temp_c         = cur.get("temp_c"),
            feelslike_c    = cur.get("feelslike_c"),
            humidity       = cur.get("humidity"),
            pressure_mb    = cur.get("pressure_mb"),
            precip_mm      = cur.get("precip_mm"),
            cloud          = cur.get("cloud"),
            wind_kph       = cur.get("wind_kph"),
            dew_point_c    = cur.get("dewpoint_c"),
            vis_km         = cur.get("vis_km"),
            uv_index       = cur.get("uv"),
            condition_code = cur.get("condition", {}).get("code"),
        )

    def _parse_forecast(self, data: dict, slug: str) -> list[WeatherSnapshot]:
        days  = data.get("forecast", {}).get("forecastday", [])
        snaps = []
        for day_data in days:
            day = day_data.get("day", {})
            hr  = day_data.get("hour", [{}])
            # Pick noon hour for representative conditions
            noon = next((h for h in hr if "12:00" in h.get("time", "")), hr[0] if hr else {})
            snaps.append(WeatherSnapshot(
                city_slug          = slug,
                fetched_at         = datetime.now(timezone.utc),
                forecast_date      = day_data.get("date"),
                temp_c             = noon.get("temp_c"),
                feelslike_c        = noon.get("feelslike_c"),
                humidity           = noon.get("humidity"),
                pressure_mb        = noon.get("pressure_mb"),
                precip_mm          = noon.get("precip_mm"),
                cloud              = noon.get("cloud"),
                wind_kph           = noon.get("wind_kph"),
                dew_point_c        = noon.get("dewpoint_c"),
                condition_code     = noon.get("condition", {}).get("code"),
                max_temp_c         = day.get("maxtemp_c"),
                min_temp_c         = day.get("mintemp_c"),
                daily_precip_mm    = day.get("totalprecip_mm"),
                daily_chance_rain  = day.get("daily_chance_of_rain"),
            ))
        return snaps

    def _empty_snapshot(self, slug: str) -> WeatherSnapshot:
        return WeatherSnapshot(city_slug=slug, fetched_at=datetime.now(timezone.utc))

    async def _cache_get(self, key: str) -> dict | list | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis cache get failed: %s", exc)
        return None

    async def _cache_set(self, key: str, value: dict | list, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.setex(key, ttl, json.dumps(value))
        except Exception as exc:
            logger.debug("Redis cache set failed: %s", exc)


# ──────────────────────────────────────────────────────────
#  Singleton — initialised in lifespan (main.py)
# ──────────────────────────────────────────────────────────

weather_provider: Optional[WeatherAPIProvider] = None

# Legacy shim — the old code called `weather_service`
# After full migration, remove this alias
weather_service: Optional[WeatherAPIProvider] = None


def get_weather_provider() -> WeatherAPIProvider:
    """Dependency injection. Raises RuntimeError if not initialised."""
    if weather_provider is None:
        raise RuntimeError(
            "WeatherAPIProvider not initialised. "
            "Call init_weather_provider() in lifespan first."
        )
    return weather_provider


def init_weather_provider(redis_client=None) -> WeatherAPIProvider:
    """
    Initialise the global weather provider singleton.
    Called from app lifespan.
    """
    global weather_provider, weather_service
    key = WEATHERAPI_KEY
    if not key:
        logger.warning(
            "WEATHERAPI_KEY not set — WeatherAPI calls will fail. "
            "Set WEATHERAPI_KEY in .env to enable live weather data."
        )
    weather_provider = WeatherAPIProvider(
        api_key      = key,
        redis_client = redis_client,
    )
    weather_service = weather_provider   # legacy alias
    logger.info("WeatherAPIProvider initialised (key_set=%s)", bool(key))
    return weather_provider
