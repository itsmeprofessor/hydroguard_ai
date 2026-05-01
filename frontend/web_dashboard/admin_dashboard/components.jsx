// HydroGuard AI — Shared UI primitives
// All components are exported to window for cross-file use.

const { useState, useEffect, useRef } = React;

/* ── SVG Icon library ─────────────────────────────────────────────── */
const Icon = ({ name, size = 16 }) => {
  const paths = {
    dashboard:  <><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></>,
    cloudburst: <><path d="M7 15a4 4 0 1 1 .7-7.94A6 6 0 0 1 20 11a3 3 0 0 1 0 6H7z"/><path d="M8 19l-1 3M12 19l-1 3M16 19l-1 3"/></>,
    flood:      <><path d="M2 16c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2"/><path d="M2 20c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2"/><path d="M12 2l3 6H9z"/></>,
    monitor:    <><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="M7 10l2 2 3-4 2 3 2-1"/></>,
    analytics:  <><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-6"/></>,
    city:       <><rect x="3" y="10" width="6" height="11"/><rect x="10" y="4" width="6" height="17"/><rect x="17" y="13" width="4" height="8"/><path d="M12 7h2M12 10h2M12 13h2M12 16h2M5 13h2M5 16h2"/></>,
    settings:   <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></>,
    user:       <><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/></>,
    bell:       <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></>,
    search:     <><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></>,
    chevron:    <><path d="m9 6 6 6-6 6"/></>,
    chevronDown:<><path d="m6 9 6 6 6-6"/></>,
    plus:       <><path d="M12 5v14M5 12h14"/></>,
    download:   <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/></>,
    refresh:    <><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></>,
    alert:      <><path d="M12 2 2 20h20L12 2z"/><path d="M12 9v5M12 18v.01"/></>,
    close:      <><path d="m18 6-12 12M6 6l12 12"/></>,
    map:        <><path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15M15 6v15"/></>,
    droplet:    <><path d="M12 2s6 7 6 12a6 6 0 1 1-12 0c0-5 6-12 6-12z"/></>,
    gauge:      <><path d="M12 14l4-4"/><path d="M20 12a8 8 0 1 0-14.9 4"/><circle cx="12" cy="14" r="1.5"/></>,
    wind:       <><path d="M9.6 4.6A2 2 0 1 1 11 8H2M12.6 19.4A2 2 0 1 0 14 16H2M17.5 8a2.5 2.5 0 1 1 2 4H2"/></>,
    therm:      <><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></>,
    pressure:   <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></>,
    zap:        <><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></>,
    check:      <><path d="m5 12 5 5L20 7"/></>,
    brain:      <><path d="M12 2a3 3 0 0 0-3 3v1c-1.5 0-3 1.5-3 3s1.5 3 3 3v1a3 3 0 0 0 6 0v-1c1.5 0 3-1.5 3-3s-1.5-3-3-3V5a3 3 0 0 0-3-3z"/><path d="M12 10v8M12 18a3 3 0 0 1-6 0c0-1 .5-2 1-2M12 18a3 3 0 0 0 6 0c0-1-.5-2-1-2"/></>,
    filter:     <><path d="M3 4h18l-7 9v7l-4-2v-5L3 4z"/></>,
    clock:      <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    lock:       <><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
    mail:       <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 7 9-7"/></>,
    logout:     <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></>,
    arrow:      <><path d="M5 12h14M13 5l7 7-7 7"/></>,
    eye:        <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>,
    shield:     <><path d="M12 2 4 6v6c0 5 4 9 8 10 4-1 8-5 8-10V6l-8-4z"/></>,
    radio:      <><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.5M7.8 16.2a6 6 0 0 1 0-8.5M19 5a10 10 0 0 1 0 14M5 19a10 10 0 0 1 0-14"/></>,
    play:       <><path d="M6 4v16l14-8z"/></>,
    pause:      <><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></>,
    server:     <><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/></>,
    copy:       <><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>,
    trash:      <><path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></>,
    externalLink:<><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/></>,
  };
  return (
    <svg viewBox="0 0 24 24" width={size} height={size}
      fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name] || null}
    </svg>
  );
};

/* ── Brand mark ────────────────────────────────────────────────────── */
const BrandMark = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
    <defs>
      <linearGradient id="bm-g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%"   stopColor="oklch(0.80 0.14 210)"/>
        <stop offset="100%" stopColor="oklch(0.55 0.18 250)"/>
      </linearGradient>
    </defs>
    <path d="M16 3 5 7v9c0 6 5 11 11 13 6-2 11-7 11-13V7L16 3z"
      fill="url(#bm-g)" opacity="0.95"/>
    <path d="M16 10s4 4.5 4 8a4 4 0 1 1-8 0c0-3.5 4-8 4-8z"
      fill="white" opacity="0.92"/>
    <circle cx="14.5" cy="18.5" r="1" fill="oklch(0.55 0.18 250)" opacity="0.7"/>
  </svg>
);

