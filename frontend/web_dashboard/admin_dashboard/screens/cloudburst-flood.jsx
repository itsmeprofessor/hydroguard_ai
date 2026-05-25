// HydroGuard AI — Cloudburst detection + Flash flood risk screens
const { useState, useEffect, useCallback, useRef } = React;

// ── Cloudburst Screen ──────────────────────────────────────────────────────
const CloudburstScreen = ({ city, cities, liveEvents }) => {
  const [events,     setEvents]     = useState([]);
  const [stats,      setStats]      = useState(null);
  const [logLines,   setLogLines]   = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [timeRange,  setTimeRange]  = useState("30d");
  const logRef = useRef(null);

  const fetchData = useCallback(async (cityName) => {
    setLoading(true); setError("");
    try {
      const [evRes, statRes] = await Promise.all([
        API.getAnomalies({ city: cityName, limit: 50, anomalies_only: true }),
        API.getStatistics({ city: cityName }),
      ]);
      setEvents(evRes.anomalies || []);
      setStats(statRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!city) return;
    fetchData(city.name);
  }, [city?.name, fetchData]);

  // Append live WS events to detection log
  useEffect(() => {
    if (!liveEvents.length) return;
    const e = liveEvents[0];
    const ts = new Date().toTimeString().slice(0, 8);
    const lvl = e.risk_level === "CRITICAL" ? "CRIT" : e.is_anomaly ? "WARN" : "INFO";
    const msg = `${e.city} · score ${e.anomaly_score?.toFixed(3)} · ${e.risk_level} · HRI ${e.hri_score ?? "—"}`;
    setLogLines(prev => [{ t: ts, lvl, msg }, ...prev].slice(0, 40));
    if (logRef.current) logRef.current.scrollTop = 0;
  }, [liveEvents]);

  // Bin distribution from events
  const bins = (() => {
    if (!events.length) return [];
    const rainfall = events.map(e => e.weather_data?.prcp || e.anomaly_score * 100).filter(Boolean);
    const counts = [0, 0, 0, 0, 0, 0];
    rainfall.forEach(r => {
      if (r < 30)  counts[0]++;
      else if (r < 50)  counts[1]++;
      else if (r < 70)  counts[2]++;
      else if (r < 90)  counts[3]++;
      else if (r < 110) counts[4]++;
      else counts[5]++;
    });
    return [
      { label: "<30",    v: counts[0] },
      { label: "30-50",  v: counts[1] },
      { label: "50-70",  v: counts[2] },
      { label: "70-90",  v: counts[3], warn: true },
      { label: "90-110", v: counts[4], warn: true },
      { label: "110+",   v: counts[5], crit: true },
    ];
  })();

  const totalEvents  = stats?.anomaly_count ?? events.length;
  const cloudburstCt = stats?.cloudburst_count ?? events.filter(e => e.cloudburst_risk?.is_likely).length;
  const avgScore     = events.length ? (events.reduce((a, e) => a + (e.anomaly_score || 0), 0) / events.length).toFixed(3) : null;

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Cloudburst Detection · {city?.name || "—"}</h1>
          <div className="page-sub">Extreme-precipitation analytics and historical event registry</div>
        </div>
        <div className="page-actions">
          <div className="seg">
            {["30d","90d","1yr","All"].map(r => (
              <button key={r} className={timeRange === r ? "on" : ""} onClick={() => setTimeRange(r)}>{r}</button>
            ))}
          </div>
          <button className="btn" onClick={() => fetchData(city?.name)}>
            <Icon name="refresh"/>Refresh
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => fetchData(city?.name)}/>}

      <div className="grid g-4 mb-16">
        <KpiCard label="Anomalies · detected"
          value={totalEvents != null ? totalEvents : null}
          sub={`cloudburst: ${cloudburstCt}`} color="var(--crit)"/>
        <KpiCard label="Avg anomaly score"
          value={avgScore}
          sub="threshold varies per city" color="var(--warn)"/>
        <KpiCard label="Cloudburst confirmed"
          value={cloudburstCt != null ? cloudburstCt : null}
          sub="is_cloudburst_likely=true" color="var(--cyan)"/>
        <KpiCard label="Total records"
          value={stats?.total_records ?? null}
          sub={`anomaly rate ${stats?.anomaly_rate != null ? (stats.anomaly_rate * 100).toFixed(1) + "%" : "—"}`}
          color="var(--hydro)"/>
      </div>

      <div className="grid g-dash mb-16">
        <Card label="Rainfall intensity · bin distribution"
          title={`${city?.name || ""} anomaly records`}
          tag={`${events.length} events`}>
          {loading
            ? <LoadingState/>
            : <BarChart data={bins.length ? bins : [{ label: "—", v: 0 }]} height={180}/>}
          <div className="mono-sm muted row between mt-8">
            <span>Bin: mm (est. from score)</span>
            <span>Cloudburst threshold ~90 mm/h</span>
          </div>
        </Card>

        <Card label="Detection Log" title="Live AI stream">
          <div ref={logRef} className="mono" style={{
            background: "var(--bg-1)", borderRadius: 6, padding: 12,
            fontSize: 11, lineHeight: 1.6, color: "var(--text-muted)",
            maxHeight: 340, overflow: "auto",
          }}>
            {logLines.length === 0 && (
              <div style={{ color: "var(--text-dim)" }}>Waiting for live events via WebSocket…</div>
            )}
            {logLines.map((l, i) => (
              <div key={i} className="row" style={{ gap: 10 }}>
                <span className="dim" style={{ fontSize: 10, width: 64 }}>{l.t}</span>
                <span style={{
                  fontSize: 10, width: 44, padding: "1px 4px", borderRadius: 3, textAlign: "center",
                  background: l.lvl === "CRIT" ? "var(--crit-soft)" : l.lvl === "WARN" ? "oklch(0.8 0.15 75 / 0.14)" : "var(--hydro-soft)",
                  color: l.lvl === "CRIT" ? "var(--crit)" : l.lvl === "WARN" ? "var(--warn)" : "var(--hydro)",
                }}>{l.lvl}</span>
                <span style={{ color: "var(--text-muted)", flex: 1 }}>{l.msg}</span>
              </div>
            ))}
            {/* Cursor */}
            <div className="row" style={{ gap: 4, color: "var(--cyan)" }}>
              <span>{">"}</span>
              <span style={{ width: 6, height: 12, background: "var(--cyan)", animation: "pulse 1s infinite" }}/>
            </div>
          </div>
        </Card>
      </div>

      <Card label="Historical Events"
        title="Anomaly records"
        right={<button className="btn" onClick={() => fetchData(city?.name)}><Icon name="refresh"/>Reload</button>}>
        <div style={{ margin: "-14px" }}>
          {loading
            ? <div style={{ padding: 24 }}><LoadingState/></div>
            : events.length === 0
              ? <div style={{ padding: 24 }}><EmptyState message="No anomaly events on record for this city." icon="check"/></div>
              : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>City</th>
                      <th>Score</th>
                      <th>HRI</th>
                      <th>Cloudburst</th>
                      <th>Risk Level</th>
                      <th>Remarks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e, i) => (
                      <tr key={i}>
                        <td className="mono strong">{e.date?.slice(0, 10) || "—"}</td>
                        <td className="strong">{e.city}</td>
                        <td className="mono" style={{ color: riskColor(e.risk_level) }}>
                          {e.anomaly_score?.toFixed(3)}
                        </td>
                        <td>
                          <div className="row" style={{ gap: 8 }}>
                            <div className="bar" style={{ width: 60 }}>
                              <span style={{ width: `${e.hri_score || 0}%`, background: riskColor(e.risk_level) }}/>
                            </div>
                            <span className="mono">{e.hri_score ?? "—"}</span>
                          </div>
                        </td>
                        <td>
                          <Status kind={e.cloudburst_risk?.is_likely ? "crit" : "ok"}>
                            {e.cloudburst_risk?.is_likely ? "LIKELY" : "NO"}
                          </Status>
                        </td>
                        <td><Status kind={riskKind(e.risk_level)}>{e.risk_level}</Status></td>
                        <td className="muted" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {e.remarks || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
          }
        </div>
      </Card>
    </div>
  );
};

