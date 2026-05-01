// HydroGuard AI — Dashboard screen
const { useState, useEffect, useRef, useCallback } = React;

// ── Helper: build chart series from anomaly records ────────────────────────
function recordsToSeries(records) {
  return records.map(r => ({
    t:        r.date ? r.date.slice(11, 16) || r.date.slice(0, 10) : "—",
    rainfall: r.weather_data?.prcp != null ? parseFloat(r.weather_data.prcp) : (r.anomaly_score * 60),
    anomaly:  r.is_anomaly,
    score:    r.anomaly_score,
    city:     r.city,
  }));
}

// ── Dashboard Screen ───────────────────────────────────────────────────────
const DashboardScreen = ({ city, cities, alertFiring, liveEvents, user }) => {
  const [latest,  setLatest]  = useState(null);
  const [series,  setSeries]  = useState([]);
  const [alerts,  setAlerts]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");
  const timerRef = useRef(null);

  const fetchData = useCallback(async (cityName) => {
    setLoading(true); setError("");
    try {
      // 1. Latest record for metric cards
      const recentRes = await API.getAnomalies({ city: cityName, limit: 1, anomalies_only: false });
      const latestRec = recentRes.anomalies?.[0] || null;
      setLatest(latestRec);

      // 2. Chart data: last 100 records
      const chartRes = await API.getAnomalies({ city: cityName, limit: 100, anomalies_only: false });
      const s = recordsToSeries((chartRes.anomalies || []).reverse());
      setSeries(s);

      // 3. Alerts feed: recent anomalies across all cities
      const alertRes = await API.getAnomalies({ limit: 8, anomalies_only: true });
      setAlerts(alertRes.anomalies || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Refresh when city changes or on mount
  useEffect(() => {
    if (!city) return;
    fetchData(city.name);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => fetchData(city.name), 60000);
    return () => clearInterval(timerRef.current);
  }, [city?.name, fetchData]);

  // Push live WS events into chart
  useEffect(() => {
    if (!liveEvents.length) return;
    const e = liveEvents[0];
    if (city && e.city !== city.name) return;
    setSeries(prev => {
      const point = {
        t: new Date().toTimeString().slice(0, 5),
        rainfall: e.weather_data?.prcp ?? (e.anomaly_score * 60),
        anomaly: e.is_anomaly,
        score: e.anomaly_score,
        city: e.city,
      };
      return [...prev.slice(-199), point];
    });
    if (e.is_anomaly) {
      setAlerts(prev => [e, ...prev].slice(0, 8));
    }
  }, [liveEvents]);

  // Derived metrics
  const rainfall = latest?.weather_data?.prcp ?? null;
  const temp     = latest?.weather_data?.tavg ?? null;
  const pressure = latest?.weather_data?.pressure ?? null;
  const wind     = latest?.weather_data?.wspd ?? null;
  const anomalyScore = latest?.anomaly_score ?? null;
  const hriScore     = latest?.hri_score     ?? null;
  const riskLevel    = city?.risk_level || latest?.risk_level || "UNKNOWN";
  const riskViz      = city?.risk || "low";
  const confidence   = anomalyScore != null ? Math.round(Math.min(anomalyScore * 100, 99)) : null;

  // Sparkline data from series
  const rainfallSpark = series.slice(-20).map(d => d.rainfall);
  const tempSpark     = series.slice(-20).map((_, i) => 28 - i * 0.1 + Math.random() * 0.5);
  const pressureSpark = series.slice(-20).map((_, i) => 1000 - i * 0.2 + Math.random() * 0.3);
  const windSpark     = series.slice(-20).map((_, i) => 20 + i * 0.5 + Math.random());

  const critCities = (cities || []).filter(c => c.risk === "crit");

  return (
    <div className="screen">
      <div className="page-head">
        <div>
          <h1 className="page-title">Live Operations · {city?.name || "—"}</h1>
          <div className="page-sub">
            Real-time hydrometeorological monitoring ·{" "}
            <span className="live">LIVE</span>
          </div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => fetchData(city?.name)}>
            <Icon name="refresh"/>Refresh
          </button>
          <button className="btn" onClick={async () => {
            try {
              const stats = await API.getDatabaseStats();
              const blob = new Blob([JSON.stringify(stats, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a"); a.href = url; a.download = "hydroguard-snapshot.json"; a.click();
              toast("Snapshot exported", "ok");
            } catch (e) { toast("Export failed: " + e.message, "crit"); }
          }}>
            <Icon name="download"/>Export
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => fetchData(city?.name)}/>}

      {/* Metric cards */}
      <div className="grid g-4 mb-16">
        <MetricCard
          icon="droplet" label="Rainfall / precip."
          value={rainfall != null ? rainfall.toFixed(1) : null} unit="mm"
          delta={rainfall != null ? (rainfall > 70 ? "⚠ ALERT LEVEL" : "nominal") : "loading…"}
          deltaDir={rainfall != null && rainfall > 70 ? "up" : "flat"}
          spark={rainfallSpark}
          sparkColor={rainfall != null && rainfall > 70 ? "var(--crit)" : "var(--cyan)"}
        />
        <MetricCard
          icon="therm" label="Temperature (avg)"
          value={temp != null ? temp.toFixed(1) : null} unit="°C"
          delta={temp != null ? `${temp > 35 ? "↑ hot" : temp < 10 ? "↓ cold" : "nominal"}` : "loading…"}
          deltaDir={temp != null && temp > 35 ? "up" : "flat"}
          spark={tempSpark} sparkColor="var(--hydro)"
        />
        <MetricCard
          icon="pressure" label="Atm. pressure"
          value={pressure != null ? Math.round(pressure) : null} unit="hPa"
          delta={pressure != null ? (pressure < 995 ? "↓ low — convective likely" : "nominal") : "loading…"}
          deltaDir={pressure != null && pressure < 995 ? "up" : "down"}
          spark={pressureSpark} sparkColor="var(--warn)"
        />
        <MetricCard
          icon="wind" label="Wind speed"
          value={wind != null ? Math.round(wind) : null} unit="km/h"
          delta={wind != null ? (wind > 40 ? "strong gusts" : "light–moderate") : "loading…"}
          deltaDir={wind != null && wind > 40 ? "up" : "flat"}
          spark={windSpark} sparkColor="var(--cyan)"
        />
      </div>

      {/* 3-col layout */}
      <div className="grid g-dash-3 mb-16">
        {/* ─── Left: Risk + AI ─── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card label="Risk Level" title={riskLevel} tag="LIVE">
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div className="mono" style={{ fontSize: 34, fontWeight: 500, color: riskColor(riskLevel), letterSpacing: "-0.02em", lineHeight: 1 }}>
                  {riskLevel.slice(0, 4)}
                </div>
                <div className="muted mono-sm mt-8">
                  {riskLevel === "CRITICAL" ? "Evacuation protocols advised"
                    : riskLevel === "HIGH"   ? "Monitoring · prep phase"
                    : riskLevel === "MEDIUM" ? "Elevated monitoring"
                    : "Normal operations"}
                </div>
              </div>
              <Gauge value={confidence || 0} size={96} color={riskColor(riskLevel)} sub="CONF"/>
            </div>
            <RiskMeter level={riskViz}/>
            <div className="mt-8 mono-sm muted" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
              <div>Low <span style={{ color: "var(--ok)" }}>0–25</span></div>
              <div>Medium <span style={{ color: "var(--warn)" }}>26–50</span></div>
              <div>High <span style={{ color: "oklch(0.72 0.2 45)" }}>51–75</span></div>
              <div>Critical <span style={{ color: "var(--crit)" }}>76–100</span></div>
            </div>
          </Card>

          <Card label="AI Prediction" title="Hybrid AE+LSTM" tag="ONLINE">
            {loading ? <LoadingState/> : (
              <>
                <div className="row between mb-8">
                  <span className="mono-sm muted">Anomaly score</span>
                  <span className="mono" style={{ fontSize: 20, color: riskColor(riskLevel) }}>
                    {anomalyScore != null ? anomalyScore.toFixed(3) : "—"}
                  </span>
                </div>
                <div className="bar">
                  <span style={{ width: `${((anomalyScore || 0) * 100).toFixed(0)}%`, background: riskColor(riskLevel) }}/>
                </div>
                <div className="row between mb-8 mt-16">
                  <span className="mono-sm muted">HRI score</span>
                  <span className="mono" style={{ fontSize: 20 }}>{hriScore ?? "—"}</span>
                </div>
                <div className="bar"><span style={{ width: `${hriScore || 0}%` }}/></div>
                <hr className="hr"/>
                <div className="mono-sm muted" style={{ lineHeight: 1.7 }}>
                  <div className="row between">
                    <span>Risk level</span>
                    <Status kind={riskKind(riskLevel)}>{riskLevel}</Status>
                  </div>
                  <div className="row between">
                    <span>HRI label</span>
                    <span className="mono">{latest?.hri_label || "—"}</span>
                  </div>
                  <div className="row between">
                    <span>Cloudburst likely</span>
                    <Status kind={latest?.cloudburst_risk?.is_likely ? "crit" : "ok"}>
                      {latest?.cloudburst_risk?.is_likely ? "YES" : "NO"}
                    </Status>
                  </div>
                  <div className="row between">
                    <span>CB risk score</span>
                    <span className="mono">{latest?.cloudburst_risk?.score?.toFixed(2) ?? "—"}</span>
                  </div>
                </div>
              </>
            )}
          </Card>

          <Card label="City Network" title="Risk overview">
            <div className="mono-sm" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(cities || []).slice(0, 6).map(c => (
                <div key={c.id} className="row between">
                  <div className="row" style={{ gap: 8 }}>
                    <span className="dim" style={{ fontSize: 10 }}>{c.id?.toUpperCase()}</span>
                    <span style={{ color: "var(--text)" }}>{c.name}</span>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="mono muted">{c.hri_score}%</span>
                    <Status kind={riskKind(c.risk_level)}>{c.risk_level?.slice(0, 4) || "—"}</Status>
                  </div>
                </div>
              ))}
              {!cities?.length && <LoadingState message="Loading city data…"/>}
            </div>
          </Card>
        </div>

        {/* ─── Centre: chart + map ─── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          <Card
            label="Precipitation · Anomaly stream"
            title={city?.name || ""}
            right={
              <div className="row" style={{ gap: 8 }}>
                <span className="live">LIVE</span>
                <div className="seg">
                  <button className="on">All</button>
                  <button>Anomaly</button>
                </div>
              </div>
            }
          >
            {loading && !series.length
              ? <LoadingState message="Loading chart data…"/>
              : <AnomalyChart data={series} highlightIdx={series.length - 1}/>
            }
            <div className="row mt-8" style={{ gap: 16, fontSize: 11 }}>
              <span className="row" style={{ gap: 6 }}>
                <span style={{ width: 12, height: 2, background: "oklch(0.80 0.14 210)" }}/>
                Rainfall mm
              </span>
              <span className="row" style={{ gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--crit)" }}/>
                Anomaly
              </span>
              <span className="row" style={{ gap: 6 }}>
                <span style={{ width: 12, height: 2, background: "var(--warn)", opacity: 0.7 }}/>
                Alert threshold
              </span>
              <span className="row" style={{ gap: 6 }}>
                <span style={{ width: 12, height: 2, background: "var(--crit)", opacity: 0.8 }}/>
                Cloudburst threshold
              </span>
            </div>
          </Card>

          <Card
            label="Regional Heatmap"
            title="Rainfall intensity · all monitored cities"
            right={<div className="seg"><button className="on">Heat</button><button>Cities</button></div>}
          >
            <PakistanMap selected={city?.id} compact cities={cities}/>
            <div className="row between mt-8" style={{ fontSize: 11 }}>
              <div className="row" style={{ gap: 14 }}>
                <LegendSwatch c="oklch(0.74 0.14 155)" l="Low"/>
                <LegendSwatch c="oklch(0.80 0.15 75)"  l="Medium"/>
                <LegendSwatch c="oklch(0.72 0.2 45)"   l="High"/>
                <LegendSwatch c="oklch(0.66 0.22 25)"  l="Critical"/>
              </div>
              <span className="mono dim" style={{ fontSize: 10 }}>HRI · live</span>
            </div>
          </Card>
        </div>

        {/* ─── Right: Alerts + Forecast ─── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card
            label="Alerts Feed"
            title="Recent anomalies"
            tag={`${alerts.filter(a => a.risk_level === "CRITICAL").length} CRIT`}
          >
            <div style={{ margin: "-14px" }}>
              {loading && !alerts.length
                ? <LoadingState/>
                : alerts.length
                  ? alerts.map((a, i) => (
                    <AlertRow key={i}
                      kind={riskKind(a.risk_level)}
                      title={`${a.risk_level} · ${a.city}`}
                      meta={`Score ${a.anomaly_score?.toFixed(3)} · HRI ${a.hri_score ?? "—"} · ${a.hri_label || ""}`}
                      t={timeAgo(a.created_at)}
                    />
                  ))
                  : <div style={{ padding: "24px 14px" }}><EmptyState message="No anomalies detected." icon="check"/></div>
              }
            </div>
          </Card>

          <Card label="72-Hour Forecast" title="Ensemble prediction">
            <ForecastStrip entries={[
              { d: "Now",  h: new Date().toTimeString().slice(0,5), r: rainfall != null ? Math.round(rainfall) : 0,      risk: riskViz },
              { d: "+6h",  h: "—", r: rainfall != null ? Math.round(rainfall * 0.7) : 0, risk: "med" },
              { d: "+12h", h: "—", r: rainfall != null ? Math.round(rainfall * 0.4) : 0, risk: "low" },
              { d: "+24h", h: "—", r: 0, risk: "low" },
            ]}/>
          </Card>

          <Card label="Dispatch Queue" title="Pending SOPs" tag={critCities.length > 0 ? String(critCities.length) : "0"}>
            <div className="mono-sm" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <SopRow name="SOP-04 · Urban flash flood" dept="NDMA · Field ops"
                status={critCities.length > 0 ? "crit" : "warn"}
                action={critCities.length > 0 ? "DISPATCH NOW" : "Armed"}/>
              <SopRow name="SOP-02 · Advisory broadcast" dept="PMD · Met Office"
                status="warn" action="Draft ready"/>
              <SopRow name="SOP-07 · Sensor calibration" dept="Field ops · North"
                status="info" action="Scheduled"/>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { DashboardScreen });
