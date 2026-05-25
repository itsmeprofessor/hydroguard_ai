// HydroGuard AI — Monitoring, Analytics, Cities, Predict, Settings, Profile screens
const { useState, useEffect, useCallback, useRef } = React;

// ── Real-time Monitoring Screen ────────────────────────────────────────────
const MonitoringScreen = ({ liveEvents, cityHealth }) => {
  const [health,    setHealth]    = useState(null);
  const [terminal,  setTerminal]  = useState([]);
  const [paused,    setPaused]    = useState(false);
  const [loading,   setLoading]   = useState(true);
  const termRef = useRef(null);

  useEffect(() => {
    API.health().then(d => { setHealth(d); setLoading(false); }).catch(() => setLoading(false));
    const interval = setInterval(() => {
      API.health().then(d => setHealth(d)).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Feed live events into terminal
  useEffect(() => {
    if (paused || !liveEvents.length) return;
    const e = liveEvents[0];
    const ts = new Date().toISOString().replace("T", " ").slice(0, 23);
    // Support v2 (risk_band, event_probability, is_alert) and v1 (risk_level, anomaly_score, is_anomaly)
    const band = e.risk_band || e.risk_level || "Low";
    const prob = e.event_probability ?? e.anomaly_score;
    const alerting = e.is_alert ?? e.is_anomaly ?? false;
    const lvl  = band === "High" || band === "CRITICAL" ? "CRIT" : alerting ? "WARN" : "INFO";
    const line = `[${ts}] ${e.city || e.city_slug} · prob=${prob != null ? prob.toFixed(3) : "—"} risk_band=${band} HRI=${e.hri_score ?? "—"} source=${e.source || "—"}`;
    setTerminal(prev => {
      const next = [...prev, { line, lvl }].slice(-80);
      // auto-scroll
      setTimeout(() => {
        if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
      }, 30);
      return next;
    });
  }, [liveEvents, paused]);

  const wsConns = health?.ws_connections
    ? Object.values(health.ws_connections).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Real-Time Monitoring</h1>
          <div className="page-sub">
            Live WebSocket feed · <span className="live">STREAMING</span>
          </div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => setPaused(p => !p)}>
            <Icon name={paused ? "play" : "pause"}/>{paused ? "Resume" : "Pause stream"}
          </button>
          <button className="btn" onClick={() => setTerminal([])}>
            <Icon name="trash"/>Clear log
          </button>
        </div>
      </div>

      <div className="grid g-4 mb-16">
        <KpiCard label="API status" value={loading ? null : health?.status || "unknown"}
          sub={`model ${health?.model_loaded ? "loaded" : "not loaded"}`}
          color={health?.status === "healthy" ? "var(--ok)" : "var(--warn)"}/>
        <KpiCard label="WS connections" value={loading ? null : wsConns}
          sub="across all channels" color="var(--cyan)"/>
        <KpiCard label="Model version" value={loading ? null : (health?.model_version ?? "—")}
          sub={health?.model_type || "autoencoder+lstm"} color="var(--hydro)"/>
        <KpiCard label="Live events" value={terminal.length}
          sub={paused ? "stream paused" : "streaming"} color="var(--ok)"/>
      </div>

      <div className="grid g-dash mb-16">
        <Card label="Live Stream" title="WebSocket event terminal" tag={paused ? "PAUSED" : "LIVE"}>
          <div ref={termRef} className="mono" style={{
            background: "var(--bg-1)", borderRadius: 6, padding: 12,
            fontSize: 11, lineHeight: 1.65, color: "var(--text-muted)",
            maxHeight: 400, overflow: "auto",
          }}>
            {terminal.length === 0 && (
              <div style={{ color: "var(--text-dim)" }}>
                Waiting for WebSocket events… authenticate and connect to /ws/anomalies
              </div>
            )}
            {terminal.map((l, i) => (
              <div key={i} style={{ color: l.lvl === "CRIT" ? "var(--crit)" : l.lvl === "WARN" ? "var(--warn)" : "var(--text-muted)" }}>
                {l.line}
              </div>
            ))}
            {!paused && (
              <div className="row" style={{ gap: 4, color: "var(--cyan)" }}>
                <span>{">"}</span>
                <span style={{ width: 6, height: 12, background: "var(--cyan)", animation: "pulse 1s infinite" }}/>
              </div>
            )}
          </div>
        </Card>

        <Card label="System Health" title="Backend status">
          {loading ? <LoadingState/> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { name: "API server",     val: health?.status || "unknown",  s: health?.status === "healthy" ? "ok" : "warn" },
                { name: "ML model",       val: health?.model_type || "—",     s: health?.model_loaded ? "ok" : "warn" },
                { name: "Model version",  val: String(health?.model_version ?? "—"), s: health?.model_version ? "ok" : "info" },
                { name: "WS · anomalies", val: `${health?.ws_connections?.anomalies || 0} conn`, s: "ok" },
                { name: "WS · risk-map",  val: `${health?.ws_connections?.["risk-map"] || 0} conn`, s: "ok" },
                { name: "WS · health",    val: `${health?.ws_connections?.health || 0} conn`, s: "ok" },
              ].map(s => (
                <div key={s.name} className="row between mono-sm" style={{ padding: "6px 8px", borderRadius: 4, background: "var(--bg-1)" }}>
                  <span style={{ color: "var(--text)" }}>{s.name}</span>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="mono muted">{s.val}</span>
                    <Status kind={s.s}>{s.s.toUpperCase()}</Status>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ── Drift Monitoring Panel ────────────────────────────────── */}
      {health?.drift && (
        <div className="mb-16">
          <Card label="Drift Monitoring" title="PSI Feature Drift — All Cities">
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {Object.entries(health.drift.states || {}).map(([slug, status]) => {
                const needsRetrain = (health.drift.needs_retrain || []).includes(slug);
                const s = status === "CRITICAL" ? "crit" : status === "WARN" ? "warn" : "ok";
                return (
                  <div key={slug} className="row between mono-sm" style={{ padding: "6px 8px", borderRadius: 4, background: "var(--bg-1)" }}>
                    <span style={{ color: "var(--text)", textTransform: "capitalize" }}>{slug.replace(/_/g, " ")}</span>
                    <div className="row" style={{ gap: 8 }}>
                      {needsRetrain && <span style={{ fontSize: 10, color: "var(--crit)", fontWeight: 700 }}>RETRAIN</span>}
                      <Status kind={s}>{status}</Status>
                    </div>
                  </div>
                );
              })}
              {Object.keys(health.drift.states || {}).length === 0 && (
                <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }}>
                  Drift monitoring builds reference window over first 500 predictions per city.
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* ── Model Registry Panel ─────────────────────────────────── */}
      {health?.registry && health.registry.total_registered > 0 && (
        <div className="mb-16">
          <Card label="Model Registry" title={`${health.registry.total_registered} cities registered`}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-dim)" }}>
                    {["City", "Version", "Architecture", "AE val_loss", "N train", "Promoted"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(health.registry.entries || {}).map(([slug, e]) => (
                    <tr key={slug} style={{ borderBottom: "1px solid var(--border-dim)" }}>
                      <td style={{ padding: "4px 8px", textTransform: "capitalize" }}>{slug.replace(/_/g, " ")}</td>
                      <td style={{ padding: "4px 8px" }}>v{e.version}</td>
                      <td style={{ padding: "4px 8px" }}>{e.architecture || "—"}</td>
                      <td style={{ padding: "4px 8px" }}>{e.ae_val_loss != null ? e.ae_val_loss.toFixed(5) : "—"}</td>
                      <td style={{ padding: "4px 8px" }}>{e.n_train?.toLocaleString() || "—"}</td>
                      <td style={{ padding: "4px 8px" }}>{e.promoted_at ? e.promoted_at.slice(0,10) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
      {/* ── Per-City ML Health Grid ──────────────────────────────── */}
      <div className="mb-16">
        <Card label="ML Runtime Health" title="Per-city inference · drift · epistemic stability">
          {!cityHealth ? (
            <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }}>
              Waiting for /ws/health broadcast (30 s cadence)…
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
              {Object.entries(cityHealth).map(([slug, c]) => {
                const infKind = c.inference_health === "ok" ? "ok" : c.inference_health === "critical" ? "crit" : c.inference_health === "degraded" ? "warn" : "info";
                const psiKind = c.psi_status === "ok" ? "ok" : c.psi_status === "critical" ? "crit" : c.psi_status === "warn" ? "warn" : "info";
                const epKind  = c.epistemic_stability === "stable" ? "ok" : c.epistemic_stability === "anomalous" ? "crit" : c.epistemic_stability === "drifting" ? "warn" : "info";
                return (
                  <div key={slug} style={{ background: "var(--bg-1)", borderRadius: 6, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, textTransform: "capitalize", color: "var(--text)", marginBottom: 2 }}>
                      {slug.replace(/_/g, " ")}
                    </div>
                    <div className="row between mono-sm">
                      <span style={{ color: "var(--text-muted)" }}>Inference</span>
                      <Status kind={infKind}>{c.inference_health.toUpperCase()}</Status>
                    </div>
                    <div className="row between mono-sm">
                      <span style={{ color: "var(--text-muted)" }}>PSI drift{c.top_drifted_feature ? ` (${c.top_drifted_feature})` : ""}</span>
                      <div className="row" style={{ gap: 6 }}>
                        {c.psi_max != null && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>{c.psi_max.toFixed(3)}</span>}
                        <Status kind={psiKind}>{c.psi_status.toUpperCase()}</Status>
                      </div>
                    </div>
                    <div className="row between mono-sm">
                      <span style={{ color: "var(--text-muted)" }}>Epistemic</span>
                      <div className="row" style={{ gap: 6 }}>
                        {c.epistemic_drift != null && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>{c.epistemic_drift.toFixed(1)}σ</span>}
                        <Status kind={epKind}>{c.epistemic_stability.toUpperCase()}</Status>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

    </div>
  );
};

// ── Analytics Screen ───────────────────────────────────────────────────────
const AnalyticsScreen = ({ user }) => {
  const [stats,   setStats]   = useState(null);
  const [admin,   setAdmin]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const stRes = await API.getStatistics();
      setStats(stRes);
      // Admin analytics (requires ADMIN or ANALYST)
      if (user?.role === "ADMIN" || user?.role === "ANALYST") {
        try {
          const adRes = await API.getAdminAnalytics();
          setAdmin(adRes);
        } catch {}
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [user?.role]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Build monthly bar chart data from stats.by_month
  const monthLabels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const monthlyData = monthLabels.map((label, i) => {
    const key = String(i + 1).padStart(2, "0");
    const v = stats?.by_month?.[key] || 0;
    return { label: label.slice(0, 3), v, warn: v > 20, crit: v > 50 };
  });

  // Risk level distribution
  const riskDist = stats?.by_risk_level || {};

  // City distribution
  const cityDist = stats?.by_city || {};
  const topCities = Object.entries(cityDist).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxCityCount = Math.max(...topCities.map(([,v]) => v), 1);

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Analytics & Reports</h1>
          <div className="page-sub">Historical trends · model performance · export</div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={fetchData}><Icon name="refresh"/>Refresh</button>
          <button className="btn" onClick={async () => {
            try {
              const data = await API.getDatabaseStats();
              const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
              const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
              a.download = "hydroguard-stats.json"; a.click();
              toast("Stats exported", "ok");
            } catch (e) { toast("Export failed: " + e.message, "crit"); }
          }}>
            <Icon name="download"/>Export JSON
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={fetchData}/>}

      <div className="grid g-4 mb-16">
        <KpiCard label="Total records" value={loading ? null : stats?.total_records ?? 0}
          sub="all cities · all time" color="var(--cyan)"/>
        <KpiCard label="Anomalies detected" value={loading ? null : stats?.anomaly_count ?? 0}
          sub={`rate ${stats?.anomaly_rate != null ? (stats.anomaly_rate * 100).toFixed(1) + "%" : "—"}`}
          color="var(--ok)"/>
        <KpiCard label="Cloudburst alerts" value={loading ? null : stats?.cloudburst_count ?? 0}
          sub="is_cloudburst_likely=true" color="var(--hydro)"/>
        <KpiCard label="This week (admin)" value={loading ? null : (admin?.total_anomalies_this_week ?? "—")}
          sub={user?.role === "ADMIN" || user?.role === "ANALYST" ? "past 7 days" : "requires ANALYST role"}
          color="var(--warn)"/>
      </div>

      <div className="grid g-2 mb-16">
        <Card label="Monthly Anomalies" title="By count · calendar year">
          {loading ? <LoadingState/> : <BarChart data={monthlyData} height={180}/>}
        </Card>

        <Card label="Risk Level Distribution" title="All-time breakdown">
          {loading ? <LoadingState/> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {["CRITICAL","HIGH","MEDIUM","LOW"].map(rl => {
                const v = riskDist[rl] || 0;
                const total = Object.values(riskDist).reduce((a, b) => a + b, 0) || 1;
                const pct = Math.round((v / total) * 100);
                return (
                  <div key={rl}>
                    <div className="row between mono-sm mb-8">
                      <span style={{ color: "var(--text)" }}>{rl}</span>
                      <span className="muted">{v} · {pct}%</span>
                    </div>
                    <div className="bar">
                      <span style={{ width: `${pct}%`, background: riskColor(rl) }}/>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <div className="grid g-2">
        <Card label="Top Cities" title="By anomaly frequency">
          {loading ? <LoadingState/> : topCities.length === 0
            ? <EmptyState message="No city data yet." icon="city"/>
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {topCities.map(([city, count], i) => (
                  <div key={city}>
                    <div className="row between mono-sm mb-8">
                      <span style={{ color: "var(--text)" }}>{i + 1}. {city}</span>
                      <span className="muted">{count} events</span>
                    </div>
                    <div className="bar">
                      <span style={{ width: `${(count / maxCityCount) * 100}%`, background: "var(--hydro)" }}/>
                    </div>
                  </div>
                ))}
              </div>
            )
          }
        </Card>

        <Card label="Admin Analytics" title={user?.role === "ADMIN" || user?.role === "ANALYST" ? "Weekly summary" : "Requires ANALYST role"}>
          {loading ? <LoadingState/> : admin ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted">Anomalies this week</span>
                <span className="mono">{admin.total_anomalies_this_week}</span>
              </div>
              <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted">Total cloudburst alerts</span>
                <span className="mono">{admin.total_cloudburst_alerts}</span>
              </div>
              <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted">Total records in DB</span>
                <span className="mono">{admin.total_records_in_db}</span>
              </div>
              <div className="mt-8">
                <div className="mono-sm dim mb-8" style={{ letterSpacing: "0.1em" }}>TOP CITIES</div>
                {(admin.top_cities_by_frequency || []).map((c, i) => (
                  <div key={i} className="row between mono-sm" style={{ padding: "4px 0" }}>
                    <span>{c.city}</span><span className="muted">{c.count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState message={`Admin analytics require ANALYST or ADMIN role. Your role: ${user?.role || "USER"}`} icon="lock"/>
          )}
        </Card>
      </div>
    </div>
  );
};

// ── City Management Screen ─────────────────────────────────────────────────
const CitiesScreen = ({ city, cities, onNav }) => {
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">City Management</h1>
          <div className="page-sub">Risk levels, HRI scores, and monitoring scope per city</div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={async () => {
            setLoading(true);
            try {
              const data = await API.getRiskMap();
              window._setCities(data.entries || []);
              toast("City data refreshed", "ok");
            } catch (e) { setError(e.message); toast("Refresh failed", "crit"); }
            setLoading(false);
          }}>
            {loading ? <Spinner size={13}/> : <Icon name="refresh"/>}
            Refresh risk map
          </button>
        </div>
      </div>

      {error && <ErrorState message={error}/>}

      <div className="grid g-3 mb-16">
        {cities.map(c => {
          const color = riskColor(c.risk_level);
          return (
            <div key={c.id} className="card" style={{
              padding: 16, cursor: "pointer",
              borderColor: c.id === city?.id ? "var(--hydro)" : "var(--border)",
            }}>
              <div className="row between">
                <div>
                  <div className="mono-sm dim">{c.lat} · {c.lng}</div>
                  <div style={{ fontSize: 17, fontWeight: 500, marginTop: 2 }}>{c.name}</div>
                  <div className="mono-sm muted">{c.region} · HRI {c.hri_score ?? "—"}</div>
                </div>
                <Status kind={riskKind(c.risk_level)}>{c.risk_level || "?"}</Status>
              </div>
              <div className="mt-12 mb-8">
                <div className="bar" style={{ height: 6 }}>
                  <span style={{ width: `${c.hri_score || 0}%`, background: color }}/>
                </div>
                <div className="mono dim" style={{ fontSize: 10, marginTop: 3 }}>
                  HRI score: {c.hri_score ?? "—"} / 100 · {c.hri_label || "—"}
                </div>
              </div>
              <div className="row between mono-sm muted" style={{ marginTop: 8 }}>
                <span>Pop: <span className="mono">{c.pop || "?"}</span></span>
                <span>Risk: <span className="mono" style={{ color }}>{c.risk_level || "?"}</span></span>
                <span>
                  <button className="btn" style={{ padding: "3px 8px", fontSize: 11 }}
                    onClick={() => onNav && onNav("cloudburst")}>
                    View events
                  </button>
                </span>
              </div>
            </div>
          );
        })}
        {cities.length === 0 && (
          <div style={{ gridColumn: "1/-1" }}>
            <EmptyState message="City data is loading… ensure the model is trained and /risk-map is available." icon="city"/>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Prediction Screen ──────────────────────────────────────────────────────
const PredictScreen = ({ city }) => {
  const now = new Date();
  const [form, setForm] = useState({
    city:        city?.name || "Islamabad",
    region:      city?.region || "Punjab",
    date:        now.toISOString().slice(0, 10),
    month:       String(now.getMonth() + 1),
    day:         String(now.getDate()),
    tmin:        "22", tmax: "34", tavg: "28",
    prcp:        "0", wspd: "15", humidity: "60",
    pressure:    "1005", dew_point: "18", cloud_cover: "30",
  });
  const [result,   setResult]   = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  useEffect(() => {
    if (city) setForm(f => ({ ...f, city: city.name, region: city.region || f.region }));
  }, [city?.name]);

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const runPredict = async () => {
    setLoading(true); setError(""); setResult(null);
    try {
      // v2 required: city, prcp, humidity, pressure
      const payload = {
        city:        form.city,
        prcp:        parseFloat(form.prcp)        ?? 0,
        humidity:    parseFloat(form.humidity)    || 60,
        pressure:    parseFloat(form.pressure)    || 1013,
        tmin:        parseFloat(form.tmin)        || undefined,
        tmax:        parseFloat(form.tmax)        || undefined,
        tavg:        parseFloat(form.tavg)        || undefined,
        wspd:        parseFloat(form.wspd)        || undefined,
        dew_point:   parseFloat(form.dew_point)   || undefined,
        cloud_cover: parseFloat(form.cloud_cover) || undefined,
      };
      const res = await API.predict(payload);
      setResult(res);
      // v2 returns risk_band; v1 returns risk_level — support both
      const band = res.risk_band || res.risk_level || "Low";
      const kind = band.toLowerCase() === "high" ? "crit" : band.toLowerCase() === "medium" ? "warn" : "ok";
      toast(`Prediction complete: ${band}`, kind);
    } catch (e) {
      setError(e.message);
      toast("Prediction failed: " + e.message, "crit");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = { background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", padding: "8px 10px", fontSize: 13, fontFamily: "inherit", width: "100%" };

  const Field = ({ label, name, type = "number" }) => (
    <div>
      <label className="field-label">{label}</label>
      <input type={type} value={form[name]} onChange={e => setField(name, e.target.value)} style={inputStyle}/>
    </div>
  );

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Run Prediction</h1>
          <div className="page-sub">Submit weather observations to the hybrid AE+LSTM model</div>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={runPredict} disabled={loading}>
            {loading ? <><Spinner size={13}/>Running…</> : <><Icon name="zap"/>Predict</>}
          </button>
        </div>
      </div>

      {error && <ErrorState message={error}/>}

      <div className="predict-grid">
        <Card label="Input Parameters" title="Weather observation">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="field-label">City *</label>
              <select value={form.city} onChange={e => setField("city", e.target.value)} style={inputStyle}>
                {["Islamabad","Rawalpindi","Lahore","Karachi","Peshawar","Quetta","Multan","Faisalabad","Hyderabad","Gilgit"].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label">Date</label>
              <input type="date" value={form.date} onChange={e => setField("date", e.target.value)} style={inputStyle}/>
            </div>
            <Field label="Min temp (°C)" name="tmin"/>
            <Field label="Max temp (°C)" name="tmax"/>
            <Field label="Avg temp (°C)" name="tavg"/>
            <Field label="Precipitation (mm)" name="prcp"/>
            <Field label="Wind speed (km/h)" name="wspd"/>
            <Field label="Humidity (%)" name="humidity"/>
            <Field label="Pressure (hPa)" name="pressure"/>
            <Field label="Dew point (°C)" name="dew_point"/>
            <Field label="Cloud cover (%)" name="cloud_cover"/>
            <div>
              <label className="field-label">Region</label>
              <input type="text" value={form.region} onChange={e => setField("region", e.target.value)} style={inputStyle}/>
            </div>
          </div>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {result ? (
            <>
              <Card label="Prediction Result" title={result.city || result.city_slug}>
                {/* ── Main score ── */}
                {(() => {
                  // Support both v2 (risk_band, event_probability) and v1 (risk_level, anomaly_score)
                  const band  = result.risk_band  || result.risk_level  || "Low";
                  const prob  = result.event_probability ?? result.anomaly_score;
                  const alert = result.is_alert   ?? result.is_anomaly  ?? false;
                  return (
                    <div className={`result-panel ${riskKind(band)}`}>
                      <div className="mono-sm dim" style={{ letterSpacing: "0.1em" }}>
                        {result.event_probability != null ? "EVENT PROBABILITY" : "ANOMALY SCORE"}
                      </div>
                      <div className="result-value" style={{ color: riskColor(band) }}>
                        {prob != null ? prob.toFixed(3) : "—"}
                      </div>
                      <div className="row mt-8" style={{ gap: 10 }}>
                        <Status kind={riskKind(band)}>{band}</Status>
                        {alert && <Status kind="crit">ALERT</Status>}
                        {result.source && <span className="mono-sm muted">{result.source}</span>}
                      </div>
                    </div>
                  );
                })()}
                <hr className="hr"/>
                <div className="mono-sm" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {/* v2 fields */}
                  {result.inference_id     != null && <div className="row between"><span className="muted">Inference ID</span><span className="mono" style={{ fontSize: 10 }}>{result.inference_id.slice(0, 16)}…</span></div>}
                  {result.model_version    != null && <div className="row between"><span className="muted">Model version</span><span className="mono">{result.model_version}</span></div>}
                  {result.uncertainty      != null && <div className="row between"><span className="muted">Uncertainty</span><span className="mono">{result.uncertainty.toFixed(3)}</span></div>}
                  {result.model_entropy    != null && <div className="row between"><span className="muted">Model entropy H(p)</span><span className="mono">{result.model_entropy.toFixed(3)}</span></div>}
                  {result.confidence_interval && <div className="row between"><span className="muted">95% CI</span><span className="mono">[{result.confidence_interval[0]?.toFixed(2)}, {result.confidence_interval[1]?.toFixed(2)}]</span></div>}
                  {/* v1 compat fields */}
                  {result.hri_score        != null && <div className="row between"><span className="muted">HRI score</span><span className="mono">{result.hri_score}</span></div>}
                  {result.consensus_score  != null && <div className="row between"><span className="muted">Consensus score</span><span className="mono">{result.consensus_score.toFixed(4)}</span></div>}
                  {result.cloudburst_risk  != null && (
                    <>
                      <div className="row between">
                        <span className="muted">Cloudburst likely</span>
                        <Status kind={result.cloudburst_risk.is_likely ? "crit" : "ok"}>
                          {result.cloudburst_risk.is_likely ? "YES" : "NO"}
                        </Status>
                      </div>
                      <div className="row between"><span className="muted">CB score</span><span className="mono">{result.cloudburst_risk.score?.toFixed(3) ?? "—"}</span></div>
                    </>
                  )}
                </div>
              </Card>

              {/* SHAP / feature contributions */}
              {(result.shap_values || result.feature_contributions) && (
                <Card label="Top Drivers (SHAP)" title="Feature importance">
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {(result.shap_values || Object.entries(result.feature_contributions || {}).map(([feature, shap]) => ({ feature, shap }))).slice(0, 8).map((e, i) => {
                      const feature = e.feature || e[0];
                      const shap    = typeof e.shap === "number" ? e.shap : (e[1] || 0);
                      const val     = e.value;
                      return (
                        <div key={i}>
                          <div className="row between mono-sm mb-4">
                            <span style={{ color: "var(--text)" }}>{feature}</span>
                            <span className="muted">
                              {shap.toFixed(4)}{val != null ? ` (val: ${typeof val === "number" ? val.toFixed(2) : val})` : ""}
                            </span>
                          </div>
                          <div className="bar">
                            <span style={{ width: `${Math.min(Math.abs(shap) * 300, 100)}%`, background: shap > 0 ? "var(--crit)" : "var(--ok)" }}/>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}
            </>
          ) : (
            <Card>
              <div className="empty-state">
                <div className="icon" style={{ marginBottom: 16 }}><Icon name="zap" size={32}/></div>
                <div>Fill in the weather parameters and click <strong>Predict</strong></div>
                <div className="muted mt-8" style={{ fontSize: 12 }}>Results will appear here</div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Settings Screen ────────────────────────────────────────────────────────
const TRAIN_CITIES = ["Islamabad","Rawalpindi","Lahore","Karachi","Peshawar","Quetta","Multan","Faisalabad","Hyderabad","Gilgit"];

const SettingsScreen = ({ user }) => {
  const [modelInfo,   setModelInfo]   = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [training,    setTraining]    = useState(false);
  const [trainMsg,    setTrainMsg]    = useState("");
  const [epochs,      setEpochs]      = useState("100");
  const [useTcn,      setUseTcn]      = useState(true);
  const [trainCity,   setTrainCity]   = useState("Islamabad");
  const [trainStatus, setTrainStatus] = useState(null);
  const [error,       setError]       = useState("");

  useEffect(() => {
    API.modelInfo().then(d => { setModelInfo(d); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const triggerRetrain = async () => {
    if (user?.role !== "ADMIN") { toast("Only ADMIN users can trigger retraining.", "crit"); return; }
    setTraining(true); setTrainMsg(""); setTrainStatus(null); setError("");
    try {
      const res = await API.triggerTraining(trainCity, {
        use_tcn: useTcn,
        epochs:  parseInt(epochs) || 100,
      });
      setTrainMsg(`Training queued (run_id: ${res.id || res.run_id || "—"})`);
      setTrainStatus(res);
      toast(`Training queued for ${trainCity}`, "ok");
      // Poll training status after 5s
      setTimeout(async () => {
        try {
          const st = await API.getTrainingStatus(trainCity);
          setTrainStatus(st);
        } catch (_) {}
        API.modelInfo().then(d => setModelInfo(d)).catch(() => {});
      }, 5000);
    } catch (e) {
      setError(e.message);
      toast("Training failed: " + e.message, "crit");
    } finally {
      setTraining(false);
    }
  };

  const isAdmin = user?.role === "ADMIN";

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">System Settings</h1>
          <div className="page-sub">API · model · notifications · configuration</div>
        </div>
      </div>

      {error && <ErrorState message={error}/>}
      {trainMsg && (
        <div style={{ padding: "10px 14px", borderRadius: 8, background: "oklch(0.74 0.14 155 / 0.12)", border: "1px solid oklch(0.74 0.14 155 / 0.3)", color: "var(--ok)", fontSize: 13, marginBottom: 16, display: "flex", gap: 8, alignItems: "center" }}>
          <Icon name="check" size={14}/>{trainMsg}
        </div>
      )}

      <div className="grid g-2 mb-16">
        <Card label="API Endpoints" title="Backend connections (v2)">
          <SettingsRow label="Prediction API (v2)"  val={`${API.BASE}/api/v2/cities/{city}/predict`}    status="ok"/>
          <SettingsRow label="Cities API (v2)"      val={`${API.BASE}/api/v2/cities`}                  status="ok"/>
          <SettingsRow label="Drift API (v2)"       val={`${API.BASE}/api/v2/drift`}                   status="ok"/>
          <SettingsRow label="Training API (v2)"    val={`${API.BASE}/api/v2/training/{city}`}         status="ok"/>
          <SettingsRow label="Auth API"             val={`${API.BASE}/auth`}                           status="ok"/>
          <SettingsRow label="WebSocket anomalies"  val={`${API.BASE.replace("http","ws")}/ws/anomalies`} status="ok"/>
        </Card>

        <Card label="Alert Thresholds" title="System defaults">
          <ThresholdRow label="Rainfall · alert"      val="70"   unit="mm/h" max={150}/>
          <ThresholdRow label="Rainfall · cloudburst" val="90"   unit="mm/h" max={150}/>
          <ThresholdRow label="Anomaly score"         val="0.85" unit=""     max={1}/>
          <ThresholdRow label="Drainage saturation"   val="85"   unit="%"    max={100}/>
          <div className="mt-8 mono-sm muted" style={{ fontSize: 11 }}>
            Thresholds are configured in <code>backend/app/core/config.py</code>
          </div>
        </Card>
      </div>

      <div className="grid g-2">
        <Card label="Notifications" title="Delivery channels">
          {[
            { ch: "In-app push · HydroGuard dashboard", on: true,  addr: "All roles · JWT authenticated" },
            { ch: "WebSocket broadcast · real-time",    on: true,  addr: "/ws/anomalies · /ws/risk-map" },
            { ch: "REST alert endpoint",                on: true,  addr: "POST /predict → emit_anomaly()" },
            { ch: "Email / SMS",                        on: false, addr: "Configure in .env file" },
            { ch: "Webhook dispatch",                   on: false, addr: "Configure NDMA webhook in .env" },
          ].map((n, i) => (
            <div key={i} className="row between" style={{ padding: "10px 0", borderBottom: i < 4 ? "1px solid var(--border)" : "none" }}>
              <div>
                <div style={{ color: "var(--text)" }}>{n.ch}</div>
                <div className="mono-sm dim">{n.addr}</div>
              </div>
              <Toggle on={n.on}/>
            </div>
          ))}
        </Card>

        <Card label="Model · AE+TCN+Fusion" title="v2 per-city training">
          {loading ? <LoadingState/> : (
            <>
              <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted">Status</span>
                <Status kind={modelInfo?.is_trained ? "ok" : "warn"}>
                  {modelInfo?.is_trained ? "Trained" : "No models"}
                </Status>
              </div>
              <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="muted">Architecture</span>
                <span className="mono">{modelInfo?.model_type || "city_hybrid_v2"}</span>
              </div>
              {modelInfo?.city_models && (
                <div className="row between mono-sm" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <span className="muted">Trained cities</span>
                  <span className="mono">{modelInfo.city_models.trained_cities ?? "—"} / {modelInfo.city_models.total_cities ?? 10}</span>
                </div>
              )}

              {isAdmin && (
                <>
                  <hr className="hr"/>
                  <div className="mono-sm muted mb-8" style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    Train a city model
                  </div>
                  <div className="row between mono-sm mb-8">
                    <span className="muted">City</span>
                    <select value={trainCity} onChange={e => setTrainCity(e.target.value)}
                      style={{ background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)", padding: "3px 8px", fontFamily: "var(--mono)", fontSize: 12 }}>
                      {TRAIN_CITIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div className="row between mono-sm mb-8">
                    <span className="muted">Epochs</span>
                    <input type="number" value={epochs} min="1" max="500"
                      onChange={e => setEpochs(e.target.value)}
                      style={{ background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)", padding: "3px 8px", fontFamily: "var(--mono)", fontSize: 12, width: 70, textAlign: "right" }}
                    />
                  </div>
                  <div className="row between mono-sm mb-12">
                    <span className="muted">Use CausalTCN</span>
                    <Toggle on={useTcn} onChange={setUseTcn}/>
                  </div>
                  <button className="btn btn-primary"
                    style={{ width: "100%", justifyContent: "center" }}
                    onClick={triggerRetrain} disabled={training}>
                    {training ? <><Spinner size={13}/>Queuing…</> : <><Icon name="brain"/>Train {trainCity}</>}
                  </button>
                  {trainStatus && (
                    <div className="mt-8 mono-sm muted" style={{ fontSize: 11 }}>
                      Status: {trainStatus.status} · ID: {(trainStatus.id || trainStatus.run_id || "—").toString().slice(0, 8)}
                    </div>
                  )}
                </>
              )}
              {!isAdmin && (
                <div className="mt-12 mono-sm muted" style={{ fontSize: 11, textAlign: "center" }}>
                  Training requires ADMIN role · your role: {user?.role || "—"}
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
};

// ── Profile Screen ─────────────────────────────────────────────────────────
const ProfileScreen = ({ user }) => {
  const [fullUser, setFullUser] = useState(user);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    API.me().then(u => { setFullUser(u); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const initials = fullUser?.username
    ? fullUser.username.slice(0, 2).toUpperCase()
    : "HG";

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">User Profile</h1>
          <div className="page-sub">Role · access · account details</div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "300px 1fr", gap: 14 }}>
        <Card>
          {loading ? <LoadingState/> : (
            <>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "12px 0 20px" }}>
                <div className="avatar" style={{ width: 72, height: 72, fontSize: 24 }}>{initials}</div>
                <div style={{ fontSize: 18, fontWeight: 500, marginTop: 12 }}>{fullUser?.username || "—"}</div>
                <div className="mono-sm dim">{fullUser?.email || "—"}</div>
                <Status kind={fullUser?.role === "ADMIN" ? "crit" : fullUser?.role === "ANALYST" ? "warn" : "ok"}
                  style={{ marginTop: 8 }}>
                  {fullUser?.role || "USER"}
                </Status>
              </div>
              <hr className="hr"/>
              <div className="mono-sm" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="row between">
                  <span className="muted">ID</span>
                  <span className="mono">{fullUser?.id}</span>
                </div>
                <div className="row between">
                  <span className="muted">Email</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{fullUser?.email || "—"}</span>
                </div>
                <div className="row between">
                  <span className="muted">Role</span>
                  <span>{fullUser?.role || "—"}</span>
                </div>
                <div className="row between">
                  <span className="muted">Status</span>
                  <Status kind={fullUser?.is_active ? "ok" : "warn"}>
                    {fullUser?.is_active ? "Active" : "Inactive"}
                  </Status>
                </div>
                <div className="row between">
                  <span className="muted">Registered</span>
                  <span className="mono">{fullUser?.created_at?.slice(0, 10) || "—"}</span>
                </div>
              </div>
            </>
          )}
        </Card>

        <Card label="Capabilities" title="What you can access">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { cap: "View Dashboard",           roles: ["USER","ANALYST","ADMIN"] },
              { cap: "Run Predictions",           roles: ["USER","ANALYST","ADMIN"] },
              { cap: "View Anomaly Records",      roles: ["USER","ANALYST","ADMIN"] },
              { cap: "View Risk Map",             roles: ["USER","ANALYST","ADMIN"] },
              { cap: "Analytics & Reports",       roles: ["ANALYST","ADMIN"] },
              { cap: "Admin Analytics",           roles: ["ANALYST","ADMIN"] },
              { cap: "Trigger Model Retraining",  roles: ["ADMIN"] },
            ].map((c, i) => {
              const allowed = c.roles.includes(fullUser?.role);
              return (
                <div key={i} className="row between" style={{ padding: "8px 12px", borderRadius: 6, background: "var(--bg-1)" }}>
                  <span style={{ color: allowed ? "var(--text)" : "var(--text-dim)" }}>{c.cap}</span>
                  <Status kind={allowed ? "ok" : "warn"}>
                    {allowed ? "Allowed" : "Restricted"}
                  </Status>
                </div>
              );
            })}
          </div>
          <hr className="hr"/>
          <div className="mono-sm muted" style={{ fontSize: 11 }}>
            Role assignment at registration · contact ADMIN to change
          </div>
        </Card>
      </div>
    </div>
  );
};

Object.assign(window, { MonitoringScreen, AnalyticsScreen, CitiesScreen, PredictScreen, SettingsScreen, ProfileScreen });
