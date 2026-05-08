/**
 * HydroGuard — Citizen App API Client v3.2
 * ==========================================
 * Communicates with the FastAPI backend.
 *
 * Key improvements vs v3.1:
 *  - All city endpoints now use /api/v2/cities/* (probabilistic v2 predictions)
 *  - v2 response fields: risk_band, event_probability, is_alert, uncertainty,
 *    confidence_interval, model_entropy, inference_id
 *  - Weather endpoints (/weather/*) still used as primary for live data
 *  - Per-endpoint TTL cache (overview = 60s, risk = 5min, forecast = 10min)
 *  - AbortController to cancel in-flight requests on city change
 *  - Graceful degradation: weather fails → /api/v2/cities/{city}/risk
 *  - All functions return Promises
 */

(function () {
  "use strict";

  // ── Base URL ───────────────────────────────────────────────────────────────
  // Priority:
  //  1. Explicit override via window.__HYDROGUARD_API__
  //  2. Raw local dev server (port 5500/3000/8080) → talk directly to API :8000
  //  3. Everything else (nginx on :80/:443, any deployed host) → same-origin so
  //     all API requests flow through nginx (/cities, /weather, /health, etc.)
  const _devPorts = new Set(["5500", "3000", "8080"]);
  const BASE =
    window.__HYDROGUARD_API__ ||
    (_devPorts.has(window.location.port)
      ? "http://127.0.0.1:8000"   // `python -m http.server 5500` dev flow
      : window.location.origin);  // nginx/production: same-origin

  // ── Active AbortControllers (city-scoped) ─────────────────────────────────
  const _controllers = {};

  function _abort(key) {
    if (_controllers[key]) {
      _controllers[key].abort();
      delete _controllers[key];
    }
  }

  function _makeController(key) {
    _abort(key);
    const ctrl = new AbortController();
    _controllers[key] = ctrl;
    return ctrl;
  }

  // ── Core fetch ─────────────────────────────────────────────────────────────
  async function req(method, path, body, signal) {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
      signal,
    };
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(BASE + path, opts);
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        msg = j.detail || j.error || msg;
      } catch (_) {}
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  // ── Retry with backoff ─────────────────────────────────────────────────────
  async function fetchWithRetry(fn, retries = 3) {
    let delay = 600;
    let lastErr;
    for (let i = 0; i < retries; i++) {
      try {
        return await fn();
      } catch (err) {
        if (err.name === "AbortError") throw err; // don't retry aborts
        lastErr = err;
        if (i < retries - 1) await new Promise(r => setTimeout(r, delay));
        delay = Math.min(delay * 2, 5000);
      }
    }
    throw lastErr;
  }

  // ── Cache layer with per-key TTL ──────────────────────────────────────────
  const _cache = {};

  const TTL = {
    cities:   10 * 60 * 1000,  // city list changes rarely
    risk:      5 * 60 * 1000,  // current risk: 5 min
    forecast: 10 * 60 * 1000,  // forecast: 10 min
    weather:   5 * 60 * 1000,  // live weather: 5 min
    overview:      60 * 1000,  // overview: 1 min
    default:   5 * 60 * 1000,
  };

  function _getCached(key, ttlKey = "default") {
    const entry = _cache[key];
    if (!entry) return null;
    const ttl = TTL[ttlKey] ?? TTL.default;
    if (Date.now() - entry.ts > ttl) { delete _cache[key]; return null; }
    return entry.value;
  }

  function _setCached(key, value) {
    _cache[key] = { value, ts: Date.now() };
    return value;
  }

  // ── Slug helper ───────────────────────────────────────────────────────────
  function slugify(city) {
    return city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  const API = {
    BASE,

    /** List all registered cities (dynamic — from dataset + trained models). */
    getCities() {
      const key = "cities";
      const cached = _getCached(key, "cities");
      if (cached) return Promise.resolve(cached);
      // v2 returns {cities:[...], total, trained, untrained} — normalise to array
      return fetchWithRetry(() => req("GET", "/api/v2/cities"))
        .then(v => _setCached(key, v.cities || v));
    },

    /** Risk snapshot for all cities. */
    getOverview() {
      const key = "overview";
      const cached = _getCached(key, "overview");
      if (cached) return Promise.resolve(cached);
      return fetchWithRetry(() => req("GET", "/api/v2/cities/overview"))
        .then(v => _setCached(key, v));
    },

    /**
     * Current risk for a city.
     * Tries the live weather endpoint first; falls back to static risk endpoint.
     */
    async getCityRisk(city) {
      const slug = slugify(city);
      const key  = `risk:${slug}`;
      const cached = _getCached(key, "risk");
      if (cached) return cached;

      const ctrl = _makeController(`risk:${slug}`);
      const signal = ctrl.signal;

      // Try live weather + prediction first
      try {
        const data = await req("GET", `/weather/${encodeURIComponent(slug)}/current`, undefined, signal);
        return _setCached(key, data);
      } catch (e) {
        if (e.name === "AbortError") throw e;
        // Fall back to static risk endpoint
      }

      try {
        // v2 risk endpoint returns probabilistic prediction fields
        const data = await fetchWithRetry(
          () => req("GET", `/api/v2/cities/${encodeURIComponent(slug)}/risk`, undefined, signal)
        );
        return _setCached(key, data);
      } catch (e) {
        if (e.name === "AbortError") throw e;
        throw e;
      }
    },

    /**
     * Submit a weather observation and get a v2 probabilistic prediction.
     * @param {string} city
     * @param {object} weather — { prcp, humidity, pressure, tmax, tmin, ... }
     *   Required v2 fields: prcp, humidity, pressure
     * Returns v2 shape: { inference_id, risk_band, event_probability, is_alert,
     *                     uncertainty, confidence_interval, model_entropy, source, ... }
     */
    predict(city, weather = {}) {
      const slug = slugify(city);
      return req("POST", `/api/v2/cities/${encodeURIComponent(slug)}/predict`, weather);
    },

    /**
     * 7-day forecast — uses live weather if available, fallback to generated.
     */
    async getForecast(city, days = 7) {
      const slug = slugify(city);
      const key  = `forecast:${slug}`;
      const cached = _getCached(key, "forecast");
      if (cached) return cached;

      const ctrl = _makeController(`forecast:${slug}`);
      const signal = ctrl.signal;

      // Try live weather forecast first
      try {
        const data = await req(
          "GET",
          `/weather/${encodeURIComponent(slug)}/forecast?days=${days}`,
          undefined,
          signal
        );
        return _setCached(key, data);
      } catch (e) {
        if (e.name === "AbortError") throw e;
        // Fall back to generated forecast
      }

      const data = await fetchWithRetry(
        () => req("GET", `/api/v2/cities/${encodeURIComponent(slug)}/forecast`, undefined, signal)
      );
      return _setCached(key, data);
    },

    /**
     * Live current weather (raw, without prediction).
     */
    getLiveWeather(city) {
      const slug = slugify(city);
      return fetchWithRetry(() => req("GET", `/weather/${encodeURIComponent(slug)}/current`));
    },

    /**
     * Recent alerts for a city.
     * Returns v2 shape: { city, alerts: [{inference_id, risk_band, is_alert, ...}], count }
     */
    getAlerts(city, n = 10) {
      const slug = slugify(city);
      return fetchWithRetry(
        () => req("GET", `/api/v2/cities/${encodeURIComponent(slug)}/alerts?n=${n}`)
      );
    },

    /**
     * City model status (v2).
     * Returns { slug, name, has_model, has_data, fusion_model_fitted, calibrator_fitted }
     */
    getCityStatus(city) {
      const slug = slugify(city);
      return req("GET", `/api/v2/cities/${encodeURIComponent(slug)}/status`);
    },

    /** Backend health check (includes drift state, registry summary). */
    health() {
      return req("GET", "/health");
    },

    /** Cancel all in-flight requests for a city (call before city change). */
    cancelCity(city) {
      const slug = slugify(city);
      _abort(`risk:${slug}`);
      _abort(`forecast:${slug}`);
    },

    /** Clear local cache (forces next request to hit the backend). */
    clearCache() {
      Object.keys(_cache).forEach(k => delete _cache[k]);
    },

    /** Clear cache for a specific city. */
    clearCityCache(city) {
      const slug = slugify(city);
      Object.keys(_cache)
        .filter(k => k.includes(slug))
        .forEach(k => delete _cache[k]);
    },
  };

  window.HydroAPI = API;
})();
