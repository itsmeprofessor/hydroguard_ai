/**
 * HydroGuard AI — Backend API Client
 * Handles JWT auth, transparent token refresh, all HTTP calls, and WebSocket.
 */
(function () {
  "use strict";

  // Allow backend URL override via <script>window.API_BASE = '...'</script>
  var BASE = (window.API_BASE || window.location.origin).replace(/\/$/, "");
  var SS = sessionStorage;

  /* ── Token helpers ─────────────────────────────────────────────── */
  function getToken()        { return SS.getItem("hg_access_token"); }
  function getRefreshToken() { return SS.getItem("hg_refresh_token"); }
  function getRole()         { return SS.getItem("hg_role"); }
  function getUsername()     { return SS.getItem("hg_username"); }

  function setTokens(access, refresh, role, username) {
    if (access)   SS.setItem("hg_access_token",  access);
    if (refresh)  SS.setItem("hg_refresh_token", refresh);
    if (role)     SS.setItem("hg_role",     role);
    if (username) SS.setItem("hg_username", username);
  }

  function clearTokens() {
    ["hg_access_token","hg_refresh_token","hg_role","hg_username"]
      .forEach(function(k){ SS.removeItem(k); });
  }

  /* ── Transparent token refresh ─────────────────────────────────── */
  var _refreshPromise = null;
  var _refreshFailCount = 0;
  var REFRESH_MAX_FAILURES = 3;

  function doRefresh() {
    if (_refreshPromise) return _refreshPromise;
    if (_refreshFailCount >= REFRESH_MAX_FAILURES) {
      clearTokens();
      window.dispatchEvent(new Event("hg:unauthorized"));
      return Promise.reject(new Error("Session expired after " + REFRESH_MAX_FAILURES + " failed refresh attempts."));
    }
    _refreshPromise = (function () {
      var rt = getRefreshToken();
      if (!rt) return Promise.reject(new Error("No refresh token"));
      return fetch(BASE + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      }).then(function (res) {
        if (!res.ok) {
          _refreshFailCount++;
          clearTokens();
          throw new Error("Session expired");
        }
        return res.json();
      }).then(function (data) {
        _refreshFailCount = 0; // reset on success
        if (data.access_token) SS.setItem("hg_access_token", data.access_token);
        return data.access_token;
      });
    })();
    _refreshPromise.finally(function () { _refreshPromise = null; });
    return _refreshPromise;
  }

  /* ── Core fetch wrapper ────────────────────────────────────────── */
  function req(method, path, body, extraHeaders, _retried) {
    var headers = Object.assign({ "Content-Type": "application/json" }, extraHeaders || {});
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    return fetch(BASE + path, {
      method: method,
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (res) {
      if (res.status === 401 && !_retried) {
        return doRefresh().then(function () {
          return req(method, path, body, extraHeaders, true);
        }).catch(function () {
          clearTokens();
          window.dispatchEvent(new Event("hg:unauthorized"));
          throw new Error("Session expired. Please sign in again.");
        });
      }
      return res.text().then(function (text) {
        var json;
        try { json = JSON.parse(text); } catch (e) { json = text; }
        if (!res.ok) {
          var msg = (json && json.detail) ? json.detail : (typeof json === "string" ? json : ("HTTP " + res.status));
          throw new Error(msg);
        }
        return json;
      });
    });
  }

  /* ── Public API object ─────────────────────────────────────────── */
  var API = {
    BASE: BASE,
    isLoggedIn: function () { return !!getToken(); },
    getToken:        getToken,
    getRefreshToken: getRefreshToken,
    getRole:         getRole,
    getUsername:     getUsername,
    clearTokens:     clearTokens,

    /* Auth --------------------------------------------------------- */
    login: function (email, password) {
      return req("POST", "/auth/login", { email: email, password: password })
        .then(function (data) {
          setTokens(data.access_token, data.refresh_token, data.role, data.username);
          return data;
        });
    },

    register: function (email, username, password) {
      // Note: role is NOT sent — the backend always creates USER accounts.
      // Admin promotion is a privileged workflow only.
      return req("POST", "/auth/register", {
        email: email, username: username, password: password,
      }).then(function (data) {
        setTokens(data.access_token, data.refresh_token, data.role, data.username);
        return data;
      });
    },

    logout: function () {
      return req("POST", "/auth/logout", null)
        .catch(function () {})
        .then(function () { clearTokens(); });
    },

    me: function () { return req("GET", "/auth/me"); },

    /* System ------------------------------------------------------- */
    health:        function () { return req("GET", "/health"); },
    modelInfo:     function () { return req("GET", "/model/info"); },
    modelVersions: function () { return req("GET", "/model/versions"); },

    /* Predictions -------------------------------------------------- */
    /* Route city from weatherData.city → /api/v2/cities/{slug}/predict */
    predict: function (weatherData) {
      var city = (weatherData && weatherData.city) || "islamabad";
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("POST", "/api/v2/cities/" + encodeURIComponent(slug) + "/predict", weatherData);
    },
    /* Legacy batch endpoint is tombstoned; expose per-city wrapper instead */
    predictBatch: function (dataArray) {
      var results = Promise.all(
        (dataArray || []).map(function (d) {
          var city = (d && d.city) || "islamabad";
          var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
          return req("POST", "/api/v2/cities/" + encodeURIComponent(slug) + "/predict", d)
            .catch(function (e) { return { error: e.message }; });
        })
      );
      return results;
    },

    /* Anomalies ---------------------------------------------------- */
    getAnomalies: function (params) {
      var qs = new URLSearchParams();
      Object.entries(params || {}).forEach(function (kv) {
        if (kv[1] != null) qs.set(kv[0], kv[1]);
      });
      return req("GET", "/anomalies?" + qs.toString());
    },
    getAnomaly: function (id) { return req("GET", "/anomalies/" + id); },
    getStatistics: function (params) {
      var qs = new URLSearchParams();
      Object.entries(params || {}).forEach(function (kv) {
        if (kv[1] != null) qs.set(kv[0], kv[1]);
      });
      return req("GET", "/anomalies/statistics?" + qs.toString());
    },

    /* Risk & Analytics --------------------------------------------- */
    getRiskMap:        function () { return req("GET", "/risk-map"); },
    getAdminAnalytics: function () { return req("GET", "/admin/analytics"); },
    getDatabaseStats:  function () { return req("GET", "/database/statistics"); },
    getAnalytics:      function () { return req("GET", "/analytics"); },

    /* Training (ADMIN only) --------------------------------------- */
    /* triggerTraining(city, params) or legacy triggerTraining(params) */
    triggerTraining: function (cityOrParams, params) {
      var city, reqParams;
      if (typeof cityOrParams === "string") {
        city = cityOrParams;
        reqParams = params || {};
      } else {
        /* Legacy: called with params object only — extract city if present */
        city = (cityOrParams && cityOrParams.city) || "islamabad";
        reqParams = cityOrParams || {};
      }
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("POST", "/api/v2/training/" + encodeURIComponent(slug), reqParams);
    },

    /* ── City-specific (v2 hybrid models) ─────────────────────────── */
    /* GET /api/v2/cities — list all cities + model availability       */
    getCityList: function () {
      return req("GET", "/api/v2/cities").then(function (d) {
        return d.cities || d || [];
      });
    },

    /* POST /api/v2/cities/refresh — rescan CSV + on-disk models (admin) */
    refreshCityRegistry: function () {
      return req("POST", "/api/v2/cities/refresh", {});
    },

    /* GET /api/v2/cities/overview — risk snapshot for all cities
     * v2 returns {cities:[{slug,name,risk_band,hri_score,...}], count}
     * Augmented with v1-compat fields for DashboardScreen (high_risk etc.) */
    getCitiesOverview: function () {
      return req("GET", "/api/v2/cities/overview").then(function (d) {
        var cities = d.cities || d || [];
        var high   = cities.filter(function (c) { return (c.risk_band || c.risk_level || "").toLowerCase() === "high"; }).length;
        var medium = cities.filter(function (c) { return (c.risk_band || c.risk_level || "").toLowerCase() === "medium"; }).length;
        var low    = cities.filter(function (c) { return (c.risk_band || c.risk_level || "").toLowerCase() === "low"; }).length;
        return Object.assign({}, d, {
          high_risk:   high,
          medium_risk: medium,
          low_risk:    low,
          total:       cities.length,
          overview:    cities.map(function (c) {
            return Object.assign({}, c, { risk_level: c.risk_band || c.risk_level });
          }),
        });
      });
    },

    /* GET /api/v2/cities/{city}/risk — live probabilistic risk      */
    getCityRisk: function (city) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("GET", "/api/v2/cities/" + encodeURIComponent(slug) + "/risk");
    },

    /* POST /api/v2/cities/{city}/predict — v2 probabilistic predict  */
    cityPredict: function (city, weatherData) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("POST", "/api/v2/cities/" + encodeURIComponent(slug) + "/predict", weatherData || {});
    },

    /* GET /api/v2/cities/{city}/forecast — 7-day outlook             */
    getCityForecast: function (city) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("GET", "/api/v2/cities/" + encodeURIComponent(slug) + "/forecast");
    },

    /* GET /api/v2/cities/{city}/alerts — recent alert events         */
    getCityAlerts: function (city, n) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("GET", "/api/v2/cities/" + encodeURIComponent(slug) + "/alerts?n=" + (n || 10));
    },

    /* GET /api/v2/cities/{city}/status — model status for a city     */
    getCityStatus: function (city) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("GET", "/api/v2/cities/" + encodeURIComponent(slug) + "/status");
    },

    /* POST /api/v2/training/{city} — trigger v2 city model training  */
    trainCityModel: function (city, params) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("POST", "/api/v2/training/" + encodeURIComponent(slug), params || {});
    },

    /* GET /api/v2/training/{city}/status — training run status        */
    getTrainingStatus: function (city) {
      var slug = city.toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
      return req("GET", "/api/v2/training/" + encodeURIComponent(slug) + "/status");
    },

    /* GET /api/v2/training/all-status — all-city training status      */
    getAllTrainingStatus: function () {
      return req("GET", "/api/v2/training/all-status");
    },

    /* Model Registry ─────────────────────────────────────────────── */
    getRegistry: function () {
      return req("GET", "/model/registry");
    },
    getCityRegistry: function (citySlug) {
      return req("GET", "/model/registry/" + encodeURIComponent(citySlug));
    },

    /* Drift Monitoring (v2) ──────────────────────────────────────── */
    getDriftState: function () {
      return req("GET", "/api/v2/drift");
    },
    getCityDrift: function (citySlug) {
      return req("GET", "/api/v2/drift/" + encodeURIComponent(citySlug));
    },

    /* Events (v2) ────────────────────────────────────────────────── */
    getEvents: function (params) {
      var qs = new URLSearchParams();
      Object.entries(params || {}).forEach(function (kv) {
        if (kv[1] != null) qs.set(kv[0], kv[1]);
      });
      return req("GET", "/api/v2/events?" + qs.toString());
    },
    getEventStatistics: function () {
      return req("GET", "/api/v2/events/statistics");
    },

    /* Live Weather ───────────────────────────────────────────────── */
    getLiveWeather: function (citySlug) {
      return req("GET", "/weather/" + encodeURIComponent(citySlug) + "/current");
    },
    getWeatherOverview: function () {
      return req("GET", "/weather/overview");
    },
    getWeatherForecast: function (citySlug, days) {
      return req("GET", "/weather/" + encodeURIComponent(citySlug) + "/forecast?days=" + (days || 7));
    },

    /* Dataset Profiler ───────────────────────────────────────────── */
    profileDataset: function () {
      return req("GET", "/api/v2/cities");  /* rescan triggered internally */
    },

    /* WebSocket with exponential-backoff reconnect ---------------- */
    connectWs: function (channel, onMessage, onClose) {
      var wsBase   = BASE.replace(/^http/, "ws");
      var delay    = 1000;
      var maxDelay = 30000;
      var stopped  = false;
      var ws       = null;

      function connect() {
        if (stopped) return;
        var token = getToken();
        // Public health channel doesn't need a token
        var url = wsBase + "/ws/" + channel + (token ? ("?token=" + token) : "");
        try {
          ws = new WebSocket(url);
        } catch (e) {
          console.error("WS connect error:", e);
          return;
        }

        ws.onopen = function () { delay = 1000; };  // reset backoff on success

        ws.onmessage = function (e) {
          try { onMessage(JSON.parse(e.data)); }
          catch (_) { onMessage(e.data); }
        };

        ws.onclose = function () {
          if (stopped) { if (onClose) onClose(); return; }
          setTimeout(connect, delay);
          delay = Math.min(delay * 2, maxDelay);
        };

        ws.onerror = function () {};  // onclose fires after onerror
      }

      connect();

      // Return a handle to close the connection intentionally
      return {
        close: function () { stopped = true; if (ws) ws.close(); },
      };
    },
  };

  window.API = API;
})();