// ── Flash Flood Risk Screen ────────────────────────────────────────────────
const FloodScreen = ({ city, cities }) => {
  const [riskMap,  setRiskMap]  = useState([]);
  const [stats,    setStats]    = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [rmRes, stRes] = await Promise.all([
        API.getRiskMap(),
        API.getStatistics(),
      ]);
      setRiskMap(rmRes.entries || []);
      setStats(stRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const critCount = riskMap.filter(e => e.risk_level === "CRITICAL").length;
  const highCount = riskMap.filter(e => e.risk_level === "HIGH").length;

  // Drainage simulation (static enriched with real data)
  const drainageData = [
    { name: "Nullah Leh",   in: 142, cap: 95,  util: 94 },
    { name: "G-13 culvert", in: 48,  cap: 60,  util: 80 },
    { name: "Korang stream",in: 78,  cap: 110, util: 71 },
    { name: "Rawal spillway",in: 210,cap: 320, util: 66 },
    { name: "F-10 drain",   in: 22,  cap: 55,  util: 40 },
  ];

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Flash Flood Risk · {city?.name || "—"}</h1>
          <div className="page-sub">Terrain · rainfall · drainage capacity models</div>
        </div>
        <div className="page-actions">
          <div className="seg">
            <button>Now</button><button className="on">+6h</button>
            <button>+24h</button><button>+72h</button>
          </div>
          <button className="btn btn-primary" onClick={fetchData}><Icon name="refresh"/>Refresh model</button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={fetchData}/>}

      <div className="grid g-4 mb-16">
        <KpiCard label="Critical risk cities"
          value={loading ? null : critCount}
          sub={`${highCount} high · ${riskMap.length} total`} color="var(--crit)"/>
        <KpiCard label="Anomaly rate (DB)"
          value={stats?.anomaly_rate != null ? `${(stats.anomaly_rate * 100).toFixed(1)}%` : null}
          sub="of all records" color="var(--warn)"/>
        <KpiCard label="Cloudburst alerts"
          value={stats?.cloudburst_count ?? null}
          sub="is_cloudburst_likely events" color="var(--warn)"/>
        <KpiCard label="Total records in DB"
          value={stats?.total_records ?? null}
          sub="all cities · all time" color="var(--hydro)"/>
      </div>

      <div className="grid g-dash mb-16">
        <Card label="Risk Modeling"
          title="Terrain + rainfall composite"
          right={<div className="seg"><button className="on">Hydro</button><button>Terrain</button><button>Drainage</button></div>}>
          <div style={{ position: "relative" }}>
            <FloodModelViz/>
          </div>
          <div className="row between mt-8" style={{ fontSize: 11 }}>
            <div className="row" style={{ gap: 12 }}>
              <LegendSwatch c="oklch(0.70 0.12 220)" l="Waterways"/>
              <LegendSwatch c="oklch(0.80 0.15 75)"  l="Medium risk"/>
              <LegendSwatch c="oklch(0.72 0.2 45)"   l="High risk"/>
              <LegendSwatch c="oklch(0.66 0.22 25)"  l="Critical zone"/>
            </div>
            <span className="mono dim" style={{ fontSize: 10 }}>Model · AE+LSTM</span>
          </div>
        </Card>

        <Card label="Drainage Simulation" title="Capacity vs inflow">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {drainageData.map(d => (
              <div key={d.name}>
                <div className="row between mono-sm" style={{ marginBottom: 4 }}>
                  <span style={{ color: "var(--text)" }}>{d.name}</span>
                  <span className="muted">{d.in} / {d.cap} m³/s</span>
                </div>
                <div className="bar" style={{ height: 6 }}>
                  <span style={{ width: `${Math.min(d.util, 100)}%`,
                    background: d.util > 90 ? "var(--crit)" : d.util > 75 ? "oklch(0.72 0.2 45)" : d.util > 50 ? "var(--warn)" : "var(--ok)" }}/>
                </div>
                <div className="mono dim" style={{ fontSize: 10, marginTop: 2 }}>{d.util}% utilization</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card label="Risk Map" title="All cities · current HRI">
        <div style={{ margin: "-14px" }}>
          {loading
            ? <div style={{ padding: 24 }}><LoadingState/></div>
            : riskMap.length === 0
              ? <div style={{ padding: 24 }}><EmptyState message="No risk data available. Ensure the model is trained." icon="map"/></div>
              : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>City</th>
                      <th>Region</th>
                      <th>HRI Score</th>
                      <th>HRI Label</th>
                      <th>Risk Level</th>
                      <th>Coordinates</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riskMap.sort((a, b) => (b.hri_score || 0) - (a.hri_score || 0)).map((e, i) => (
                      <tr key={i}>
                        <td className="strong">{e.city}</td>
                        <td className="muted">{e.region}</td>
                        <td>
                          <div className="row" style={{ gap: 8 }}>
                            <div className="bar" style={{ width: 80 }}>
                              <span style={{ width: `${e.hri_score || 0}%`, background: riskColor(e.risk_level) }}/>
                            </div>
                            <span className="mono" style={{ color: riskColor(e.risk_level) }}>{e.hri_score ?? "—"}</span>
                          </div>
                        </td>
                        <td>{e.hri_label || "—"}</td>
                        <td><Status kind={riskKind(e.risk_level)}>{e.risk_level}</Status></td>
                        <td className="mono dim" style={{ fontSize: 11 }}>{e.latitude?.toFixed(2)}, {e.longitude?.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
          }
        </div>
      </Card>
    </div>
  );
};

Object.assign(window, { CloudburstScreen, FloodScreen });
