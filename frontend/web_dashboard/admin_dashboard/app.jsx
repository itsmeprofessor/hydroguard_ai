// HydroGuard AI — Root App Shell
// Auth flow, sidebar, topbar, WebSocket management, city state.
const { useState, useEffect, useRef, useCallback } = React;

// ── City-coordinate lookup for the Pakistan map SVG ───────────────────────
const CITY_SVG_MAP = {
  "Islamabad":  { id: "isb", lat: "33.68°N", lng: "73.04°E", pop: "1.1M" },
  "Rawalpindi": { id: "rwp", lat: "33.56°N", lng: "73.01°E", pop: "2.1M" },
  "Lahore":     { id: "lhr", lat: "31.52°N", lng: "74.36°E", pop: "13.1M" },
  "Karachi":    { id: "khi", lat: "24.86°N", lng: "67.00°E", pop: "16.9M" },
  "Peshawar":   { id: "pew", lat: "34.02°N", lng: "71.58°E", pop: "2.0M" },
  "Quetta":     { id: "que", lat: "30.18°N", lng: "66.99°E", pop: "1.0M" },
  "Multan":     { id: "mul", lat: "30.19°N", lng: "71.47°E", pop: "1.9M" },
  "Faisalabad": { id: "fsd", lat: "31.42°N", lng: "73.08°E", pop: "3.2M" },
  "Hyderabad":  { id: "hyd", lat: "25.39°N", lng: "68.37°E", pop: "1.7M" },
  "Gilgit":     { id: "gil", lat: "35.92°N", lng: "74.31°E", pop: "0.3M" },
};
const RISK_VIZ = { "LOW": "low", "MEDIUM": "med", "HIGH": "high", "CRITICAL": "crit" };

function mapApiCities(entries) {
  return (entries || []).map(e => {
    const svg = CITY_SVG_MAP[e.city] || { id: e.city.slice(0, 3).toLowerCase(), lat: `${e.latitude}°N`, lng: `${e.longitude}°E`, pop: "?" };
    return {
      ...svg,
      name:       e.city,
      region:     e.region,
      risk:       RISK_VIZ[e.risk_level] || "low",
      rainfall:   e.hri_score || 0,
      hri_score:  e.hri_score,
      hri_label:  e.hri_label,
      risk_level: e.risk_level,
    };
  });
}

// ── Navigation definition ─────────────────────────────────────────────────
const NAV = [
  { group: "Operations", items: [
    { k: "dashboard",  label: "Dashboard",           icon: "dashboard"  },
    { k: "monitoring", label: "Real-time monitoring", icon: "monitor"    },
    { k: "cloudburst", label: "Cloudburst detection", icon: "cloudburst" },
    { k: "flood",      label: "Flash flood risk",     icon: "flood"      },
  ]},
  { group: "Intelligence", items: [
    { k: "analytics",  label: "Analytics & reports",  icon: "analytics"  },
    { k: "cities",     label: "City management",       icon: "city"       },
    { k: "predict",    label: "Run prediction",        icon: "zap"        },
  ]},
  { group: "System", items: [
    { k: "settings",   label: "Settings",              icon: "settings"   },
    { k: "profile",    label: "Profile",               icon: "user"       },
  ]},
];

// ── Sidebar ───────────────────────────────────────────────────────────────
const Sidebar = ({ current, onNav, onLogout, user, critCount }) => (
  <aside className="sidebar">
    <div className="brand">
      <div className="brand-mark"><BrandMark size={18}/></div>
      <div style={{ minWidth: 0 }}>
        <div className="brand-text">
          HydroGuard <span style={{ color: "var(--cyan)" }}>AI</span>
        </div>
        <div className="brand-sub">v3.0 · prod</div>
      </div>
    </div>

    {NAV.map(g => (
      <div key={g.group} className="nav-section">
        <div className="nav-title">{g.group}</div>
        {g.items.map(it => (
          <div key={it.k}
            className={`nav-item ${current === it.k ? "active" : ""}`}
            onClick={() => onNav(it.k)}>
            <Icon name={it.icon}/>
            <span>{it.label}</span>
            {it.k === "cloudburst" && critCount > 0 && (
              <span className="badge">{critCount}</span>
            )}
          </div>
        ))}
      </div>
    ))}

    <div className="sidebar-footer">
      <div className="avatar">
        {user ? user.username.slice(0, 2).toUpperCase() : "HG"}
      </div>
      <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
        <div style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {user?.username || "Loading…"}
        </div>
        <div className="mono-sm dim">{user?.role || "—"}</div>
      </div>
      <button className="iconbtn" onClick={onLogout} title="Sign out">
        <Icon name="logout"/>
      </button>
    </div>
  </aside>
);

