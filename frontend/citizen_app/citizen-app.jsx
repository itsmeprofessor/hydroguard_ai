/**
 * HydroGuard — Citizen App Root
 * Web-first, responsive, connected to HydroAPI backend.
 *
 * Layout:
 *   ┌───────────────────────────────────────────────────────┐
 *   │ TopBar: Logo + City selector + Theme toggle + Status  │
 *   ├──────────┬────────────────────────────────────────────┤
 *   │ Sidebar  │  Screen content (max-width centred card)   │
 *   │ nav      │                                            │
 *   │ (≥768px) │                                            │
 *   └──────────┴────────────────────────────────────────────┘
 *   Bottom tab bar on mobile (<768 px)
 */

const { useState, useEffect, useCallback, useRef } = React;

const NAV_ITEMS = [
  { k: "home",     icon: "home",     label: "Home"     },
  { k: "forecast", icon: "forecast", label: "Forecast" },
  { k: "alerts",   icon: "bell",     label: "Alerts"   },
  { k: "learn",    icon: "learn",    label: "Learn"    },
  { k: "settings", icon: "gear",     label: "Settings" },
];

// Fallback list — used only if the /cities API is unreachable on first load.
// In production, the city list is fetched dynamically and reflects whatever
// cities exist in the backend dataset.
const CITIES_FALLBACK = ["Islamabad", "Lahore", "Karachi", "Peshawar", "Quetta", "Gilgit"];

// ─── Brand mark ──────────────────────────────────────────────────────────────
const BrandMark = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
    <rect width="40" height="40" rx="10" fill="url(#bmGrad)"/>
    <path d="M20 8 C20 8 28 18 28 24 C28 28.4 24.4 32 20 32 C15.6 32 12 28.4 12 24 C12 18 20 8 20 8Z"
      fill="white" opacity="0.95"/>
    <defs>
      <linearGradient id="bmGrad" x1="0" y1="0" x2="40" y2="40">
        <stop offset="0%" stopColor="#2563EB"/>
        <stop offset="100%" stopColor="#0891B2"/>
      </linearGradient>
    </defs>
  </svg>
);

// ─── Status dot ───────────────────────────────────────────────────────────────
const StatusDot = ({ online }) => (
  <span style={{
    width: 7, height: 7, borderRadius: "50%",
    background: online ? "var(--c-ok)" : "#9AA4B2",
    display: "inline-block", marginRight: 5,
    boxShadow: online ? "0 0 0 3px var(--c-ok-soft)" : "none",
  }}/>
);

