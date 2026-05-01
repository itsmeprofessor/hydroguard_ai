/**
 * HydroGuard — Citizen App API Client
 * Communicates with the FastAPI backend /cities/* endpoints.
 * All functions return Promises.
 */

(function () {
  "use strict";

  // Auto-detect backend URL: same origin in production, localhost in dev
  const BASE =
    window.__HYDROGUARD_API__ ||
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://127.0.0.1:8000"
      : window.location.origin);

  /**
   * Core fetch helper — returns parsed JSON or throws {status, message}.
   */
  async function req(method, path, body) {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(BASE + path, opts);
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        msg = j.detail || j.error || msg;
      } catch (_) {}
      throw { status: res.status, message: msg };
    }
    return res.json();
  }

  /**
   * Retry wrapper with exponential backoff (max 3 attempts).
   */
  async function fetchWithRetry(fn, retries = 3) {
    let delay = 600;
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (err) {
        if (i === retries - 1) throw err;
        await new Promise(r => setTimeout(r, delay));
        delay *= 2;
      }
    }
  }

  // ─── Cache layer ─────────────────────────────────────────────────────────────
  const _cache = {};
  const _TTL_MS = 5 * 60 * 1000; // 5 min

  function _getCached(key) {
    const entry = _cache[key];
    if (!entry) return null;
    if (Date.now() - entry.ts > _TTL_MS) { delete _cache[key]; return null; }
    return entry.value;
  }

  function _setCached(key, value) {
    _cache[key] = { value, ts: Date.now() };
    return value;
  }

  // ─── Public API ──────────────────────────────────────────────────────────────

  const API = {
    BASE,

    /** List all cities with model availability. */
    getCities() {
      const cached = _getCached("cities");
      if (cached) return Promise.resolve(cached);
      return fetchWithRetry(() => req("GET", "/cities"))
        .then(v => _setCached("cities", v));
    },

    /** Snapshot risk for all cities. */
    getOverview() {
      return fetchWithRetry(() => req("GET", "/cities/overview"));
    },

    /**
     * Current risk for one city.
     * @param {string} city — display name or slug (e.g. "Islamabad")
     */
    getCityRisk(city) {
      const slug = city.toLowerCase().replace(/ /g, "_");
      const key  = `risk:${slug}`;
      const cached = _getCached(key);
      if (cached) return Promise.resolve(cached);
      return fetchWithRetry(() => req("GET", `/cities/${encodeURIComponent(slug)}/risk`))
        .then(v => _setCached(key, v));
    },

    /**
     * Submit a weather observation and get a prediction.
     * @param {string} city
     * @param {object} weather — { prcp, humidity, pressure, tmax, tmin, ... }
     */
    predict(city, weather = {}) {
      const slug = city.toLowerCase().replace(/ /g, "_");
      return req("POST", `/cities/${encodeURIComponent(slug)}/predict`, weather);
    },

    /**
     * 7-day forecast for a city.
     */
    getForecast(city) {
      const slug = city.toLowerCase().replace(/ /g, "_");
      const key  = `forecast:${slug}`;
      const cached = _getCached(key);
      if (cached) return Promise.resolve(cached);
      return fetchWithRetry(() => req("GET", `/cities/${encodeURIComponent(slug)}/forecast`))
        .then(v => _setCached(key, v));
    },

    /**
     * Recent alerts for a city.
     */
    getAlerts(city, n = 10) {
      const slug = city.toLowerCase().replace(/ /g, "_");
      return fetchWithRetry(() => req("GET", `/cities/${encodeURIComponent(slug)}/alerts?n=${n}`));
    },

    /**
     * Backend health check.
     */
    health() {
      return req("GET", "/health");
    },

    /** Clear local cache (useful for manual refresh). */
    clearCache() { Object.keys(_cache).forEach(k => delete _cache[k]); },
  };

  window.HydroAPI = API;
})();
