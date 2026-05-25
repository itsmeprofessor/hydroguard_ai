/**
 * HydroGuard — Citizen App Screens
 * Adapted from the zip design for web deployment.
 * Screens: Home, Forecast, Alerts, Learn, Settings
 *
 * Data flows in via props from the root App component which
 * calls HydroAPI to fetch live data from the backend.
 */

const { useState, useEffect, useCallback } = React;

// ─── Scenario helpers ────────────────────────────────────────────────────────

const SCENARIO_META = {
  safe: {
    bgClass: "scr-safe", headlineClass: "safe", iconBg: "safe",
    pillChip: "safe", pillText: "Safe to go outside",
    headlineText: "All clear",
    subText: "No flood or cloudburst risk detected in your area.",
  },
  warn: {
    bgClass: "scr-warn", headlineClass: "warn", iconBg: "warn",
    pillChip: "warn", pillText: "Be prepared",
    headlineText: "Heads up",
    subText: "Heavy rain expected. Stay alert in low-lying areas.",
  },
  crit: {
    bgClass: "scr-crit", headlineClass: "crit", iconBg: "crit",
    pillChip: "crit", pillText: "High risk — stay alert",
    headlineText: "High risk alert",
    subText: "Extreme rainfall detected. Avoid low-lying areas.",
  },
};

/**
 * Map a risk level string to a UI scenario.
 * Accepts v1 (risk_level: Low/Medium/High/Critical) and
 * v2 (risk_band: Low/Moderate/High/Severe) values.
 */
function riskToScenario(riskLevel) {
  if (!riskLevel) return "safe";
  const r = riskLevel.toLowerCase();
  if (r === "high" || r === "critical" || r === "severe") return "crit";
  if (r === "medium" || r === "moderate" || r === "elevated") return "warn";
  return "safe";
}

/**
 * Normalise a v1 or v2 prediction response to a consistent shape used by all
 * screens. v1 returns risk_level/anomaly_score/confidence/is_anomaly;
 * v2 returns risk_band/event_probability/uncertainty/is_alert.
 */
function normRisk(d) {
  if (!d) return d;
  return {
    ...d,
    // canonical risk label — prefer v2 risk_band
    risk_label:       d.risk_band      ?? d.risk_level      ?? "Low",
    // probability 0‑1 — prefer v2 event_probability
    prob:             d.event_probability ?? d.anomaly_score ?? null,
    // alert flag — prefer v2 is_alert
    alerting:         d.is_alert       ?? d.is_anomaly      ?? false,
    // confidence 0‑1 — derive from v2 uncertainty or v1 confidence
    conf: d.confidence != null
      ? d.confidence
      : (d.uncertainty != null ? Math.max(0, 1 - d.uncertainty) : null),
  };
}

function scenarioPalette(scenario) {
  if (scenario === "crit") return { color: "var(--c-crit)", soft: "var(--c-crit-soft)" };
  if (scenario === "warn") return { color: "#D97706",       soft: "var(--c-warn-soft)" };
  return                         { color: "var(--c-ok)",    soft: "var(--c-ok-soft)" };
}

// ─── Inline SVG mini chart for forecast strip ────────────────────────────────
const ForecastChart = ({ data, scenario }) => {
  const w = 360, h = 140, pad = { t: 16, r: 12, b: 24, l: 32 };
  const max = Math.max(...(data || []).map(d => d.prcp || 0), 20);
  const step = (w - pad.l - pad.r) / Math.max((data || []).length - 1, 1);
  const yf = v => pad.t + (h - pad.t - pad.b) * (1 - v / max);
  const xf = i => pad.l + i * step;
  const line = (data || []).map((d, i) => `${i === 0 ? "M" : "L"}${xf(i).toFixed(1)},${yf(d.prcp || 0).toFixed(1)}`).join(" ");
  const area = `${line} L${xf((data || []).length - 1)},${h - pad.b} L${pad.l},${h - pad.b} Z`;
  const c = scenario === "crit" ? "#DC2626" : scenario === "warn" ? "#D97706" : "#2563EB";
  if (!data || !data.length) return null;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="fcGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity="0.28"/>
          <stop offset="100%" stopColor={c} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0, max / 2, max].map((t, idx) => (
        <g key={idx}>
          <line x1={pad.l} x2={w - pad.r} y1={yf(t)} y2={yf(t)} stroke="#E6EAF0" strokeWidth="1" strokeDasharray="2 3"/>
          <text x={pad.l - 5} y={yf(t) + 3.5} fontSize="9" textAnchor="end" fill="#9AA4B2">{Math.round(t)}</text>
        </g>
      ))}
      <path d={area} fill="url(#fcGrad)"/>
      <path d={line} stroke={c} strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      {data.map((d, i) => (
        <text key={i} x={xf(i)} y={h - 6} fontSize="9" textAnchor="middle" fill="#9AA4B2">{d.day_short || d.day_name?.slice(0, 3)}</text>
      ))}
    </svg>
  );
};

