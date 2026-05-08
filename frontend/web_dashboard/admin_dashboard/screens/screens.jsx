/**
 * HydroGuard AI — Admin Dashboard Screens
 * Exports: DashboardScreen, MonitoringScreen, CloudburstScreen, FloodScreen,
 *          AnalyticsScreen, CitiesScreen, PredictScreen, SettingsScreen, ProfileScreen
 *
 * City-specific architecture: each screen that needs predictions uses
 * API.cityPredict() / API.getCityRisk() / API.getCitiesOverview() instead of
 * the single global /predict endpoint.
 */
const { useState, useEffect, useCallback, useRef } = React;

// ─── Shared helpers ────────────────────────────────────────────────────────
// Fallback list — used only if the /cities API is unreachable.
// Real list is fetched dynamically and reflects the dataset.
const CITIES_FALLBACK = ["Islamabad","Lahore","Karachi","Peshawar","Quetta","Gilgit"];

// Custom hook: fetches the city list from the backend once and caches it.
function useCityList() {
  const [list, setList] = useState(null);   // null = loading
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    API.getCityList()
      .then(d => { if (alive) setList(d || []); })
      .catch(e => { if (alive) { setError(e.message); setList([]); } });
    return () => { alive = false; };
  }, []);

  return { list, error, names: (list || []).map(c => c.name) };
}

function riskColor(r) {
  if (!r) return "var(--text-muted)";
  const l = r.toLowerCase();
  if (l === "high"   || l === "critical") return "var(--crit)";
  if (l === "medium" || l === "elevated") return "var(--warn)";
  if (l === "low"    || l === "guarded")  return "var(--ok)";
  return "var(--text-muted)";
}

function scoreBar(v, color) {
  const pct = Math.min(Math.max(v * 100, 0), 100).toFixed(0);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--panel-2)", overflow: "hidden" }}>
        <div style={{ width: pct + "%", height: "100%", background: color || "var(--hydro)", borderRadius: 3, transition: "width 0.4s ease" }}/>
      </div>
      <span className="mono-sm">{pct}%</span>
    </div>
  );
}

