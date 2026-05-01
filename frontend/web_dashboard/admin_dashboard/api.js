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

  function doRefresh() {
    if (_refreshPromise) return _refreshPromise;
    _refreshPromise = (function () {
      var rt = getRefreshToken();
      if (!rt) return Promise.reject(new Error("No refresh token"));
      return fetch(BASE + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      }).then(function (res) {
        if (!res.ok) { clearTokens(); throw new Error("Session expired"); }
        return res.json();
      }).then(function (data) {
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

    register: function (email, username, password, role) {
      return req("POST", "/auth/register", {
        email: email, username: username,
        password: password, role: role || "USER",
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
    predict: function (weatherData) {
      return req("POST", "/predict", weatherData);
    },
    predictBatch: function (dataArray) {
      return req("POST", "/predict/batch", { data: dataArray });
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
    triggerTraining: function (params) {
      return req("POST", "/train", params || {});
    },

    /* ── City-specific (v3 hybrid models) ─────────────────────── */
    /* GET /cities — list all cities + model availability           */
    getCityList: function () {
      return req("GET", "/cities");
    },

    /* POST /cities/refresh — rescan CSV + on-disk models (admin)   */
    refreshCityRegistry: function () {
      return req("POST", "/cities/refresh", {});
    },

    /* GET /cities/overview — risk snapshot for all 10 cities      */
    getCitiesOverview: function () {
      return req("GET", "/cities/overview");
    },

    /* GET /cities/{city}/risk — current risk for one city          */
    getCityRisk: function (city) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("GET", "/cities/" + encodeURIComponent(slug) + "/risk");
    },

    /* POST /cities/{city}/predict — submit weather data            */
    cityPredict: function (city, weatherData) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("POST", "/cities/" + encodeURIComponent(slug) + "/predict", weatherData || {});
    },

    /* GET /cities/{city}/forecast — 7-day outlook                  */
    getCityForecast: function (city) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("GET", "/cities/" + encodeURIComponent(slug) + "/forecast");
    },

    /* GET /cities/{city}/alerts — recent anomaly alerts            */
    getCityAlerts: function (city, n) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("GET", "/cities/" + encodeURIComponent(slug) + "/alerts?n=" + (n || 10));
    },

    /* GET /cities/{city}/status — model info for a city            */
    getCityStatus: function (city) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("GET", "/cities/" + encodeURIComponent(slug) + "/status");
    },

    /* POST /cities/{city}/train — trigger city model training      */
    trainCityModel: function (city, params) {
      var slug = city.toLowerCase().replace(/ /g, "_");
      return req("POST", "/cities/" + encodeURIComponent(slug) + "/train", params || {});
    },

    /* WebSocket --------------------------------------------------- */
    connectWs: function (channel, onMessage, onError) {
      var token = getToken();
      if (!token) return null;
      var wsBase = BASE.replace(/^http/, "ws");
      var ws;
      try {
        ws = new WebSocket(wsBase + "/ws/" + channel + "?token=" + token);
      } catch (e) {
        console.error("WS connect error:", e);
        return null;
      }
      ws.onmessage = function (e) {
        try { onMessage(JSON.parse(e.data)); }
        catch (err) { onMessage(e.data); }
      };
      ws.onerror = onError || function () {};
      return ws;
    },
  };

  window.API = API;
})();