/* ── Sparkline SVG ─────────────────────────────────────────────────── */
const Sparkline = ({ data, color = "var(--cyan)", width = 140, height = 36, fill = true, strokeWidth = 1.4 }) => {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((v, i) => [i * step, height - ((v - min) / range) * (height - 4) - 2]);
  const d = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const fillD = `${d} L${width},${height} L0,${height} Z`;
  const id = `sp-${Math.random().toString(36).slice(2, 8)}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.35"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {fill && <path d={fillD} fill={`url(#${id})`}/>}
      <path d={d} stroke={color} strokeWidth={strokeWidth} fill="none"
        strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
};

/* ── Gauge (semi-circle) ────────────────────────────────────────────── */
const Gauge = ({ value = 0, size = 96, color = "var(--cyan)", sub = "" }) => {
  const r = size / 2 - 8;
  const cx = size / 2, cy = size / 2;
  const arc = (pct) => {
    const a = Math.PI * (1 + pct);
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  };
  const p = Math.min(Math.max((value) / 100, 0), 1);
  const end = arc(p);
  const start = { x: cx - r, y: cy };
  const large = p > 0.5 ? 1 : 0;
  const bg = `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy}`;
  const fg = p === 0 ? '' : `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y}`;
  return (
    <div className="gauge-wrap" style={{ width: size, height: size / 2 + 10 }}>
      <svg width={size} height={size / 2 + 4} viewBox={`0 0 ${size} ${size / 2 + 4}`}>
        <path d={bg} fill="none" stroke="var(--panel-3)" strokeWidth="5" strokeLinecap="round"/>
        {fg && <path d={fg} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"/>}
        <text x={cx} y={cy + 2} textAnchor="middle"
          fontSize="14" fill="var(--text)" fontFamily="var(--mono)" fontWeight="500">
          {value}%
        </text>
      </svg>
      {sub && <div className="gauge-sub">{sub}</div>}
    </div>
  );
};

/* ── Risk meter bar ────────────────────────────────────────────────── */
const RiskMeter = ({ level }) => {
  const lvl = ["low", "med", "high", "crit"];
  const idx = lvl.indexOf(level);
  return (
    <div className="risk-meter">
      {lvl.map((l, i) => (
        <div key={l} className={`risk-seg ${i <= idx ? "on " + l : ""}`}/>
      ))}
    </div>
  );
};

/* ── Status badge ──────────────────────────────────────────────────── */
const Status = ({ kind = "ok", children }) => (
  <span className={`status ${kind}`}><span className="dt"/>{children}</span>
);

/* ── Chip ───────────────────────────────────────────────────────────── */
const Chip = ({ kind = "", children }) => (
  <span className={`chip ${kind}`}><span className="dot"/>{children}</span>
);

/* ── Card ───────────────────────────────────────────────────────────── */
const Card = ({ title, label, tag, right, children, style, className = "" }) => (
  <div className={`card ${className}`} style={style}>
    {(title || label || tag || right) && (
      <div className="card-hd">
        {label && <span className="label">{label}</span>}
        {title && <h3>{title}</h3>}
        <div className="spacer"/>
        {tag && <span className="tag">{tag}</span>}
        {right}
      </div>
    )}
    <div className="card-bd">{children}</div>
  </div>
);

/* ── Loading spinner ────────────────────────────────────────────────── */
const Spinner = ({ size = 20 }) => (
  <div className="spinner" style={{ width: size, height: size }}/>
);

/* ── Loading state placeholder ──────────────────────────────────────── */
const LoadingState = ({ message = "Loading…" }) => (
  <div className="loading-state">
    <Spinner size={18}/>
    <span>{message}</span>
  </div>
);

/* ── Error state ────────────────────────────────────────────────────── */
const ErrorState = ({ message, onRetry }) => (
  <div className="error-state">
    <Icon name="alert" size={14}/>
    <span style={{ flex: 1 }}>{message || "An error occurred."}</span>
    {onRetry && (
      <button className="btn" style={{ padding: "3px 10px", fontSize: 11 }} onClick={onRetry}>
        <Icon name="refresh" size={12}/>Retry
      </button>
    )}
  </div>
);

/* ── Empty state ────────────────────────────────────────────────────── */
const EmptyState = ({ message = "No data yet.", icon = "search" }) => (
  <div className="empty-state">
    <div className="icon"><Icon name={icon} size={28}/></div>
    <div>{message}</div>
  </div>
);

/* ── Toast manager ──────────────────────────────────────────────────── */
let _toastSetFn = null;
const ToastContainer = () => {
  const [toasts, setToasts] = useState([]);
  _toastSetFn = setToasts;
  useEffect(() => {
    if (!toasts.length) return;
    const t = setTimeout(() => setToasts(ts => ts.slice(1)), 4000);
    return () => clearTimeout(t);
  }, [toasts]);
  return (
    <div className="toast-container">
      {toasts.map((t, i) => (
        <div key={i} className={`toast ${t.kind || ""}`}>
          <Icon name={t.kind === "ok" ? "check" : t.kind === "crit" ? "alert" : "bell"} size={14}/>
          {t.msg}
        </div>
      ))}
    </div>
  );
};
const toast = (msg, kind = "") => {
  if (_toastSetFn) _toastSetFn(ts => [...ts, { msg, kind }]);
};

/* ── Anomaly chart ──────────────────────────────────────────────────── */
const AnomalyChart = ({ data = [], height = 220, highlightIdx = -1 }) => {
  if (!data.length) return <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center" }}><LoadingState message="Awaiting data…"/></div>;
  const w = 760, h = height;
  const pad = { t: 20, r: 16, b: 28, l: 36 };
  const maxV = Math.max(...data.map(d => d.rainfall || d.v || 0), 50) * 1.15;
  const xFn  = i => pad.l + i * ((w - pad.l - pad.r) / (data.length - 1));
  const yFn  = v => pad.t + (1 - v / maxV) * (h - pad.t - pad.b);
  const line = data.map((d, i) => (i === 0 ? `M${xFn(i)},${yFn(d.rainfall || d.v || 0)}` : `L${xFn(i)},${yFn(d.rainfall || d.v || 0)}`)).join(" ");
  const fill = `${line} L${xFn(data.length - 1)},${h - pad.b} L${xFn(0)},${h - pad.b} Z`;
  const thr  = 70, cbThr = 90;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="oklch(0.80 0.14 210)" stopOpacity="0.35"/>
          <stop offset="100%" stopColor="oklch(0.80 0.14 210)" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {/* Gridlines */}
      {[0, 0.25, 0.5, 0.75, 1].map(f => (
        <g key={f}>
          <line x1={pad.l} x2={w - pad.r} y1={yFn(f * maxV)} y2={yFn(f * maxV)}
            stroke="oklch(0.30 0.015 240)" strokeWidth="0.5" strokeDasharray="2 4"/>
          <text x={pad.l - 6} y={yFn(f * maxV) + 3}
            fontSize="9" textAnchor="end" fill="oklch(0.5 0.012 240)"
            fontFamily="Geist Mono, monospace">
            {Math.round(f * maxV)}
          </text>
        </g>
      ))}
      {/* Alert thresholds */}
      <line x1={pad.l} x2={w - pad.r} y1={yFn(thr)} y2={yFn(thr)}
        stroke="var(--warn)" strokeWidth="1" strokeDasharray="4 4" opacity="0.7"/>
      <line x1={pad.l} x2={w - pad.r} y1={yFn(cbThr)} y2={yFn(cbThr)}
        stroke="var(--crit)" strokeWidth="1" strokeDasharray="4 4" opacity="0.8"/>
      {/* Anomaly zones */}
      {data.map((d, i) => d.anomaly && (
        <rect key={i} x={xFn(i) - 6} y={pad.t} width={12} height={h - pad.t - pad.b}
          fill="var(--crit)" opacity="0.07"/>
      ))}
      {/* Area fill */}
      <path d={fill} fill="url(#chart-fill)"/>
      {/* Line */}
      <path d={line} stroke="oklch(0.80 0.14 210)" strokeWidth="1.8" fill="none"
        strokeLinecap="round" strokeLinejoin="round"/>
      {/* Anomaly dots */}
      {data.map((d, i) => d.anomaly && (
        <circle key={i} cx={xFn(i)} cy={yFn(d.rainfall || d.v || 0)}
          r="4" fill="var(--crit)" stroke="var(--bg)" strokeWidth="1.5"/>
      ))}
      {/* Highlight dot */}
      {highlightIdx >= 0 && data[highlightIdx] && (
        <circle cx={xFn(highlightIdx)} cy={yFn(data[highlightIdx].rainfall || data[highlightIdx].v || 0)}
          r="5" fill="var(--warn)" stroke="var(--bg)" strokeWidth="1.5"/>
      )}
      {/* X-axis labels */}
      {data.filter((_, i) => i % Math.max(1, Math.floor(data.length / 8)) === 0).map((d, _, arr) => {
        const idx = data.indexOf(d);
        return (
          <text key={idx} x={xFn(idx)} y={h - 8} fontSize="9" textAnchor="middle"
            fill="oklch(0.5 0.012 240)" fontFamily="Geist Mono, monospace">
            {d.t || ""}
          </text>
        );
      })}
    </svg>
  );
};

/* ── Bar chart ──────────────────────────────────────────────────────── */
const BarChart = ({ data = [], height = 180 }) => {
  if (!data.length) return <div style={{ height }}><LoadingState/></div>;
  const w = 600, h = height;
  const pad = { t: 12, r: 8, b: 28, l: 32 };
  const maxV = Math.max(...data.map(d => d.v), 1) * 1.15;
  const bw = (w - pad.l - pad.r) / data.length;
  const yFn = v => pad.t + (1 - v / maxV) * (h - pad.t - pad.b);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block" }}>
      {[0, 0.5, 1].map(f => (
        <g key={f}>
          <line x1={pad.l} x2={w - pad.r} y1={yFn(f * maxV)} y2={yFn(f * maxV)}
            stroke="oklch(0.30 0.015 240)" strokeWidth="0.5"/>
          <text x={pad.l - 4} y={yFn(f * maxV) + 3}
            fontSize="9" textAnchor="end" fill="oklch(0.5 0.012 240)"
            fontFamily="Geist Mono, monospace">
            {Math.round(f * maxV)}
          </text>
        </g>
      ))}
      {data.map((d, i) => {
        const x = pad.l + i * bw + bw * 0.15;
        const bwInner = bw * 0.7;
        const barH = (h - pad.t - pad.b) - (yFn(d.v) - pad.t);
        const color = d.crit ? "var(--crit)" : d.warn ? "var(--warn)" : "var(--hydro)";
        return (
          <g key={i}>
            <rect x={x} y={yFn(d.v)} width={bwInner} height={Math.max(barH, 0)}
              fill={color} opacity="0.85" rx="2"/>
            <text x={x + bwInner / 2} y={h - 10} fontSize="9" textAnchor="middle"
              fill="oklch(0.5 0.012 240)" fontFamily="Geist Mono, monospace">
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

/* ── Forecast strip ─────────────────────────────────────────────────── */
const ForecastStrip = ({ entries = [] }) => {
  if (!entries.length) {
    entries = [
      { d: "Now",  h: "—", r: 0,  risk: "low"  },
      { d: "+6h",  h: "—", r: 0,  risk: "low"  },
      { d: "+12h", h: "—", r: 0,  risk: "low"  },
      { d: "+24h", h: "—", r: 0,  risk: "low"  },
    ];
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {entries.map((d, i) => (
        <div key={i} className="row between mono-sm" style={{ padding: "4px 0" }}>
          <span style={{ width: 50, color: i === 0 ? "var(--text)" : "var(--text-muted)" }}>{d.d}</span>
          <span className="dim" style={{ width: 58, fontSize: 10 }}>{d.h}</span>
          <div className="bar" style={{ flex: 1, margin: "0 10px" }}>
            <span style={{ width: `${Math.min((d.r / 120) * 100, 100)}%`,
              background: d.risk === "crit" ? "var(--crit)" : d.risk === "high" ? "oklch(0.72 0.2 45)" : d.risk === "med" ? "var(--warn)" : "var(--ok)" }}/>
          </div>
          <span className="mono" style={{ width: 50, textAlign: "right", color: "var(--text)" }}>{d.r}mm</span>
        </div>
      ))}
    </div>
  );
};

/* ── Alert row ──────────────────────────────────────────────────────── */
const AlertRow = ({ kind, title, meta, t }) => (
  <div className={`alert-row ${kind}`}>
    <div className="stripe"/>
    <div>
      <div className="title">{title}</div>
      <div className="meta">{meta}</div>
    </div>
    <div className="t">{t}</div>
  </div>
);

/* ── SOP row ────────────────────────────────────────────────────────── */
const SopRow = ({ name, dept, status, action }) => (
  <div className="row between" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
    <div>
      <div style={{ color: "var(--text)" }}>{name}</div>
      <div className="dim" style={{ fontSize: 10 }}>{dept}</div>
    </div>
    <Status kind={status}>{action}</Status>
  </div>
);

/* ── Toggle switch ──────────────────────────────────────────────────── */
const Toggle = ({ on, onChange }) => (
  <div onClick={() => onChange && onChange(!on)} style={{
    width: 32, height: 18, borderRadius: 10,
    background: on ? "var(--hydro)" : "var(--panel-3)",
    position: "relative", cursor: "pointer",
    boxShadow: on ? "0 0 10px var(--hydro-soft)" : "none",
    transition: "all 0.2s", flexShrink: 0,
  }}>
    <div style={{
      position: "absolute", top: 2, left: on ? 16 : 2,
      width: 14, height: 14, borderRadius: "50%",
      background: "white", transition: "left 0.2s",
    }}/>
  </div>
);

/* ── Legend swatch ──────────────────────────────────────────────────── */
const LegendSwatch = ({ c, l }) => (
  <span className="row mono-sm muted" style={{ gap: 6 }}>
    <span style={{ width: 10, height: 10, borderRadius: 2, background: c, flexShrink: 0 }}/>{l}
  </span>
);

/* ── KPI card ───────────────────────────────────────────────────────── */
const KpiCard = ({ label, value, unit, sub, color = "var(--text)" }) => (
  <div className="card metric">
    <div className="label">{label}</div>
    <div className="value tnum" style={{ color }}>
      {value !== null && value !== undefined ? value : <Spinner size={20}/>}
      {unit && value != null && <span className="unit">{unit}</span>}
    </div>
    <div className="delta flat">{sub}</div>
  </div>
);

/* ── Metric card with sparkline ─────────────────────────────────────── */
const MetricCard = ({ icon, label, value, unit, delta, deltaDir, spark, sparkColor }) => (
  <div className="card metric">
    <div className="label"><Icon name={icon} size={12}/>{label}</div>
    <div className="value tnum">
      {value !== null && value !== undefined ? value : <Spinner size={20}/>}
      {unit && value != null && <span className="unit">{unit}</span>}
    </div>
    <div className="row between mt-8">
      <span className={`delta ${deltaDir || "flat"}`}>{delta || "—"}</span>
      {spark && spark.length > 1 ? (
        <Sparkline data={spark} color={sparkColor} width={100} height={28}/>
      ) : null}
    </div>
  </div>
);

/* ── Settings row ───────────────────────────────────────────────────── */
const SettingsRow = ({ label, val, status }) => (
  <div className="row between" style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
    <div>
      <div style={{ color: "var(--text)" }}>{label}</div>
      <div className="mono-sm dim">{val}</div>
    </div>
    <Status kind={status}>{status === "ok" ? "Connected" : "Degraded"}</Status>
  </div>
);

/* ── Threshold row ──────────────────────────────────────────────────── */
const ThresholdRow = ({ label, val, unit, max }) => {
  const pct = (parseFloat(val) / max) * 100;
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <div className="row between mb-8">
        <span style={{ color: "var(--text)" }}>{label}</span>
        <span className="mono" style={{ color: "var(--cyan)" }}>{val}{unit}</span>
      </div>
      <div className="bar"><span style={{ width: `${Math.min(pct, 100)}%`, background: "var(--cyan)" }}/></div>
    </div>
  );
};

/* ── Time ago helper ────────────────────────────────────────────────── */
function timeAgo(ts) {
  if (!ts) return "—";
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 5)  return "just now";
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

/* ── Risk colors ────────────────────────────────────────────────────── */
function riskColor(rl) {
  if (!rl) return "var(--text-muted)";
  const r = rl.toUpperCase();
  if (r === "CRITICAL") return "var(--crit)";
  if (r === "HIGH")     return "oklch(0.72 0.2 45)";
  if (r === "MEDIUM")   return "var(--warn)";
  return "var(--ok)";
}

function riskKind(rl) {
  if (!rl) return "info";
  const r = rl.toUpperCase();
  if (r === "CRITICAL") return "crit";
  if (r === "HIGH")     return "warn";
  if (r === "MEDIUM")   return "warn";
  return "ok";
}

/* ── Export all to window ───────────────────────────────────────────── */
Object.assign(window, {
  Icon, BrandMark, Sparkline, Gauge, RiskMeter, Status, Chip, Card,
  Spinner, LoadingState, ErrorState, EmptyState, ToastContainer, toast,
  AnomalyChart, BarChart, ForecastStrip, AlertRow, SopRow, Toggle,
  LegendSwatch, KpiCard, MetricCard, SettingsRow, ThresholdRow,
  timeAgo, riskColor, riskKind,
});