// ── City switcher dropdown ─────────────────────────────────────────────────
const CitySwitcher = ({ city, cities, onSelect }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="city-switcher" onClick={() => setOpen(o => !o)}>
      <svg className="city-mini-map" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.6">
        <path d="M4 6v12l5-2 6 2 5-2V4l-5 2-6-2-5 2z"/>
        <path d="M9 4v14M15 6v14"/>
      </svg>
      <div className="meta">
        <span>{city ? city.name : "Select city"}</span>
        <span>{city ? `${city.lat} · ${city.lng}` : "—"}</span>
      </div>
      <Icon name="chevronDown" size={13}/>
      {open && (
        <div className="city-menu" onClick={e => e.stopPropagation()}>
          {cities.length === 0 && (
            <div style={{ padding: "10px 8px" }} className="mono-sm dim">Loading cities…</div>
          )}
          {cities.map(c => (
            <div key={c.id} className={`city-menu-item risk-${c.risk}`}
              onClick={() => { onSelect(c.id); setOpen(false); }}>
              <span className="name">{c.name}</span>
              <span className="sub">HRI {c.hri_score ?? "—"} · {c.risk_level || c.risk.toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Topbar ────────────────────────────────────────────────────────────────
const Topbar = ({ current, city, cities, onCity, theme, onTheme, wsConnected, critCount }) => {
  const TITLES = {
    dashboard:  "Dashboard",           monitoring: "Real-time monitoring",
    cloudburst: "Cloudburst detection",flood:      "Flash flood risk",
    analytics:  "Analytics & reports", cities:     "City management",
    predict:    "Run prediction",      settings:   "Settings",
    profile:    "Profile",
  };
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const i = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(i);
  }, []);
  const timeStr = time.toTimeString().slice(0, 8) + " PKT";

  return (
    <div className="topbar">
      <CitySwitcher city={city} cities={cities} onSelect={onCity}/>
      <div className="breadcrumb">
        <span>HydroGuard</span>
        <Icon name="chevron" size={12}/>
        <strong>{TITLES[current] || current}</strong>
      </div>

      {critCount > 0
        ? <Chip kind="crit"><span>{critCount} CRITICAL · NATIONAL</span></Chip>
        : <Chip kind="warn"><span>MONITORING</span></Chip>}

      <Chip kind={wsConnected ? "ok" : "warn"}>
        <span>{wsConnected ? "WS LIVE" : "WS OFF"}</span>
      </Chip>

      <span className="mono-sm dim" style={{ fontSize: 11 }}>{timeStr}</span>
      <div className="spacer"/>

      <button className="iconbtn"
        onClick={() => onTheme(theme === "dark" ? "light" : "dark")}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
        <Icon name="eye"/>
      </button>

      <a href={API.BASE + "/docs"} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
        <button className="iconbtn" title="API docs">
          <Icon name="externalLink"/>
        </button>
      </a>
    </div>
  );
};

// ── Root App ──────────────────────────────────────────────────────────────
const App = () => {
  // ── view state: "loading" | "landing" | "auth" | "app"
  const [view,    setView]    = useState("loading");
  const [current, setCurrent] = useState(() => localStorage.getItem("hg-screen") || "dashboard");
  const [cityId,  setCityId]  = useState(() => localStorage.getItem("hg-city")   || "isb");
  const [theme,   setTheme]   = useState(() => localStorage.getItem("hg-theme")  || "dark");

  const [user,        setUser]        = useState(null);
  const [cities,      setCities]      = useState([]);
  const [critCount,   setCritCount]   = useState(0);
  const [alertFiring, setAlertFiring] = useState(false);
  const [liveEvents,  setLiveEvents]  = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

  const wsRef        = useRef(null);
  const wsReconnectRef = useRef(null);

  // ── Persist preferences ──────────────────────────────────────────────────
  useEffect(() => { localStorage.setItem("hg-screen", current); }, [current]);
  useEffect(() => { localStorage.setItem("hg-city",   cityId);  }, [cityId]);
  useEffect(() => {
    localStorage.setItem("hg-theme", theme);
    document.body.className = theme === "light" ? "theme-light" : "";
  }, [theme]);

  // ── Load risk-map → cities array ─────────────────────────────────────────
  const loadCities = useCallback(async () => {
    try {
      const data = await API.getRiskMap();
      const mapped = mapApiCities(data.entries || []);
      setCities(mapped);
      window._setCities(data.entries || []);
      const cc = mapped.filter(c => c.risk === "crit").length;
      setCritCount(cc);
      if (cc > 0) setAlertFiring(true);
    } catch (e) {
      console.warn("Risk-map unavailable:", e.message);
    }
  }, []);

  // ── WebSocket connection ──────────────────────────────────────────────────
  const connectWs = useCallback(() => {
    clearTimeout(wsReconnectRef.current);
    if (wsRef.current) { try { wsRef.current.close(); } catch {} }

    const ws = API.connectWs("anomalies",
      (data) => {
        setLiveEvents(prev => [{ ...data, _ts: Date.now() }, ...prev].slice(0, 200));
        if (data.risk_level === "CRITICAL" || data.is_anomaly) {
          setAlertFiring(true);
          setCritCount(c => c + 1);
        }
        window.dispatchEvent(new CustomEvent("hg:anomaly", { detail: data }));
      },
      () => { setWsConnected(false); }
    );

    if (ws) {
      ws.onopen  = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        wsReconnectRef.current = setTimeout(connectWs, 4000);
      };
      wsRef.current = ws;
    }
  }, []);

  // ── Bootstrap: check existing session ───────────────────────────────────
  useEffect(() => {
    const onUnauth = () => handleLogout();
    window.addEventListener("hg:unauthorized", onUnauth);

    if (API.isLoggedIn()) {
      API.me()
        .then(u => {
          setUser(u);
          setView("app");
          loadCities();
        })
        .catch(() => { API.clearTokens(); setView("auth"); });
    } else {
      setView("landing");
    }

    return () => {
      window.removeEventListener("hg:unauthorized", onUnauth);
    };
  }, []); // eslint-disable-line

  // ── Start WS + auto-refresh when app view mounts ────────────────────────
  useEffect(() => {
    if (view !== "app") return;
    connectWs();
    const poll = setInterval(loadCities, 60000);
    return () => {
      clearInterval(poll);
      clearTimeout(wsReconnectRef.current);
      if (wsRef.current) { try { wsRef.current.close(); } catch {} }
    };
  }, [view, connectWs, loadCities]);

  // ── Auth handlers ────────────────────────────────────────────────────────
  const handleLogin = async (email, password, username, role) => {
    if (username) {
      // Register path
      await API.register(email, username, password, role || "USER");
    } else {
      await API.login(email, password);
    }
    const me = await API.me();
    setUser(me);
    setView("app");
    await loadCities();
  };

  const handleLogout = async () => {
    clearTimeout(wsReconnectRef.current);
    if (wsRef.current) { try { wsRef.current.close(); } catch {} }
    setWsConnected(false);
    await API.logout();
    setUser(null);
    setCities([]);
    setAlertFiring(false);
    setCritCount(0);
    setLiveEvents([]);
    setView("landing");
  };

  // ── Derived state ────────────────────────────────────────────────────────
  const city = cities.find(c => c.id === cityId) || cities[0] || null;

  const navTo = (k) => {
    setCurrent(k);
    window.scrollTo(0, 0);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  if (view === "loading") {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "var(--bg)" }}>
        <div style={{ textAlign: "center" }}>
          <Spinner size={40}/>
          <div className="mono-sm dim mt-16" style={{ fontSize: 12 }}>Authenticating…</div>
        </div>
      </div>
    );
  }

  if (view === "landing") return <LandingScreen onEnter={() => setView("auth")}/>;

  if (view === "auth") return (
    <AuthScreen
      onLogin={handleLogin}
      onBack={() => setView("landing")}
    />
  );

  // Shared props passed to every screen
  const screenProps = {
    city, cities, alertFiring, liveEvents, user, onNav: navTo,
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <Sidebar
        current={current}
        onNav={navTo}
        onLogout={handleLogout}
        user={user}
        critCount={critCount}
      />

      {/* Right pane */}
      <div style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
        <Topbar
          current={current}
          city={city}
          cities={cities}
          onCity={id => setCityId(id)}
          theme={theme}
          onTheme={setTheme}
          wsConnected={wsConnected}
          critCount={critCount}
        />

        {/* Global critical banner */}
        {alertFiring && critCount > 0 && (
          <div className="crit-banner">
            <div className="icon"><Icon name="alert" size={20}/></div>
            <div>
              <div className="title">
                {critCount} CITY{critCount !== 1 ? "IES" : ""} AT CRITICAL RISK
              </div>
              <div className="sub">
                HRI ≥ 76 · Cloudburst/flash-flood protocols may apply
              </div>
            </div>
            <div className="spacer"/>
            <button className="btn btn-danger" onClick={() => navTo("cloudburst")}>
              <Icon name="zap"/>View events
            </button>
            <button className="btn"
              style={{ background: "transparent", borderColor: "oklch(1 0 0 / 0.25)", color: "white" }}
              onClick={() => { setAlertFiring(false); setCritCount(0); }}>
              Dismiss
            </button>
          </div>
        )}

        {/* Screen router */}
        <div className="main">
          {current === "dashboard"  && <DashboardScreen  {...screenProps}/>}
          {current === "monitoring" && <MonitoringScreen  {...screenProps}/>}
          {current === "cloudburst" && <CloudburstScreen  {...screenProps}/>}
          {current === "flood"      && <FloodScreen       {...screenProps}/>}
          {current === "analytics"  && <AnalyticsScreen   {...screenProps}/>}
          {current === "cities"     && <CitiesScreen      {...screenProps}/>}
          {current === "predict"    && <PredictScreen     {...screenProps}/>}
          {current === "settings"   && <SettingsScreen    {...screenProps}/>}
          {current === "profile"    && <ProfileScreen     {...screenProps}/>}
        </div>
      </div>

      {/* Toast notifications */}
      <ToastContainer/>
    </div>
  );
};

// ── Boot ─────────────────────────────────────────────────────────────────
ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