// ─── Risk Meter ──────────────────────────────────────────────────────────────
const RiskMeter = ({ score = 0, scenario }) => {
  const pct = Math.min(Math.max(score, 0), 100);
  const color = scenario === "crit" ? "#DC2626" : scenario === "warn" ? "#D97706" : "#16A34A";
  const r = 52, cx = 64, cy = 64;
  const circ = 2 * Math.PI * r;
  const arc  = circ * 0.75; // 270-degree arc
  const dash = arc * (pct / 100);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <svg width="128" height="128" viewBox="0 0 128 128">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--c-line)" strokeWidth="10"
          strokeDasharray={`${arc} ${circ}`}
          strokeDashoffset={`${circ * 0.125}`}
          strokeLinecap="round" transform={`rotate(135 ${cx} ${cy})`}/>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={`${dash} ${circ}`}
          strokeDashoffset={`${circ * 0.125}`}
          strokeLinecap="round" transform={`rotate(135 ${cx} ${cy})`}
          style={{ transition: "stroke-dasharray 0.6s ease" }}/>
        <text x={cx} y={cy - 4} fontSize="22" fontWeight="700" textAnchor="middle" fill={color}
          style={{ fontFamily: "var(--c-display)", letterSpacing: "-0.02em" }}>{pct}</text>
        <text x={cx} y={cy + 15} fontSize="10" textAnchor="middle" fill="var(--c-muted)">HRI Score</text>
      </svg>
    </div>
  );
};

// ─── Loading skeleton ─────────────────────────────────────────────────────────
const Skeleton = ({ h = 20, w = "100%", r = 8 }) => (
  <div className="skeleton" style={{ height: h, width: w, borderRadius: r }}/>
);

// ─── Advice cards per scenario ────────────────────────────────────────────────
const ADVICE = {
  safe: [
    { ic: "info",   kind: "info", title: "Light showers expected this evening",      body: "Carry an umbrella if heading out around 7 PM. Roads should remain passable." },
    { ic: "shield", kind: "safe", title: "Your area is monitored continuously",       body: "HydroGuard sensors stream rainfall data every minute to keep you informed." },
  ],
  warn: [
    { ic: "umbrella", kind: "warn", title: "Avoid low-lying areas and underpasses",   body: "Nullahs and drainage channels flood quickly during heavy rain. Plan an alternate route." },
    { ic: "car",      kind: "warn", title: "Drive carefully — roads will be slippery", body: "Reduce speed and maintain extra distance from vehicles ahead." },
    { ic: "phone",    kind: "info", title: "Save emergency numbers",                   body: "Save Rescue 1122 and NDMA helpline before you need them." },
  ],
  crit: [
    { ic: "elevation", kind: "crit", title: "Move away from streams and nullahs immediately", body: "Flash floods can rise within minutes. Do not wait." },
    { ic: "family",    kind: "crit", title: "Check on family and neighbors",                   body: "Help elderly relatives and those with mobility challenges evacuate first." },
    { ic: "car",       kind: "warn", title: "Do not drive through flowing water",               body: "30 cm of moving water can sweep a car away. Turn around — don't drown." },
    { ic: "phone",     kind: "info", title: "Call Rescue 1122 if in danger",                   body: "Free emergency hotline. Available 24/7 across Pakistan." },
  ],
};

