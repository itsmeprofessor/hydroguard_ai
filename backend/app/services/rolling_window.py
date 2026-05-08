"""
HydroGuard-AI — Redis-backed Rolling Window Buffer
=====================================================
Stores the last 48 hourly weather observations per city in Redis.
Used by FeaturePipelineV2 to compute rolling delta features:
  - pressure_delta_3h, pressure_delta_6h
  - humidity_delta_3h
  - rain_rate_1h, rain_accumulation_3h, rain_accumulation_6h
  - cloud_jump_3h

Redis key: hg:rolling:{city_slug}  (Sorted Set, score = unix timestamp)
TTL: 48 hours per entry
Multi-worker safe (Redis-backed, not in-process).

Falls back gracefully when Redis is unavailable — returns None deltas.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_ROLLING_PREFIX  = "hg:rolling:"
_MAX_ENTRIES     = 48          # 48 hours of hourly observations
_TTL_SECONDS     = 48 * 3600  # 48 hours


# ─────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────

@dataclass
class HourlyObservation:
    city_slug:  str
    ts:         float          # unix timestamp (timezone-aware source)
    pressure:   Optional[float] = None
    humidity:   Optional[float] = None
    precip_mm:  Optional[float] = None
    cloud:      Optional[float] = None
    temp_c:     Optional[float] = None

    def to_json(self) -> str:
        return json.dumps({
            "city_slug": self.city_slug,
            "ts":        self.ts,
            "pressure":  self.pressure,
            "humidity":  self.humidity,
            "precip_mm": self.precip_mm,
            "cloud":     self.cloud,
            "temp_c":    self.temp_c,
        })

    @classmethod
    def from_json(cls, s: str) -> "HourlyObservation":
        d = json.loads(s)
        return cls(
            city_slug  = d["city_slug"],
            ts         = float(d["ts"]),
            pressure   = d.get("pressure"),
            humidity   = d.get("humidity"),
            precip_mm  = d.get("precip_mm"),
            cloud      = d.get("cloud"),
            temp_c     = d.get("temp_c"),
        )


@dataclass
class RollingDeltas:
    """All rolling delta features derived from the hourly buffer."""
    pressure_delta_3h:    Optional[float] = None
    pressure_delta_6h:    Optional[float] = None
    humidity_delta_3h:    Optional[float] = None
    rain_rate_1h:         Optional[float] = None
    rain_accumulation_3h: Optional[float] = None
    rain_accumulation_6h: Optional[float] = None
    cloud_jump_3h:        Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
#  Buffer
# ─────────────────────────────────────────────────────────────

class RollingWindowBuffer:
    """
    Redis-backed hourly observation store per city.

    push(obs)         — store one observation
    get_window(city, n) — return last n observations, oldest-first
    get_deltas(city, now_ts) — compute all delta features
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, city_slug: str) -> str:
        return f"{_ROLLING_PREFIX}{city_slug}"

    # ── Push ────────────────────────────────────────────────

    async def push(self, obs: HourlyObservation) -> None:
        """Store one hourly observation. Trims to last _MAX_ENTRIES."""
        if not self._redis:
            return
        key = self._key(obs.city_slug)
        try:
            pipe = self._redis.pipeline()
            # Score = unix timestamp for time-ordered retrieval
            await pipe.zadd(key, {obs.to_json(): obs.ts})
            # Trim to keep only the most recent _MAX_ENTRIES
            await pipe.zremrangebyrank(key, 0, -(_MAX_ENTRIES + 1))
            # Sliding TTL
            await pipe.expire(key, _TTL_SECONDS)
            await pipe.execute()
        except Exception as exc:
            logger.debug("RollingWindowBuffer.push failed: %s", exc)

    # ── Read ────────────────────────────────────────────────

    async def get_window(
        self,
        city_slug: str,
        n: int = 24,
        before_ts: Optional[float] = None,
    ) -> list[HourlyObservation]:
        """
        Return last n observations, oldest-first.
        Returns empty list if fewer than n observations exist.
        before_ts: if set, only return observations with ts < before_ts.
        """
        if not self._redis:
            return []
        key = self._key(city_slug)
        try:
            max_score = before_ts if before_ts is not None else "+inf"
            # zrevrangebyscore returns newest-first; we want oldest-first so reverse
            raw = await self._redis.zrevrangebyscore(
                key,
                max=max_score,
                min="-inf",
                start=0,
                num=n,
                withscores=False,
            )
            if len(raw) < n:
                return []
            # raw is newest-first → reverse to oldest-first
            obs_list = [HourlyObservation.from_json(r) for r in reversed(raw)]
            return obs_list
        except Exception as exc:
            logger.debug("RollingWindowBuffer.get_window failed: %s", exc)
            return []

    async def get_deltas(
        self,
        city_slug: str,
        current_ts: Optional[float] = None,
    ) -> RollingDeltas:
        """
        Compute all rolling delta features.
        Returns RollingDeltas with None fields when history is insufficient.
        """
        if not self._redis:
            return RollingDeltas()

        now_ts = current_ts or time.time()
        key    = self._key(city_slug)

        try:
            # Fetch last 7 hours (enough for all deltas up to 6h)
            raw = await self._redis.zrevrangebyscore(
                key,
                max=now_ts,
                min=now_ts - 7 * 3600,
                withscores=True,
            )
            if not raw:
                return RollingDeltas()

            # Build list of (obs, score) sorted oldest-first
            entries: list[tuple[HourlyObservation, float]] = []
            for member, score in raw:
                try:
                    obs = HourlyObservation.from_json(member)
                    entries.append((obs, float(score)))
                except Exception:
                    continue
            entries.sort(key=lambda x: x[1])   # oldest first

            if not entries:
                return RollingDeltas()

            def _find_at_offset(hours: float) -> Optional[HourlyObservation]:
                """Find observation closest to (now_ts - hours*3600)."""
                target = now_ts - hours * 3600
                best: Optional[HourlyObservation] = None
                best_dt = float("inf")
                for obs, score in entries:
                    dt = abs(score - target)
                    if dt < best_dt:
                        best_dt = dt
                        best    = obs
                return best if best_dt < 3600 else None   # within 1h tolerance

            current_obs = entries[-1][0] if entries else None

            obs_1h  = _find_at_offset(1.0)
            obs_3h  = _find_at_offset(3.0)
            obs_6h  = _find_at_offset(6.0)

            deltas = RollingDeltas()

            # Pressure deltas (drop = negative = destabilising)
            if current_obs and obs_3h and current_obs.pressure and obs_3h.pressure:
                deltas.pressure_delta_3h = current_obs.pressure - obs_3h.pressure
            if current_obs and obs_6h and current_obs.pressure and obs_6h.pressure:
                deltas.pressure_delta_6h = current_obs.pressure - obs_6h.pressure

            # Humidity delta
            if current_obs and obs_3h and current_obs.humidity and obs_3h.humidity:
                deltas.humidity_delta_3h = current_obs.humidity - obs_3h.humidity

            # Rain rate (last 1h precipitation)
            if current_obs and obs_1h and current_obs.precip_mm is not None and obs_1h.precip_mm is not None:
                deltas.rain_rate_1h = max(0.0, current_obs.precip_mm - obs_1h.precip_mm)

            # Rain accumulation (cumulative mm in window)
            def _accumulate_precip(obs_start, obs_end) -> Optional[float]:
                if obs_start is None or obs_end is None:
                    return None
                t_start = obs_start[1] if isinstance(obs_start, tuple) else now_ts - 6*3600
                t_end   = now_ts
                total   = 0.0
                count   = 0
                prev_precip: Optional[float] = None
                for obs, score in entries:
                    if t_start <= score <= t_end:
                        if obs.precip_mm is not None:
                            if prev_precip is not None:
                                total += max(0.0, obs.precip_mm - prev_precip)
                            prev_precip = obs.precip_mm
                            count += 1
                return total if count > 0 else None

            # Simpler accumulation: sum of positive precip deltas in window
            def _sum_precip_window(hours: float) -> Optional[float]:
                t_start = now_ts - hours * 3600
                window_entries = [(o, s) for o, s in entries if s >= t_start]
                if len(window_entries) < 2:
                    return None
                total = 0.0
                prev  = None
                for obs, _ in sorted(window_entries, key=lambda x: x[1]):
                    if obs.precip_mm is not None:
                        if prev is not None:
                            total += max(0.0, obs.precip_mm - prev)
                        prev = obs.precip_mm
                return total

            deltas.rain_accumulation_3h = _sum_precip_window(3.0)
            deltas.rain_accumulation_6h = _sum_precip_window(6.0)

            # Cloud jump (3h)
            if current_obs and obs_3h and current_obs.cloud is not None and obs_3h.cloud is not None:
                deltas.cloud_jump_3h = current_obs.cloud - obs_3h.cloud

            return deltas

        except Exception as exc:
            logger.debug("RollingWindowBuffer.get_deltas failed: %s", exc)
            return RollingDeltas()

    async def count(self, city_slug: str) -> int:
        """Return number of stored observations for a city."""
        if not self._redis:
            return 0
        try:
            return await self._redis.zcard(self._key(city_slug))
        except Exception:
            return 0


# ─────────────────────────────────────────────────────────────
#  Singleton — set in lifespan
# ─────────────────────────────────────────────────────────────

rolling_window_buffer: Optional[RollingWindowBuffer] = None


def init_rolling_window(redis_client) -> RollingWindowBuffer:
    """Initialise and return the global RollingWindowBuffer singleton."""
    global rolling_window_buffer
    rolling_window_buffer = RollingWindowBuffer(redis_client)
    logger.info("RollingWindowBuffer initialised")
    return rolling_window_buffer


def get_rolling_window() -> Optional[RollingWindowBuffer]:
    """Return the singleton, or None if not initialised."""
    return rolling_window_buffer