// ─── City selector dropdown ───────────────────────────────────────────────────
const CitySelector = ({ city, cities, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const list = cities && cities.length ? cities : CITIES_FALLBACK;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="city-selector-btn" onClick={() => setOpen(o => !o)}>
        <CIcon name="pin" size={14}/>
        {city}
        <CIcon name="chevronDown" size={14}/>
      </button>
      {open && (
        <div className="city-dropdown">
          {list.map(c => (
            <button key={c} className={`city-option ${c === city ? "on" : ""}`}
              onClick={() => { onChange(c); setOpen(false); }}>
              {c === city && <CIcon name="check" size={13}/>}
              {c}
            </button>
          ))}
          {list.length === 0 && (
            <div style={{ padding: "12px 16px", fontSize: 12, color: "var(--c-muted)" }}>
              No cities available. The dataset may be empty.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Top bar ──────────────────────────────────────────────────────────────────
const TopBar = ({ city, cities, onCityChange, theme, onTheme, online, tab, onTab }) => (
  <header className="topbar">
    <div className="topbar-left">
      <BrandMark size={30}/>
      <div className="topbar-brand">
        <span className="brand-name-text">HydroGuard</span>
        <span style={{ color: "var(--c-blue)", fontWeight: 600 }}> AI</span>
      </div>
    </div>

    <div className="topbar-center">
      <CitySelector city={city} cities={cities} onChange={onCityChange}/>
    </div>

    <div className="topbar-right">
      <div className="online-badge">
        <StatusDot online={online}/>
        <span>{online ? "Live" : "Offline"}</span>
      </div>
      <button className="theme-btn" onClick={onTheme} title="Toggle theme">
        <CIcon name={theme === "dark" ? "sun" : "moon"} size={16}/>
      </button>
    </div>

    {/* Desktop nav tabs inside top bar */}
    <nav className="topbar-nav">
      {NAV_ITEMS.map(n => (
        <button key={n.k} className={`topbar-nav-item ${tab === n.k ? "active" : ""}`} onClick={() => onTab(n.k)}>
          <CIcon name={n.icon} size={16}/>
          <span>{n.label}</span>
        </button>
      ))}
    </nav>
  </header>
);

// ─── Bottom tab bar (mobile) ──────────────────────────────────────────────────
const BottomTabBar = ({ tab, onTab, dark, hasAlert }) => (
  <nav className={`citizen-tab-bar ${dark ? "dark" : ""}`}>
    {NAV_ITEMS.map(n => (
      <button key={n.k} className={`tab-btn ${tab === n.k ? "on" : ""}`} onClick={() => onTab(n.k)}>
        <span style={{ position: "relative" }}>
          <CIcon name={n.icon} size={22} stroke={tab === n.k ? 2.2 : 1.8}/>
          {n.k === "alerts" && hasAlert && (
            <span style={{ position: "absolute", top: -2, right: -4, width: 8, height: 8, borderRadius: "50%", background: "var(--c-crit)", border: "2px solid white" }}/>
          )}
        </span>
        <span>{n.label}</span>
      </button>
    ))}
  </nav>
);

// ─── Toast notification ───────────────────────────────────────────────────────
const Toast = ({ msg, kind = "ok" }) => (
  <div className={`citizen-toast ${kind}`}>
    <CIcon name={kind === "crit" ? "alert" : kind === "warn" ? "alert" : "check"} size={16}/>
    {msg}
  </div>
);

// ─── Refresh button ───────────────────────────────────────────────────────────
const RefreshBtn = ({ loading, onRefresh }) => (
  <button className="refresh-btn" onClick={onRefresh} disabled={loading}
    title="Refresh data">
    <CIcon name={loading ? "droplet" : "forecast"} size={16}/>
    {loading ? "Updating…" : "Refresh"}
  </button>
);

// ─── Root App ─────────────────────────────────────────────────────────────────
const App = () => {
  const [tab,      setTab]      = useState(() => localStorage.getItem("hg-tab")     || "home");
  const [city,     setCity]     = useState(() => localStorage.getItem("hg-city")    || "Islamabad");
  const [theme,    setTheme]    = useState(() => localStorage.getItem("hg-theme")   || "light");
  const [prefs,    setPrefsRaw] = useState(() => {
    try { return JSON.parse(localStorage.getItem("hg-prefs") || "{}"); }
    catch { return {}; }
  });

  // Dynamic city list — fetched from /cities at startup
  const [cityList, setCityList] = useState([]);

  // Data state
  const [riskData,  setRiskData]  = useState(null);
  const [forecast,  setForecast]  = useState(null);
  const [alerts,    setAlerts]    = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [online,    setOnline]    = useState(true);
  const [toast,     setToast]     = useState(null);
  const [lastCity,  setLastCity]  = useState(null);

  const setPrefs = (patch) => {
    setPrefsRaw(prev => {
      const next = { ...prev, ...patch };
      localStorage.setItem("hg-prefs", JSON.stringify(next));
      return next;
    });
  };

  // Persist tab + city + theme
  useEffect(() => { localStorage.setItem("hg-tab",   tab);   }, [tab]);
  useEffect(() => { localStorage.setItem("hg-city",  city);  }, [city]);
  useEffect(() => {
    localStorage.setItem("hg-theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
    document.body.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // Sync city from settings prefs
  useEffect(() => {
    if (prefs.city && prefs.city !== city) setCity(prefs.city);
  }, [prefs.city]);

  // Fetch the dynamic city list from /cities once at startup.
  // If the saved city no longer exists in the dataset, snap to the first one.
  useEffect(() => {
    HydroAPI.getCities()
      .then(list => {
        const names = (list || []).map(c => c.name);
        if (names.length === 0) {
          setCityList(CITIES_FALLBACK);
          return;
        }
        setCityList(names);
        if (!names.includes(city)) {
          setCity(names[0]);
        }
      })
      .catch(err => {
        console.warn("Could not fetch city list:", err);
        setCityList(CITIES_FALLBACK);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Fetch data ──────────────────────────────────────────────────────────────
  const fetchAll = useCallback(async (cityName) => {
    setLoading(true);
    setOnline(true);
    try {
      const [risk, fc, al] = await Promise.allSettled([
        HydroAPI.getCityRisk(cityName),
        HydroAPI.getForecast(cityName),
        HydroAPI.getAlerts(cityName, 8),
      ]);

      if (risk.status === "fulfilled")     setRiskData(risk.value);
      else                                 console.warn("Risk fetch failed:", risk.reason);

      if (fc.status === "fulfilled")       setForecast(fc.value);
      else                                 console.warn("Forecast fetch failed:", fc.reason);

      if (al.status === "fulfilled")       setAlerts(al.value);
      else                                 console.warn("Alerts fetch failed:", al.reason);

      if (risk.status === "rejected" && fc.status === "rejected") {
        setOnline(false);
        showToast("Could not reach server. Showing cached data.", "warn");
      }
    } catch (err) {
      setOnline(false);
      showToast("Network error — please check your connection.", "crit");
    } finally {
      setLoading(false);
      setLastCity(cityName);
    }
  }, []);

  // Fetch on mount + city change
  useEffect(() => {
    if (city !== lastCity) {
      HydroAPI.clearCache();
      fetchAll(city);
    }
  }, [city, fetchAll]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const id = setInterval(() => fetchAll(city), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [city, fetchAll]);

  const showToast = (msg, kind = "ok") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  const handleRefresh = () => {
    HydroAPI.clearCache();
    fetchAll(city);
    showToast("Refreshing data…", "ok");
  };

  const hasAlert = (alerts?.count ?? 0) > 0
    || (riskData?.risk_level && riskData.risk_level !== "Low");

  const dark = theme === "dark";
  const scenario = riskToScenario(riskData?.risk_level);

  return (
    <div className={`hg-app ${dark ? "dark" : ""}`}>
      <TopBar
        city={city} cities={cityList}
        onCityChange={(c) => { setCity(c); setPrefs({ city: c }); }}
        theme={theme} onTheme={() => setTheme(t => t === "dark" ? "light" : "dark")}
        online={online} tab={tab} onTab={setTab}
      />

      <main className="hg-main">
        {/* Content pane */}
        <div className={`hg-content ${dark ? "dark" : ""}`}>
          {/* Page header (above screen content) */}
          <div className="page-header">
            <div>
              <div className="page-city">{city}</div>
              <div className="page-sub">
                {loading ? "Updating…" : `Last update: ${riskData?.timestamp ? new Date(riskData.timestamp).toLocaleTimeString() : "—"}`}
              </div>
            </div>
            <RefreshBtn loading={loading} onRefresh={handleRefresh}/>
          </div>

          {/* Risk badge strip (only on home) */}
          {tab === "home" && !loading && riskData && (
            <div className={`risk-strip ${scenario}`}>
              <span className="dot"/>
              <span>{riskData.risk_level} risk</span>
              <span className="sep">·</span>
              <span>HRI {riskData.hri_score}/100</span>
              <span className="sep">·</span>
              <span>Confidence {Math.round((riskData.confidence ?? 0) * 100)}%</span>
              {riskData.source === "heuristic" && (
                <><span className="sep">·</span><span className="badge">Rule-based</span></>
              )}
            </div>
          )}

          {/* ── Screens ── */}
          {tab === "home" && (
            <HomeScreen riskData={riskData} forecast={forecast} loading={loading} onTab={setTab} city={city}/>
          )}
          {tab === "forecast" && (
            <ForecastScreen forecast={forecast} riskData={riskData} loading={loading} city={city}/>
          )}
          {tab === "alerts" && (
            <AlertsScreen alerts={alerts} riskData={riskData} loading={loading} city={city}/>
          )}
          {tab === "learn" && (
            <LearnScreen/>
          )}
          {tab === "settings" && (
            <SettingsScreen
              prefs={{ ...prefs, city, theme }}
              setPrefs={(patch) => {
                setPrefs(patch);
                if (patch.theme)  setTheme(patch.theme);
                if (patch.city)   setCity(patch.city);
              }}
              scenario={scenario}
            />
          )}
        </div>
      </main>

      {/* Mobile bottom nav */}
      <BottomTabBar tab={tab} onTab={setTab} dark={dark} hasAlert={hasAlert}/>

      {/* Toast */}
      {toast && <Toast msg={toast.msg} kind={toast.kind}/>}
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