// ─── Live Weather Badge ───────────────────────────────────────────────────────
const LiveBadge = ({ isLive }) => isLive ? (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 4,
    fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
    color: "#16A34A", background: "#DCFCE7",
    border: "1px solid #BBF7D0", borderRadius: 20,
    padding: "2px 8px",
  }}>
    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#16A34A",
      boxShadow: "0 0 0 3px #BBF7D0", display: "inline-block" }}/>
    LIVE
  </span>
) : null;

// ─── HOME SCREEN ─────────────────────────────────────────────────────────────
const HomeScreen = ({ riskData, forecast, loading, onTab, city }) => {
  const rd        = normRisk(riskData);
  const scenario  = riskToScenario(rd?.risk_label);
  const meta      = SCENARIO_META[scenario];
  const pal       = scenarioPalette(scenario);
  const advice    = ADVICE[scenario];
  const hri       = rd?.hri_score ?? 0;
  // Live weather data is included in riskData when the /weather endpoint is used
  const prcp      = rd?.prcp      ?? rd?.inputs?.prcp     ?? 0;
  const pressure  = rd?.pressure  ?? rd?.inputs?.pressure ?? 1013;
  const humidity  = rd?.humidity  ?? rd?.inputs?.humidity ?? 50;
  const tmax      = rd?.tmax      ?? rd?.inputs?.tmax     ?? null;
  const wspd      = rd?.wspd      ?? rd?.inputs?.wspd     ?? null;
  const isLive    = rd?.is_live === true;
  // v2 probability display (falls back to v1 confidence)
  const confPct   = rd?.conf != null ? Math.round(rd.conf * 100) : null;
  const probPct   = rd?.prob != null ? Math.round(rd.prob * 100) : null;

  // Build hourly/daily strip from real forecast data when available.
  // The backend provides daily resolution; we show the next 7 days labelled by
  // day-name.  When forecast is unavailable, fall back to a placeholder strip
  // based on today's current readings — clearly labelled as estimates.
  const fcDays = forecast?.forecast ?? [];
  const hourStrip = fcDays.length >= 2
    ? fcDays.slice(0, 8).map((d, i) => {
        const r = Math.round(d.daily_precip_mm ?? d.prcp ?? 0);
        const label = i === 0 ? "Today" : (d.day_name?.slice(0, 3) ?? `+${i}d`);
        return {
          t:  label,
          ic: r > 50 ? "rain" : r > 10 ? "rain" : r > 0 ? "cloud" : "sun",
          r,
        };
      })
    : [
        { t: "Now",   ic: prcp > 50 ? "rain" : prcp > 10 ? "rain" : "sun",  r: prcp },
        { t: "Est.",  ic: "cloud", r: Math.round(prcp * 0.9) },
        { t: "Est.",  ic: "rain",  r: Math.round(prcp * 0.7) },
        { t: "Est.",  ic: "cloud", r: Math.round(prcp * 0.5) },
        { t: "Est.",  ic: "cloud", r: Math.round(prcp * 0.3) },
        { t: "Est.",  ic: "sun",   r: 0 },
        { t: "Est.",  ic: "sun",   r: 0 },
        { t: "Est.",  ic: "cloud", r: Math.round(prcp * 0.2) },
      ];

  return (
    <div className={`citizen-screen ${meta.bgClass}`}>
      {/* Hero card */}
      <div className="status-hero">
        <div className={`status-icon-bg ${meta.iconBg}`}/>
        <div style={{ position: "relative" }}>
          <div className="status-label">Risk level</div>
          {loading
            ? <Skeleton h={36} w={200} r={8}/>
            : <h1 className={`status-headline ${meta.headlineClass}`}>{meta.headlineText}</h1>
          }
          <p className="status-sub">{loading ? "" : meta.subText}</p>
          <div style={{ marginTop: 12 }}>
            <span className={`pill-chip ${meta.pillChip}`}><span className="dt"/>{meta.pillText}</span>
          </div>
        </div>

        {/* Live badge */}
        {!loading && <div style={{ marginBottom: 6 }}><LiveBadge isLive={isLive}/></div>}

        {/* Metrics row */}
        <div className="metrics-row">
          <div className="metric-tile">
            <div className="ic" style={{ background: pal.soft, color: pal.color }}><CIcon name="droplet" size={16}/></div>
            {loading ? <Skeleton h={24} r={4}/> : <div className="v">{Number(prcp).toFixed(0)}<small>mm</small></div>}
            <div className="l">Rainfall</div>
          </div>
          <div className="metric-tile">
            <div className="ic" style={{ background: "var(--c-blue-soft)", color: "var(--c-blue)" }}><CIcon name="therm" size={16}/></div>
            {loading ? <Skeleton h={24} r={4}/> : <div className="v">{tmax != null ? `${tmax}` : "—"}<small>°C</small></div>}
            <div className="l">Temp</div>
          </div>
          <div className="metric-tile">
            <div className="ic" style={{ background: "#EFF6FF", color: "#2563EB" }}><CIcon name="droplet" size={16}/></div>
            {loading ? <Skeleton h={24} r={4}/> : <div className="v">{humidity}<small>%</small></div>}
            <div className="l">Humidity</div>
          </div>
          <div className="metric-tile">
            <div className="ic" style={{ background: pal.soft, color: pal.color }}><CIcon name="shield" size={16}/></div>
            {loading ? <Skeleton h={24} r={4}/> : <div className="v">{rd?.risk_label ?? "—"}</div>}
            <div className="l">Risk</div>
          </div>
        </div>

        {/* HRI meter */}
        {!loading && <div style={{ marginTop: 16, display: "flex", justifyContent: "center" }}>
          <RiskMeter score={hri} scenario={scenario}/>
        </div>}
      </div>

      {/* Action banner for warn/crit */}
      {!loading && scenario !== "safe" && (
        <div className={`action-banner ${scenario === "crit" ? "" : "warn"}`}>
          <span className="pulse"/>
          <h4>{scenario === "crit" ? "ELEVATED FLOOD RISK" : "Heavy rain advisory"}</h4>
          <p>
            {probPct != null ? `P(event) ${probPct}%` : confPct != null ? `Confidence ${confPct}%` : ""}
            {" · HRI "}{hri}/100 · {city}
          </p>
          <button onClick={() => onTab("alerts")}>View alerts <CIcon name="arrow" size={14}/></button>
        </div>
      )}

      {/* Hourly strip */}
      <div className="sec-head">
        <h3>Next 24 hours</h3>
        <a onClick={() => onTab("forecast")} style={{ cursor: "pointer" }}>See all</a>
      </div>
      <div className="fc-strip">
        {hourStrip.map((h, i) => (
          <div key={i} className={`fc-hour ${i === 0 ? "now" : ""}`}>
            <div className="t">{h.t}</div>
            <div className="ic">
              <CIcon name={h.ic} size={20}
                color={i === 0 ? "white" : h.r > 50 ? "var(--c-blue)" : h.r > 0 ? "var(--c-cyan)" : "#F59E0B"}/>
            </div>
            <div className="r">{h.r}<small>mm</small></div>
          </div>
        ))}
      </div>

      {/* What to do */}
      <div className="sec-head">
        <h3>What to do</h3>
        <a onClick={() => onTab("learn")} style={{ cursor: "pointer" }}>Learn more</a>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {advice.map((a, i) => (
          <div key={i} className="tip-card">
            <div className={`ic-wrap ${a.kind}`}><CIcon name={a.ic} size={18}/></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h4>{a.title}</h4>
              <p>{a.body}</p>
            </div>
            <CIcon name="chevron" size={16} color="var(--c-dim)"/>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── FORECAST SCREEN ─────────────────────────────────────────────────────────
const ForecastScreen = ({ forecast, riskData, loading, city }) => {
  const rd       = normRisk(riskData);
  const scenario = riskToScenario(rd?.risk_label);
  // v2 forecast days use daily_precip_mm + event_probability; v1 uses prcp + risk_level
  const rawDays  = forecast?.forecast ?? [];
  const days = rawDays.map(d => ({
    ...d,
    prcp:       d.daily_precip_mm ?? d.prcp ?? 0,
    risk_level: d.risk_band       ?? d.risk_level ?? "Low",
    tmax:       d.max_temp_c      ?? d.tmax ?? null,
    tmin:       d.min_temp_c      ?? d.tmin ?? null,
  }));

  const dayIcon = (fc) => {
    if (fc.prcp > 60) return "rain";
    if (fc.prcp > 15) return "rain";
    if (fc.prcp > 3)  return "cloud";
    return "sun";
  };
  const dayKind = (fc) => riskToScenario(fc.risk_level);

  return (
    <div className="citizen-screen scr-safe">
      {/* Chart */}
      <div className="c-card">
        <div className="c-card-bd">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 13, color: "var(--c-muted)" }}>7-day forecast · {city}</div>
              {loading
                ? <Skeleton h={28} w={160} r={4}/>
                : <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em" }}>
                    Peak <span style={{ color: scenario === "crit" ? "var(--c-crit)" : scenario === "warn" ? "#D97706" : "var(--c-blue)" }}>
                      {Math.max(...days.map(d => d.prcp || 0), 0).toFixed(0)}mm
                    </span>
                  </div>
              }
            </div>
            <span className={`pill-chip ${scenario}`}><span className="dt"/>{rd?.risk_label ?? "—"} risk</span>
          </div>
          {!loading && days.length > 0 && (
            <ForecastChart
              data={days.map(d => ({
                ...d,
                day_short: d.day_name?.slice(0, 3) ?? d.date?.slice(5),
                prcp: d.prcp || 0,
              }))}
              scenario={scenario}
            />
          )}
          {loading && <Skeleton h={130} r={8}/>}
        </div>
      </div>

      <div className="sec-head"><h3>This week</h3></div>
      {loading
        ? Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} h={56} r={12} style={{ marginBottom: 10 }}/>)
        : days.map((day, i) => {
            const kind = dayKind(day);
            return (
              <div key={i} className="day-card">
                <div className="day">{day.day_name}<small>{day.date}</small></div>
                <CIcon name={dayIcon(day)} size={26}
                  color={kind === "crit" ? "var(--c-crit)" : kind === "warn" ? "#D97706" : kind === "safe" ? "#16A34A" : "var(--c-blue)"}/>
                <div className="name">
                  {day.risk_level} risk
                  <small>
                    <span className={`pill-chip ${kind}`} style={{ padding: "2px 8px", fontSize: 10 }}>
                      <span className="dt"/>{day.risk_level}
                    </span>
                  </small>
                </div>
                <div className="rain">{(day.prcp || 0).toFixed(0)}mm<small>/h</small></div>
              </div>
            );
          })
      }

      <div className="sec-head"><h3>About this forecast</h3></div>
      <div className="tip-card">
        <div className="ic-wrap info"><CIcon name="info" size={18}/></div>
        <div style={{ flex: 1 }}>
          <h4>How HydroGuard predicts</h4>
          <p>City-specific AI models (Autoencoder + LSTM + Attention) analyse real-time sensor data and historical patterns to detect anomalies and project risk.</p>
        </div>
      </div>
    </div>
  );
};

// ─── ALERTS SCREEN ───────────────────────────────────────────────────────────
const AlertsScreen = ({ alerts, riskData, loading, city }) => {
  const rd       = normRisk(riskData);
  const scenario = riskToScenario(rd?.risk_label);
  const [filter, setFilter] = useState("all");  // "all" | "crit" | "warn" | "info"

  // Build live alerts from real backend response.
  // v2 shape: { inference_id, risk_band, is_alert, event_probability, inferred_at, source }
  // v1 shape: { id, risk_level, is_anomaly, anomaly_score, ts, score }
  const liveAlerts = (alerts?.alerts ?? []).map(a => {
    const riskLabel = a.risk_band ?? a.risk_level ?? "Low";
    const probPct   = a.event_probability != null
      ? Math.round(a.event_probability * 100)
      : a.score != null ? Math.round(a.score * 100) : null;
    const ts = a.inferred_at ?? a.ts;
    return {
      kind:  riskToScenario(riskLabel),
      scope: "area",
      t:     ts ? new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—",
      title: `${riskLabel} flood event detected`,
      meta:  `HydroGuard · ${city}${probPct != null ? ` · P(event) ${probPct}%` : ""}`,
      body:  probPct != null
        ? `Model event probability ${probPct}%. Exercise caution in low-lying areas.`
        : `Anomaly detected. Exercise caution in low-lying areas.`,
    };
  });

  // Contextual fallback alerts — only shown when the backend returns no live data.
  const staticAlerts = scenario === "crit" ? [
    { kind: "crit", scope: "area",     t: "Now",      title: "Elevated flood risk",     meta: `HydroGuard AI · ${city}`, body: "Model confidence high. Avoid areas prone to flash flooding." },
    { kind: "warn", scope: "national", t: "Earlier",  title: "Heavy rain advisory",     meta: "PMD · Regional",          body: "Convective activity detected. Rainfall expected above seasonal average." },
    { kind: "info", scope: "national", t: "Seasonal", title: "Monsoon season active",   meta: "HydroGuard · seasonal",   body: "Review your emergency kit and update your family's evacuation plan." },
  ] : scenario === "warn" ? [
    { kind: "warn", scope: "area",     t: "Now",      title: "Heavy rain advisory",     meta: `HydroGuard AI · ${city}`, body: "Stay alert and avoid underpasses and nullah crossings." },
    { kind: "info", scope: "national", t: "Seasonal", title: "Monsoon season active",   meta: "HydroGuard · seasonal",   body: "Drainage capacity is near limit in some urban areas." },
  ] : [
    { kind: "info", scope: "area",     t: "Today",    title: "All clear",               meta: `HydroGuard AI · ${city}`, body: "No flood risk detected. Light showers possible this evening." },
    { kind: "info", scope: "national", t: "Seasonal", title: "Monsoon season watch",    meta: "HydroGuard · seasonal",   body: "Conditions can change rapidly. Keep HydroGuard notifications on." },
  ];

  // Show live alerts if available; fall back to contextual static alerts.
  const allDisplayAlerts = liveAlerts.length > 0 ? liveAlerts : staticAlerts;

  // Apply filter
  const filteredAlerts = filter === "all"
    ? allDisplayAlerts
    : filter === "area"
    ? allDisplayAlerts.filter(a => a.scope === "area")
    : allDisplayAlerts.filter(a => a.scope === "national");

  const pillStyle = (id) => ({
    cursor: "pointer",
    background: filter === id ? "var(--c-text)" : undefined,
    color:      filter === id ? "white" : undefined,
  });

  return (
    <div className="citizen-screen scr-safe">
      {/* Filter pills — now functional */}
      <div style={{ display: "flex", gap: 8, paddingBottom: 14, overflowX: "auto" }}>
        <span className="pill-chip" style={pillStyle("all")}  onClick={() => setFilter("all")}>All</span>
        <span className="pill-chip" style={pillStyle("area")} onClick={() => setFilter("area")}>My area</span>
        <span className="pill-chip" style={pillStyle("national")} onClick={() => setFilter("national")}>National</span>
      </div>

      {loading
        ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} h={90} r={14} style={{ marginBottom: 10 }}/>)
        : filteredAlerts.length === 0
        ? <p style={{ color: "var(--c-dim)", textAlign: "center", marginTop: 32 }}>No alerts for this filter.</p>
        : filteredAlerts.map((a, i) => (
          <div key={i} className={`alert-item ${a.kind}`}>
            <div className="stripe"/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <h4>{a.title}</h4>
                <span className="t">{a.t}</span>
              </div>
              <div className="meta">{a.meta}</div>
              <div className="body">{a.body}</div>
              {a.kind !== "info" && (
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button style={{ background: "var(--c-text)", color: "white", border: "none", borderRadius: 8, padding: "7px 12px", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>Safety steps</button>
                </div>
              )}
            </div>
          </div>
        ))
      }
    </div>
  );
};

// ─── LEARN SCREEN ────────────────────────────────────────────────────────────
const LearnScreen = () => {
  const cards = [
    { t: "What is a cloudburst?",     read: "2 min", ic: "cloud",    color: "#2563EB", bg: "var(--c-blue-soft)" },
    { t: "How flash floods form",     read: "3 min", ic: "waves",    color: "#0891B2", bg: "var(--c-cyan-soft)" },
    { t: "Building an emergency kit", read: "4 min", ic: "medkit",   color: "#DC2626", bg: "var(--c-crit-soft)" },
    { t: "Driving in heavy rain",     read: "2 min", ic: "car",      color: "#D97706", bg: "var(--c-warn-soft)" },
    { t: "Helping elderly neighbors", read: "3 min", ic: "family",   color: "#16A34A", bg: "var(--c-ok-soft)"   },
    { t: "Reading weather warnings",  read: "5 min", ic: "book",     color: "#7C3AED", bg: "#EDE9FE"            },
  ];
  return (
    <div className="citizen-screen scr-safe">
      {/* Hero guide */}
      <div style={{
        background: "linear-gradient(135deg, #1E40AF 0%, #2563EB 60%, #0891B2 100%)",
        color: "white", borderRadius: 22, padding: "22px 20px",
        position: "relative", overflow: "hidden", marginBottom: 20,
      }}>
        <div style={{ position: "absolute", right: -20, top: -20, opacity: 0.14 }}>
          <CIcon name="cloud" size={140} stroke={1.2} color="white"/>
        </div>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", opacity: 0.85, textTransform: "uppercase" }}>Featured guide</div>
        <h2 style={{ margin: "6px 0 6px", fontSize: 22, fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.15 }}>What to do in a cloudburst</h2>
        <p style={{ fontSize: 13, opacity: 0.9, margin: 0, maxWidth: 280 }}>Five simple steps that can save your life when extreme rainfall hits your area.</p>
        <button style={{ marginTop: 14, background: "white", color: "#1E40AF", border: "none", borderRadius: 10, padding: "9px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <CIcon name="play" size={13}/>Read guide
        </button>
      </div>

      <div className="sec-head" style={{ marginTop: 0 }}><h3>Topics</h3></div>
      <div className="learn-grid">
        {cards.map((c, i) => (
          <div key={i} className="learn-card">
            <div className="ic-lg" style={{ background: c.bg, color: c.color }}><CIcon name={c.ic} size={22}/></div>
            <div>
              <h4>{c.t}</h4>
              <div className="read">{c.read} read</div>
            </div>
          </div>
        ))}
      </div>

      <div className="sec-head"><h3>Emergency contacts</h3></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[
          { name: "Rescue 1122",     num: "1122",             desc: "Free emergency hotline",  color: "var(--c-crit)", bg: "var(--c-crit-soft)" },
          { name: "NDMA Helpline",   num: "051-111-157-157",  desc: "National Disaster Mgmt",  color: "var(--c-blue)", bg: "var(--c-blue-soft)" },
          { name: "Edhi Foundation", num: "115",              desc: "Ambulance & rescue",      color: "#16A34A",       bg: "var(--c-ok-soft)"   },
        ].map((e, i) => (
          <div key={i} className="tip-card">
            <div className="ic-wrap" style={{ background: e.bg, color: e.color }}><CIcon name="phone" size={18}/></div>
            <div style={{ flex: 1 }}>
              <h4>{e.name}</h4>
              <p>{e.desc} · <span style={{ fontFamily: "var(--c-mono)", color: e.color, fontWeight: 600 }}>{e.num}</span></p>
            </div>
            <a href={`tel:${e.num}`}>
              <button style={{ background: e.color, color: "white", border: "none", borderRadius: 100, padding: "8px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>Call</button>
            </a>
          </div>
        ))}
      </div>
    </div>
  );
};

// Export to window
Object.assign(window, {
  HomeScreen, ForecastScreen, AlertsScreen, LearnScreen,
  ForecastChart, RiskMeter, Skeleton, SCENARIO_META, riskToScenario, normRisk,
});