// ─── DASHBOARD SCREEN ──────────────────────────────────────────────────────
const DashboardScreen = ({ city, cities, liveEvents, onNav }) => {
  const [overview, setOverview] = useState(null);
  const [stats,    setStats]    = useState(null);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      API.getCitiesOverview(),
      API.getDatabaseStats(),
    ]).then(([ov, st]) => {
      if (ov.status === "fulfilled") setOverview(ov.value);
      if (st.status === "fulfilled") setStats(st.value);
      setLoading(false);
    });
  }, []);

  const highRisk  = overview?.high_risk   ?? 0;
  const medRisk   = overview?.medium_risk ?? 0;
  const lowRisk   = overview?.low_risk    ?? 0;
  const total     = overview?.total       ?? CITIES_FALLBACK.length;
  const entries   = overview?.overview    ?? [];

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="page-sub">City-specific hybrid model · Autoencoder + TCN + LightGBM Fusion</div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => onNav("predict")}>
            <Icon name="zap"/>Run prediction
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid g-4 mb-16">
        <KpiCard label="High risk cities"   value={loading ? null : highRisk}
          sub="HRI ≥ 65"          color="var(--crit)"/>
        <KpiCard label="Medium risk cities" value={loading ? null : medRisk}
          sub="HRI 40–65"         color="var(--warn)"/>
        <KpiCard label="Low risk cities"    value={loading ? null : lowRisk}
          sub="HRI < 40"          color="var(--ok)"/>
        <KpiCard label="DB anomaly records" value={loading ? null : (stats?.total_records ?? "—")}
          sub="all time"          color="var(--hydro)"/>
      </div>

      {/* City risk table */}
      <Card label="Risk Overview" title="All cities — current risk assessment" tag="LIVE">
        {loading ? <LoadingState/> : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border)" }}>
                {["City","Province","Risk Level","HRI Score","Anomaly","Source","Rainfall (mm/h)"].map(h => (
                  <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "10px 10px", fontWeight: 600 }}>{e.city}</td>
                  <td style={{ padding: "10px 10px", color: "var(--text-muted)" }}>{e.province ?? "—"}</td>
                  <td style={{ padding: "10px 10px" }}>
                    <span style={{ color: riskColor(e.risk_level), fontWeight: 600 }}>{e.risk_level}</span>
                  </td>
                  <td style={{ padding: "10px 10px" }}>
                    <div>{e.hri_score ?? "—"}</div>
                    <div style={{ marginTop: 4 }}>{scoreBar((e.hri_score ?? 0) / 100, riskColor(e.risk_level))}</div>
                  </td>
                  <td style={{ padding: "10px 10px" }}>
                    <span style={{ color: e.is_anomaly ? "var(--crit)" : "var(--ok)" }}>
                      {e.is_anomaly ? "YES" : "No"}
                    </span>
                  </td>
                  <td style={{ padding: "10px 10px", color: "var(--text-dim)" }}>{e.source ?? "—"}</td>
                  <td style={{ padding: "10px 10px" }}>{e.rainfall_mh ?? "—"}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: "var(--text-dim)" }}>
                  No data available — backend may be starting up
                </td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>

      {/* Recent live events */}
      {liveEvents?.length > 0 && (
        <Card label="Recent Events" title="Latest WebSocket anomaly events" style={{ marginTop: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {liveEvents.slice(0, 6).map((e, i) => (
              <div key={i} className="row" style={{
                background: "var(--panel)", borderRadius: 6, padding: "8px 12px", gap: 12,
                borderLeft: `3px solid ${riskColor(e.risk_level)}`,
              }}>
                <span style={{ fontWeight: 600, minWidth: 90 }}>{e.city}</span>
                <span style={{ color: riskColor(e.risk_level), fontWeight: 600, minWidth: 60 }}>{e.risk_level}</span>
                <span className="mono-sm dim">score {e.anomaly_score?.toFixed(3) ?? "—"}</span>
                <span className="mono-sm dim">HRI {e.hri_score ?? "—"}</span>
                <span className="mono-sm dim" style={{ marginLeft: "auto" }}>
                  {e._ts ? new Date(e._ts).toLocaleTimeString() : "—"}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

// ─── MONITORING SCREEN ─────────────────────────────────────────────────────
const MonitoringScreen = ({ liveEvents }) => {
  const [health,  setHealth]  = useState(null);
  const [terminal,setTerminal]= useState([]);
  const [paused,  setPaused]  = useState(false);
  const [loading, setLoading] = useState(true);
  const termRef = useRef(null);

  useEffect(() => {
    API.health().then(d => { setHealth(d); setLoading(false); }).catch(() => setLoading(false));
    const id = setInterval(() => API.health().then(d => setHealth(d)).catch(() => {}), 30000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (paused || !liveEvents?.length) return;
    const e = liveEvents[0];
    const ts = new Date().toISOString().replace("T"," ").slice(0,23);
    const lvl = e.risk_level === "CRITICAL" ? "CRIT" : e.is_anomaly ? "WARN" : "INFO";
    const line = `[${ts}] ${e.city} score=${e.anomaly_score?.toFixed(3)} risk=${e.risk_level} HRI=${e.hri_score??"-"} AE=${e.ae_score?.toFixed(3)??"—"} LSTM=${e.lstm_score?.toFixed(3)??"—"}`;
    setTerminal(prev => {
      const next = [...prev, { line, lvl }].slice(-100);
      setTimeout(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight; }, 30);
      return next;
    });
  }, [liveEvents, paused]);

  const wsConns = health?.ws_connections ? Object.values(health.ws_connections).reduce((a,b)=>a+b,0) : 0;

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Real-Time Monitoring</h1>
          <div className="page-sub">Live WebSocket feed · <span className="live">STREAMING</span></div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => setPaused(p=>!p)}>
            <Icon name={paused?"play":"pause"}/>{paused?"Resume":"Pause"}
          </button>
          <button className="btn" onClick={() => setTerminal([])}>
            <Icon name="trash"/>Clear
          </button>
        </div>
      </div>

      <div className="grid g-4 mb-16">
        <KpiCard label="API status"     value={loading?null:(health?.status||"unknown")} sub="backend" color="var(--ok)"/>
        <KpiCard label="WS connections" value={loading?null:wsConns} sub="all channels" color="var(--cyan)"/>
        <KpiCard label="Model version"  value={loading?null:(health?.model_version??"—")} sub={health?.model_type||"hybrid"} color="var(--hydro)"/>
        <KpiCard label="Events buffered" value={terminal.length} sub={paused?"paused":"live"} color="var(--ok)"/>
      </div>

      <Card label="Event Terminal" title="WebSocket prediction stream" tag={paused?"PAUSED":"LIVE"}>
        <div ref={termRef} className="mono" style={{
          background:"var(--bg-1)", borderRadius:6, padding:12,
          fontSize:11, lineHeight:1.65, color:"var(--text-muted)",
          maxHeight:500, overflow:"auto",
        }}>
          {terminal.length === 0 && <div style={{color:"var(--text-dim)"}}>Waiting for WebSocket events…</div>}
          {terminal.map((l,i) => (
            <div key={i} style={{color: l.lvl==="CRIT"?"var(--crit)":l.lvl==="WARN"?"var(--warn)":"var(--text-muted)"}}>
              {l.line}
            </div>
          ))}
          {!paused && <div className="row" style={{gap:4,color:"var(--cyan)"}}>
            <span>{">"}</span>
            <span style={{width:6,height:12,background:"var(--cyan)",animation:"pulse 1s infinite"}}/>
          </div>}
        </div>
      </Card>
    </div>
  );
};

// ─── CLOUDBURST SCREEN ─────────────────────────────────────────────────────
const CloudburstScreen = ({ cities, liveEvents }) => {
  const [filter, setFilter] = useState("all");
  const events = (liveEvents || []).filter(e =>
    filter === "all" ? true : e.risk_level?.toLowerCase() === filter
  );

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Cloudburst Detection</h1>
          <div className="page-sub">ML anomaly events · AE + LSTM + Attention per city</div>
        </div>
        <div className="page-actions">
          {["all","high","medium","low"].map(f => (
            <button key={f} className={`btn ${filter===f?"active":""}`} onClick={() => setFilter(f)}>
              {f.charAt(0).toUpperCase()+f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid g-4 mb-16">
        <KpiCard label="Total events"  value={liveEvents?.length??0}  sub="this session" color="var(--hydro)"/>
        <KpiCard label="High risk"     value={(liveEvents||[]).filter(e=>e.risk_level==="High").length}   sub="anomaly confirmed" color="var(--crit)"/>
        <KpiCard label="Medium risk"   value={(liveEvents||[]).filter(e=>e.risk_level==="Medium").length} sub="watch" color="var(--warn)"/>
        <KpiCard label="Low risk"      value={(liveEvents||[]).filter(e=>e.risk_level==="Low").length}    sub="nominal" color="var(--ok)"/>
      </div>

      <Card label="Events" title="Cloudburst / anomaly event log" tag="LIVE">
        {events.length === 0
          ? <div style={{padding:24,textAlign:"center",color:"var(--text-dim)"}}>No events matching filter. Waiting for detections…</div>
          : <div style={{display:"flex",flexDirection:"column",gap:6}}>
              {events.slice(0,30).map((e,i) => (
                <div key={i} style={{
                  background:"var(--panel)", borderRadius:7, padding:"10px 14px",
                  display:"grid", gridTemplateColumns:"110px 80px 80px 80px 80px 1fr auto",
                  gap:12, alignItems:"center", fontSize:12.5,
                  borderLeft:`3px solid ${riskColor(e.risk_level)}`,
                }}>
                  <span style={{fontWeight:600}}>{e.city}</span>
                  <span style={{color:riskColor(e.risk_level),fontWeight:600}}>{e.risk_level}</span>
                  <span className="mono-sm">AE {e.ae_score?.toFixed(3)??"—"}</span>
                  <span className="mono-sm">LSTM {e.lstm_score?.toFixed(3)??"—"}</span>
                  <span className="mono-sm">HRI {e.hri_score??"—"}</span>
                  <span className="mono-sm dim">{e.source??"model"}</span>
                  <span className="mono-sm dim">{e._ts?new Date(e._ts).toLocaleTimeString():"—"}</span>
                </div>
              ))}
            </div>
        }
      </Card>
    </div>
  );
};

// ─── FLOOD RISK SCREEN ─────────────────────────────────────────────────────
const FloodScreen = ({ cities }) => {
  const [overview, setOverview] = useState(null);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    API.getCitiesOverview().then(d => { setOverview(d); setLoading(false); }).catch(() => setLoading(false));
    const id = setInterval(() => API.getCitiesOverview().then(d => setOverview(d)).catch(()=>{}), 60000);
    return () => clearInterval(id);
  }, []);

  const entries = overview?.overview ?? [];

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Flash Flood Risk</h1>
          <div className="page-sub">City-level HRI scores · updated each minute</div>
        </div>
      </div>

      {loading ? <LoadingState/> : (
        <div className="grid g-3 mb-16" style={{"--col-count":"3"}}>
          {entries.map((e, i) => {
            const color = riskColor(e.risk_level);
            return (
              <div key={i} style={{
                background:"var(--panel)", borderRadius:12, padding:"16px 18px",
                borderTop:`3px solid ${color}`,
              }}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
                  <span style={{fontWeight:600,fontSize:14}}>{e.city}</span>
                  <span style={{color,fontWeight:700,fontSize:13}}>{e.risk_level}</span>
                </div>
                <div style={{marginBottom:8}}>
                  {scoreBar((e.hri_score??0)/100, color)}
                </div>
                <div style={{display:"flex",gap:8,fontSize:12,color:"var(--text-muted)"}}>
                  <span>HRI {e.hri_score??0}</span>
                  <span>·</span>
                  <span>{e.is_anomaly?"Anomaly":"Normal"}</span>
                  {e.rainfall_mh != null && <><span>·</span><span>{e.rainfall_mh}mm/h</span></>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ─── ANALYTICS SCREEN ──────────────────────────────────────────────────────
const AnalyticsScreen = () => {
  const { names: cityNames } = useCityList();
  const [analytics, setAnalytics] = useState(null);
  const [dbStats,   setDbStats]   = useState(null);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    Promise.allSettled([API.getAnalytics(), API.getDatabaseStats()])
      .then(([an, db]) => {
        if (an.status==="fulfilled") setAnalytics(an.value);
        if (db.status==="fulfilled") setDbStats(db.value);
        setLoading(false);
      });
  }, []);

  const riskBreakdown = analytics?.alerts_by_risk_level ?? {};
  const topCities     = analytics?.top_cities_by_frequency ?? [];
  const weekCount     = analytics?.anomalies_last_7_days ?? 0;

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Analytics & Reports</h1>
          <div className="page-sub">Aggregated anomaly statistics from all city models</div>
        </div>
      </div>

      {loading ? <LoadingState/> : (
        <>
          <div className="grid g-4 mb-16">
            <KpiCard label="Anomalies (7 days)" value={weekCount}     sub="all cities"      color="var(--crit)"/>
            <KpiCard label="Total DB records"   value={dbStats?.total_records??0} sub="all time" color="var(--hydro)"/>
            <KpiCard label="Cities tracked"     value={cityNames.length || "—"} sub="city-specific AI" color="var(--cyan)"/>
            <KpiCard label="Anomaly rate"        value={dbStats?.anomaly_rate ? (dbStats.anomaly_rate*100).toFixed(1)+"%" : "—"} sub="long-term" color="var(--warn)"/>
          </div>

          <div className="grid g-dash mb-16">
            <Card label="Risk Distribution" title="Alerts by risk level">
              {Object.entries(riskBreakdown).length === 0
                ? <div style={{color:"var(--text-dim)",padding:12}}>No data yet</div>
                : Object.entries(riskBreakdown).map(([lvl, cnt]) => (
                  <div key={lvl} style={{display:"flex",alignItems:"center",gap:12,marginBottom:10}}>
                    <span style={{width:70,fontWeight:600,color:riskColor(lvl)}}>{lvl}</span>
                    <div style={{flex:1}}>{scoreBar(cnt/(Object.values(riskBreakdown).reduce((a,b)=>a+b,1)),riskColor(lvl))}</div>
                    <span className="mono-sm">{cnt}</span>
                  </div>
                ))
              }
            </Card>

            <Card label="Top Cities" title="Most frequent anomaly sources">
              {topCities.length === 0
                ? <div style={{color:"var(--text-dim)",padding:12}}>No data yet</div>
                : topCities.slice(0,8).map((c,i) => (
                  <div key={i} style={{display:"flex",alignItems:"center",gap:12,marginBottom:10}}>
                    <span style={{width:90,fontSize:12.5}}>{c.city}</span>
                    <div style={{flex:1}}>{scoreBar(c.count/(topCities[0].count||1),"var(--hydro)")}</div>
                    <span className="mono-sm">{c.count}</span>
                  </div>
                ))
              }
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

// ─── CITIES SCREEN (City Model Management) ─────────────────────────────────
const CitiesScreen = () => {
  const [cityList,   setCityList]   = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [cityRisk,   setCityRisk]   = useState(null);
  const [cityFc,     setCityFc]     = useState(null);
  const [training,   setTraining]   = useState(false);
  const [trainMsg,   setTrainMsg]   = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [detailLoad, setDetailLoad] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Load city list (dynamic from backend)
  const fetchCities = useCallback(() => {
    setLoading(true);
    return API.getCityList()
      .then(d => {
        const list = d || [];
        setCityList(list);
        if (list.length && !selected) {
          setSelected(list[0].name);
        }
        setLoading(false);
        return list;
      })
      .catch(() => { setLoading(false); return []; });
  }, [selected]);

  useEffect(() => { fetchCities(); }, []); // eslint-disable-line

  // Admin endpoint: rescans the dataset CSV + saved_models for new cities
  const handleRefresh = async () => {
    setRefreshing(true); setTrainMsg(null);
    try {
      const j = await API.refreshCityRegistry();
      setTrainMsg({ ok: true, msg: `Registry refreshed · ${j.total_cities} cities discovered` });
      await fetchCities();
    } catch (err) {
      setTrainMsg({ ok: false, msg: err.message || "Refresh failed" });
    } finally {
      setRefreshing(false);
    }
  };

  // Load city details when selection changes
  useEffect(() => {
    if (!selected) return;
    setDetailLoad(true); setCityRisk(null); setCityFc(null);
    Promise.allSettled([
      API.getCityRisk(selected),
      API.getCityForecast(selected),
    ]).then(([r, f]) => {
      if (r.status==="fulfilled") setCityRisk(r.value);
      if (f.status==="fulfilled") setCityFc(f.value);
      setDetailLoad(false);
    }).catch(() => setDetailLoad(false));
  }, [selected]);

  const handleTrain = async () => {
    if (!selected) return;
    setTraining(true); setTrainMsg(null);
    try {
      const res = await API.trainCityModel(selected, { epochs: 150, use_lstm: true });
      setTrainMsg({ ok: true, msg: res.message || "Training started" });
      // Refresh cities so the badge updates after training completes
      setTimeout(() => fetchCities(), 4000);
    } catch (err) {
      setTrainMsg({ ok: false, msg: err.message || "Training failed" });
    } finally {
      setTraining(false);
    }
  };

  const cityInfo = cityList.find(c => c.name === selected);

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">City Management</h1>
          <div className="page-sub">Per-city hybrid model status · Autoencoder + LSTM + Attention</div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={handleRefresh} disabled={refreshing}>
            <Icon name={refreshing?"spinner":"refresh"}/>{refreshing?"Refreshing…":"Rescan dataset"}
          </button>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"260px 1fr",gap:16,alignItems:"start"}}>
        {/* City list — driven entirely by /cities response */}
        <div style={{background:"var(--panel)",borderRadius:10,overflow:"hidden"}}>
          <div style={{padding:"10px 14px",fontSize:11,fontWeight:600,letterSpacing:"0.08em",
            color:"var(--text-dim)",textTransform:"uppercase",borderBottom:"1px solid var(--border)"}}>
            {loading
              ? "Loading…"
              : `${cityList.length} cities · ${cityList.filter(c=>c.has_model).length} trained`
            }
          </div>
          {!loading && cityList.length === 0 && (
            <div style={{padding:18,fontSize:12.5,color:"var(--text-dim)",lineHeight:1.5}}>
              No cities discovered. Place a CSV with a <code>city</code> column in
              <code style={{display:"block",marginTop:6,fontSize:11.5,padding:"4px 8px",background:"var(--panel-2)",borderRadius:4}}>
                backend/data/
              </code>
              and click "Rescan dataset".
            </div>
          )}
          {cityList.map(c => (
            <div key={c.slug}
              onClick={() => setSelected(c.name)}
              style={{
                display:"flex",alignItems:"center",gap:10,
                padding:"10px 14px",cursor:"pointer",
                background: selected===c.name ? "var(--panel-2)" : "transparent",
                borderLeft: selected===c.name ? "3px solid var(--cyan)" : "3px solid transparent",
                transition:"background 0.1s",
              }}>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontWeight:selected===c.name?600:400,fontSize:13.5}}>{c.name}</div>
                {c.province && c.province !== "—" && (
                  <div style={{fontSize:10.5,color:"var(--text-dim)",marginTop:1}}>{c.province}</div>
                )}
              </div>
              <span style={{
                fontSize:10,fontWeight:600,padding:"2px 7px",borderRadius:100,
                background: c.has_model ? "var(--ok-soft,#dcfce7)"
                          : c.has_data  ? "var(--warn-soft,#fef3c7)"
                          : "var(--panel-3)",
                color:      c.has_model ? "var(--ok)"
                          : c.has_data  ? "#B45309"
                          : "var(--text-dim)",
              }}>
                {c.has_model?"MODEL": c.has_data?"DATA":"—"}
              </span>
            </div>
          ))}
        </div>

        {/* City detail */}
        <div style={{display:"flex",flexDirection:"column",gap:14}}>
          {!selected && !loading && (
            <div style={{background:"var(--panel)",borderRadius:10,padding:"32px 24px",textAlign:"center",color:"var(--text-dim)"}}>
              Select a city from the list to view its model status and forecast.
            </div>
          )}
          {selected && (<>
          {/* Status card */}
          <div style={{background:"var(--panel)",borderRadius:10,padding:"16px 20px"}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
              <div>
                <div style={{fontSize:18,fontWeight:600}}>{selected}</div>
                <div style={{fontSize:12,color:"var(--text-muted)",marginTop:2}}>
                  {cityInfo?.province ?? "—"}
                </div>
              </div>
              <div style={{display:"flex",gap:8,alignItems:"center"}}>
                {cityInfo?.has_model
                  ? <span style={{padding:"4px 12px",borderRadius:100,background:"var(--ok-soft,#dcfce7)",color:"var(--ok)",fontSize:12,fontWeight:600}}>Model trained</span>
                  : <span style={{padding:"4px 12px",borderRadius:100,background:"var(--panel-2)",color:"var(--text-dim)",fontSize:12,fontWeight:600}}>Heuristic fallback</span>
                }
                <button className="btn" onClick={handleTrain} disabled={training}>
                  <Icon name={training?"spinner":"zap"}/>{training?"Training…":"Train model"}
                </button>
              </div>
            </div>
            {trainMsg && (
              <div style={{
                padding:"8px 12px",borderRadius:7,fontSize:12.5,
                background: trainMsg.ok ? "var(--ok-soft,#dcfce7)" : "var(--crit-soft,#fee2e2)",
                color: trainMsg.ok ? "var(--ok)" : "var(--crit)",
                marginBottom:12,
              }}>
                {trainMsg.msg}
              </div>
            )}

            {/* Risk summary */}
            {detailLoad ? <LoadingState/> : cityRisk && (
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginTop:4}}>
                {[
                  {label:"Risk level",  v: cityRisk.risk_level,             c: riskColor(cityRisk.risk_level)},
                  {label:"HRI score",   v: `${cityRisk.hri_score}/100`,     c: "var(--hydro)"},
                  {label:"Anomaly",     v: cityRisk.is_anomaly?"YES":"No",  c: cityRisk.is_anomaly?"var(--crit)":"var(--ok)"},
                  {label:"Source",      v: cityRisk.source??"—",            c: "var(--text-muted)"},
                ].map((m,i) => (
                  <div key={i} style={{background:"var(--panel-2)",borderRadius:8,padding:"10px 12px"}}>
                    <div style={{fontSize:11,color:"var(--text-dim)",marginBottom:4}}>{m.label}</div>
                    <div style={{fontWeight:700,color:m.c}}>{m.v}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Score breakdown */}
          {cityRisk && !detailLoad && (
            <div style={{background:"var(--panel)",borderRadius:10,padding:"16px 20px"}}>
              <div style={{fontSize:12,fontWeight:600,letterSpacing:"0.06em",textTransform:"uppercase",
                color:"var(--text-dim)",marginBottom:12}}>Model scores</div>
              <div style={{display:"flex",flexDirection:"column",gap:10}}>
                {[
                  {label:"Anomaly score",  v:cityRisk.anomaly_score??0, c:"var(--crit)"},
                  {label:"AE score",        v:cityRisk.ae_score??0,      c:"var(--hydro)"},
                  {label:"LSTM score",      v:cityRisk.lstm_score??0,    c:"var(--cyan)"},
                  {label:"Confidence",      v:cityRisk.confidence??0,    c:"var(--ok)"},
                ].map((s,i) => (
                  <div key={i} style={{display:"flex",alignItems:"center",gap:10}}>
                    <span style={{width:110,fontSize:12.5}}>{s.label}</span>
                    <div style={{flex:1}}>{scoreBar(s.v, s.c)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 7-day forecast */}
          {cityFc && !detailLoad && (
            <div style={{background:"var(--panel)",borderRadius:10,padding:"16px 20px"}}>
              <div style={{fontSize:12,fontWeight:600,letterSpacing:"0.06em",textTransform:"uppercase",
                color:"var(--text-dim)",marginBottom:12}}>7-day forecast</div>
              <div style={{display:"flex",gap:8,overflowX:"auto"}}>
                {(cityFc.forecast||[]).map((d,i) => (
                  <div key={i} style={{
                    background:"var(--panel-2)",borderRadius:8,padding:"10px 12px",
                    minWidth:90,textAlign:"center",flexShrink:0,
                    borderTop:`2px solid ${riskColor(d.risk_level)}`,
                  }}>
                    <div style={{fontSize:11,color:"var(--text-dim)"}}>{d.day_name?.slice(0,3)}</div>
                    <div style={{fontSize:11,color:"var(--text-dim)",marginBottom:6}}>{d.date?.slice(5)}</div>
                    <div style={{fontWeight:700,color:riskColor(d.risk_level),fontSize:13}}>{d.risk_level}</div>
                    <div style={{fontSize:11,color:"var(--text-muted)",marginTop:2}}>{d.prcp??0}mm/h</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          </>)}
        </div>
      </div>
    </div>
  );
};

// ─── PREDICT SCREEN ────────────────────────────────────────────────────────
const PredictScreen = () => {
  const { names: cityNames } = useCityList();
  const [city,    setCity]    = useState("");
  const [form,    setForm]    = useState({ prcp:"", humidity:"", pressure:"", tmax:"", tmin:"", cloud_cover:"", dew_point:"", wspd:"" });
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  // Snap to first city as soon as the list loads
  useEffect(() => {
    if (cityNames.length && !city) setCity(cityNames[0]);
    if (cityNames.length && city && !cityNames.includes(city)) setCity(cityNames[0]);
  }, [cityNames]); // eslint-disable-line

  const handleChange = (k, v) => setForm(f => ({...f, [k]: v}));

  const handleSubmit = async () => {
    setLoading(true); setError(null); setResult(null);
    const payload = {};
    Object.entries(form).forEach(([k,v]) => { if (v !== "") payload[k] = parseFloat(v); });
    try {
      const res = await API.cityPredict(city, payload);
      setResult(res);
    } catch (err) {
      setError(err.message || "Prediction failed");
    } finally {
      setLoading(false);
    }
  };

  const fields = [
    {k:"prcp",        label:"Precipitation",   unit:"mm/h", placeholder:"e.g. 45"},
    {k:"humidity",    label:"Humidity",          unit:"%",    placeholder:"e.g. 75"},
    {k:"pressure",    label:"Pressure",          unit:"hPa",  placeholder:"e.g. 1005"},
    {k:"tmax",        label:"Max temperature",   unit:"°C",   placeholder:"e.g. 35"},
    {k:"tmin",        label:"Min temperature",   unit:"°C",   placeholder:"e.g. 22"},
    {k:"cloud_cover", label:"Cloud cover",        unit:"%",    placeholder:"e.g. 80"},
    {k:"dew_point",   label:"Dew point",          unit:"°C",   placeholder:"e.g. 18"},
    {k:"wspd",        label:"Wind speed",         unit:"km/h", placeholder:"e.g. 25"},
  ];

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Run Prediction</h1>
          <div className="page-sub">Submit weather data to the city-specific hybrid model</div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 420px",gap:16,alignItems:"start"}}>
        {/* Form */}
        <div style={{background:"var(--panel)",borderRadius:10,padding:"20px 22px"}}>
          <div style={{marginBottom:16}}>
            <label style={{fontSize:12,color:"var(--text-muted)",display:"block",marginBottom:6}}>
              City <span className="mono-sm dim">({cityNames.length} available)</span>
            </label>
            <select value={city} onChange={e => setCity(e.target.value)} disabled={!cityNames.length}
              style={{background:"var(--panel-2)",color:"var(--text)",border:"1px solid var(--border)",
                borderRadius:7,padding:"8px 12px",fontSize:13.5,width:"100%"}}>
              {cityNames.length === 0 && <option value="">Loading cities…</option>}
              {cityNames.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
            {fields.map(f => (
              <div key={f.k}>
                <label style={{fontSize:12,color:"var(--text-muted)",display:"block",marginBottom:5}}>
                  {f.label} <span className="mono-sm dim">({f.unit})</span>
                </label>
                <input
                  type="number" step="any"
                  placeholder={f.placeholder}
                  value={form[f.k]}
                  onChange={e => handleChange(f.k, e.target.value)}
                  style={{
                    background:"var(--panel-2)", color:"var(--text)",
                    border:"1px solid var(--border)", borderRadius:7,
                    padding:"8px 10px", fontSize:13.5, width:"100%",
                  }}
                />
              </div>
            ))}
          </div>

          <div style={{marginTop:16,display:"flex",gap:10}}>
            <button className="btn btn-primary" onClick={handleSubmit} disabled={loading}
              style={{flex:1,justifyContent:"center",padding:"10px"}}>
              <Icon name={loading?"spinner":"zap"}/>{loading?"Running…":"Run prediction"}
            </button>
            <button className="btn" onClick={() => {setForm({prcp:"",humidity:"",pressure:"",tmax:"",tmin:"",cloud_cover:"",dew_point:"",wspd:""});setResult(null);setError(null);}}>
              Clear
            </button>
          </div>
          {error && <div style={{marginTop:12,padding:"10px 14px",background:"var(--crit-soft,#fee2e2)",color:"var(--crit)",borderRadius:7,fontSize:12.5}}>{error}</div>}
        </div>

        {/* Result */}
        <div style={{background:"var(--panel)",borderRadius:10,padding:"20px 22px"}}>
          <div style={{fontSize:12,fontWeight:600,letterSpacing:"0.07em",textTransform:"uppercase",
            color:"var(--text-dim)",marginBottom:14}}>
            {result ? "Prediction result" : "Result will appear here"}
          </div>

          {!result && !loading && (
            <div style={{textAlign:"center",padding:"32px 0",color:"var(--text-dim)",fontSize:13}}>
              Fill in the form and click "Run prediction"
            </div>
          )}
          {loading && <LoadingState/>}

          {result && (
            <div style={{display:"flex",flexDirection:"column",gap:12}}>
              {/* Risk badge */}
              <div style={{
                textAlign:"center",padding:"20px",borderRadius:10,
                background: result.risk_level==="High" ? "var(--crit-soft,#fee2e2)" :
                            result.risk_level==="Medium" ? "#FEF3C7" : "var(--ok-soft,#dcfce7)",
              }}>
                <div style={{fontSize:11,fontWeight:600,letterSpacing:"0.06em",textTransform:"uppercase",
                  color: riskColor(result.risk_level),marginBottom:4}}>Risk Level</div>
                <div style={{fontSize:32,fontWeight:700,color:riskColor(result.risk_level)}}>
                  {result.risk_level}
                </div>
                <div style={{fontSize:13,color:"var(--text-muted)",marginTop:4}}>
                  HRI {result.hri_score}/100 · Confidence {Math.round((result.confidence??0)*100)}%
                </div>
              </div>

              {/* Score breakdown */}
              <div style={{display:"flex",flexDirection:"column",gap:8}}>
                {[
                  {label:"Anomaly score",  v:result.anomaly_score??0, c:"var(--crit)"},
                  {label:"AE score",        v:result.ae_score??0,      c:"var(--hydro)"},
                  {label:"LSTM score",      v:result.lstm_score??0,    c:"var(--cyan)"},
                  {label:"Confidence",      v:result.confidence??0,    c:"var(--ok)"},
                ].map((s,i)=>(
                  <div key={i} style={{display:"flex",alignItems:"center",gap:10}}>
                    <span style={{width:110,fontSize:12}}>{s.label}</span>
                    <div style={{flex:1}}>{scoreBar(s.v, s.c)}</div>
                  </div>
                ))}
              </div>

              <div style={{fontSize:11,color:"var(--text-dim)",borderTop:"1px solid var(--border)",paddingTop:10}}>
                Model: {result.source??"city_model"} · City: {result.city} · {new Date(result.timestamp||Date.now()).toLocaleTimeString()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── SETTINGS SCREEN ───────────────────────────────────────────────────────
const SettingsScreen = ({ user }) => {
  const [modelInfo, setModelInfo] = useState(null);
  const [health,    setHealth]    = useState(null);
  const [training,  setTraining]  = useState(false);
  const [trainResult, setTrainResult] = useState(null);

  useEffect(() => {
    Promise.allSettled([API.modelInfo(), API.health()])
      .then(([m,h]) => {
        if (m.status==="fulfilled") setModelInfo(m.value);
        if (h.status==="fulfilled") setHealth(h.value);
      });
  }, []);

  const handleTrainGlobal = async () => {
    setTraining(true); setTrainResult(null);
    try {
      const res = await API.triggerTraining({ use_lstm: true, epochs: 150 });
      setTrainResult({ ok: true, msg: res.message || "Global training triggered" });
    } catch (err) {
      setTrainResult({ ok: false, msg: err.message });
    } finally {
      setTraining(false);
    }
  };

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <div className="page-sub">System configuration · model management</div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        {/* Global model */}
        <div style={{background:"var(--panel)",borderRadius:10,padding:"18px 20px"}}>
          <div style={{fontSize:12,fontWeight:600,letterSpacing:"0.07em",textTransform:"uppercase",
            color:"var(--text-dim)",marginBottom:14}}>Global model (fallback)</div>
          {modelInfo ? (
            <div style={{display:"flex",flexDirection:"column",gap:8,fontSize:13}}>
              {[
                {k:"Model type",   v:modelInfo.model_type ?? "hybrid"},
                {k:"Version",      v:modelInfo.version    ?? "—"},
                {k:"Input dim",    v:modelInfo.input_dim  ?? "—"},
                {k:"Threshold",    v:modelInfo.threshold  ?? "—"},
                {k:"Anomaly rate", v:modelInfo.anomaly_rate != null ? (modelInfo.anomaly_rate*100).toFixed(1)+"%" : "—"},
                {k:"Trained at",   v:modelInfo.trained_at  ?? "—"},
              ].map((r,i) => (
                <div key={i} style={{display:"flex",justifyContent:"space-between",borderBottom:"1px solid var(--border)",paddingBottom:6}}>
                  <span style={{color:"var(--text-muted)"}}>{r.k}</span>
                  <span className="mono-sm">{String(r.v)}</span>
                </div>
              ))}
            </div>
          ) : <LoadingState/>}
          <button className="btn btn-primary" style={{marginTop:16,width:"100%",justifyContent:"center"}}
            onClick={handleTrainGlobal} disabled={training}>
            <Icon name={training?"spinner":"zap"}/>{training?"Training…":"Retrain global model"}
          </button>
          {trainResult && (
            <div style={{marginTop:10,padding:"8px 12px",borderRadius:7,fontSize:12.5,
              background: trainResult.ok?"var(--ok-soft,#dcfce7)":"var(--crit-soft,#fee2e2)",
              color: trainResult.ok?"var(--ok)":"var(--crit)"}}>
              {trainResult.msg}
            </div>
          )}
        </div>

        {/* System health */}
        <div style={{background:"var(--panel)",borderRadius:10,padding:"18px 20px"}}>
          <div style={{fontSize:12,fontWeight:600,letterSpacing:"0.07em",textTransform:"uppercase",
            color:"var(--text-dim)",marginBottom:14}}>System health</div>
          {health ? (
            <div style={{display:"flex",flexDirection:"column",gap:8,fontSize:13}}>
              {[
                {k:"Status",      v:health.status,       c: health.status==="healthy"?"var(--ok)":"var(--warn)"},
                {k:"Model loaded",v:health.model_loaded?"Yes":"No", c:"var(--text)"},
                {k:"DB records",  v:health.total_records??0, c:"var(--text)"},
                {k:"Uptime",      v:health.uptime??"—",   c:"var(--text)"},
              ].map((r,i) => (
                <div key={i} style={{display:"flex",justifyContent:"space-between",borderBottom:"1px solid var(--border)",paddingBottom:6}}>
                  <span style={{color:"var(--text-muted)"}}>{r.k}</span>
                  <span style={{color:r.c,fontWeight:600,fontSize:12}}>{String(r.v)}</span>
                </div>
              ))}
            </div>
          ) : <LoadingState/>}
          <a href={API.BASE+"/docs"} target="_blank" rel="noopener">
            <button className="btn" style={{marginTop:16,width:"100%",justifyContent:"center"}}>
              <Icon name="externalLink"/>Open API docs
            </button>
          </a>
        </div>
      </div>
    </div>
  );
};

// ─── PROFILE SCREEN ────────────────────────────────────────────────────────
const ProfileScreen = ({ user }) => (
  <div className="screen">
    <div className="page-head">
      <div><h1 className="page-title">Profile</h1></div>
    </div>
    <div style={{background:"var(--panel)",borderRadius:10,padding:"24px 28px",maxWidth:440}}>
      <div style={{display:"flex",alignItems:"center",gap:16,marginBottom:24}}>
        <div style={{width:56,height:56,borderRadius:"50%",
          background:"linear-gradient(135deg,var(--hydro),var(--cyan))",
          display:"grid",placeItems:"center",color:"white",fontSize:20,fontWeight:600}}>
          {user?.username?.slice(0,2).toUpperCase()||"HG"}
        </div>
        <div>
          <div style={{fontSize:17,fontWeight:600}}>{user?.username||"—"}</div>
          <div style={{fontSize:12.5,color:"var(--text-muted)"}}>{user?.email||"—"}</div>
        </div>
      </div>
      {[
        {k:"Role",          v:user?.role||"—"},
        {k:"Account status",v:user?.is_active?"Active":"Inactive"},
        {k:"Last login",    v:user?.last_login ? new Date(user.last_login).toLocaleString() : "—"},
      ].map((r,i) => (
        <div key={i} style={{display:"flex",justifyContent:"space-between",
          borderBottom:"1px solid var(--border)",padding:"10px 0",fontSize:13}}>
          <span style={{color:"var(--text-muted)"}}>{r.k}</span>
          <span style={{fontWeight:500}}>{r.v}</span>
        </div>
      ))}
    </div>
  </div>
);

// Export all
window._setCities = function() {}; // placeholder for loadCities hook
Object.assign(window, {
  DashboardScreen, MonitoringScreen, CloudburstScreen, FloodScreen,
  AnalyticsScreen, CitiesScreen, PredictScreen, SettingsScreen, ProfileScreen,
});
