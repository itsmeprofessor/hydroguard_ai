// HydroGuard AI — Visualizations: Pakistan map + flood terrain SVG

// ── Static city coordinate table ───────────────────────────────────────────
// These are SVG-space positions for the Pakistan outline (720×620 viewBox).
// Runtime data (hri_score, risk_level, rainfall) is merged from the API.
const CITY_COORDS = {
  "Islamabad":  { id: "isb", x: 480, y: 170, lat: "33.68°N", lng: "73.04°E", pop: "1.1M" },
  "Rawalpindi": { id: "rwp", x: 512, y: 198, lat: "33.56°N", lng: "73.01°E", pop: "2.1M" },
  "Lahore":     { id: "lhr", x: 548, y: 290, lat: "31.52°N", lng: "74.36°E", pop: "13.1M" },
  "Karachi":    { id: "khi", x: 262, y: 560, lat: "24.86°N", lng: "67.00°E", pop: "16.9M" },
  "Peshawar":   { id: "pew", x: 420, y: 148, lat: "34.02°N", lng: "71.58°E", pop: "2.0M" },
  "Quetta":     { id: "que", x: 222, y: 332, lat: "30.18°N", lng: "66.99°E", pop: "1.0M" },
  "Multan":     { id: "mul", x: 432, y: 382, lat: "30.19°N", lng: "71.47°E", pop: "1.9M" },
  "Faisalabad": { id: "fsd", x: 502, y: 304, lat: "31.42°N", lng: "73.08°E", pop: "3.2M" },
  "Hyderabad":  { id: "hyd", x: 288, y: 502, lat: "25.39°N", lng: "68.37°E", pop: "1.7M" },
  "Gilgit":     { id: "gil", x: 388, y: 100, lat: "35.92°N", lng: "74.31°E", pop: "0.3M" },
};

const RISK_TO_VIZ = { "LOW": "low", "MEDIUM": "med", "HIGH": "high", "CRITICAL": "crit" };

// Build CITIES array from API risk-map or fallback to static defaults
function buildCities(apiEntries) {
  const entries = apiEntries || [];
  const result = [];
  entries.forEach(e => {
    const coords = CITY_COORDS[e.city];
    if (!coords) return;
    result.push({
      ...coords,
      name: e.city,
      region: e.region,
      risk: RISK_TO_VIZ[e.risk_level] || "low",
      rainfall: e.hri_score || 0,
      hri_score: e.hri_score,
      hri_label: e.hri_label,
      risk_level: e.risk_level,
    });
  });
  // Add any cities from static table not in the API response
  if (!result.length) {
    Object.entries(CITY_COORDS).forEach(([name, coords]) => {
      result.push({ ...coords, name, region: "Pakistan", risk: "low", rainfall: 0, hri_score: 0, hri_label: "Low", risk_level: "LOW" });
    });
  }
  return result;
}

// Global CITIES (updated by app.jsx when risk-map loads)
let CITIES = buildCities([]);
window._setCities = function(apiEntries) {
  CITIES = buildCities(apiEntries);
  window._CITIES = CITIES;
};
window._CITIES = CITIES;

// ── Risk heat gradient IDs ─────────────────────────────────────────────────
const HEAT_IDS = { crit: "heat-crit", high: "heat-high", med: "heat-med", low: "heat-low" };

// ── Pakistan Map ───────────────────────────────────────────────────────────
const PakistanMap = ({ selected, onSelect, showHeat = true, compact = false, cities: propCities }) => {
  const citiesData = propCities || window._CITIES || CITIES;
  const w = compact ? 600 : 720;
  const h = compact ? 520 : 620;
  const scale = compact ? 600 / 720 : 1;

  const heatColor = (risk) => ({
    crit: "oklch(0.66 0.22 25)",
    high: "oklch(0.72 0.2 45)",
    med:  "oklch(0.80 0.15 75)",
    low:  "oklch(0.74 0.14 155)",
  }[risk] || "oklch(0.74 0.14 155)");

  return (
    <div style={{ position: "relative", width: "100%", aspectRatio: `${w}/${h}` }}>
      <svg viewBox={`0 0 ${w} ${h}`}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0H0v20" stroke="oklch(0.35 0.015 240)"
              strokeWidth="0.3" fill="none" opacity="0.25"/>
          </pattern>
          {["crit","high","med","low"].map(r => (
            <radialGradient key={r} id={HEAT_IDS[r]}>
              <stop offset="0%"   stopColor={heatColor(r)} stopOpacity="0.65"/>
              <stop offset="100%" stopColor={heatColor(r)} stopOpacity="0"/>
            </radialGradient>
          ))}
          <filter id="city-glow">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feComposite in="SourceGraphic" in2="blur" operator="over"/>
          </filter>
        </defs>

        {/* Background grid */}
        <rect width={w} height={h} fill="url(#grid)"/>

        {/* Pakistan outline — stylised polygon */}
        <path
          d="M 360 80 L 440 70 L 490 95 L 530 120 L 560 140 L 610 165 L 640 200
             L 620 240 L 580 265 L 570 310 L 585 345 L 555 365 L 525 380
             L 520 410 L 540 440 L 525 475 L 495 495 L 470 530 L 440 555
             L 400 585 L 360 595 L 310 585 L 270 570 L 230 545 L 200 510
             L 180 470 L 175 420 L 185 375 L 175 335 L 155 295 L 145 255
             L 170 220 L 195 195 L 220 175 L 245 155 L 260 120 L 280 90
             L 310 72 Z"
          fill="oklch(0.20 0.014 240 / 0.7)"
          stroke="oklch(0.45 0.018 240)"
          strokeWidth="1.2"
        />

        {/* Heat halos */}
        {showHeat && citiesData.map(c => {
          const sx = c.x * (compact ? scale : 1);
          const sy = c.y * (compact ? scale : 1);
          const r = compact ? 55 : 70;
          return (
            <ellipse key={c.id} cx={sx} cy={sy} rx={r} ry={r * 0.8}
              fill={`url(#${HEAT_IDS[c.risk] || "heat-low"})`} opacity="0.9"/>
          );
        })}

        {/* City dots & labels */}
        {citiesData.map(c => {
          const sx = compact ? c.x * scale : c.x;
          const sy = compact ? c.y * scale : c.y;
          const isSelected = selected === c.id;
          const dotColor = c.risk === "crit" ? "var(--crit)"
            : c.risk === "high" ? "oklch(0.72 0.2 45)"
            : c.risk === "med"  ? "var(--warn)"
            : "var(--ok)";
          return (
            <g key={c.id} style={{ cursor: "pointer" }}
              onClick={() => onSelect && onSelect(c.id)}>
              {/* Outer ring for selected */}
              {isSelected && (
                <circle cx={sx} cy={sy} r={9}
                  fill="none" stroke={dotColor} strokeWidth="1.5" opacity="0.6"/>
              )}
              <circle cx={sx} cy={sy} r={isSelected ? 6 : 4.5}
                fill={dotColor}
                stroke="oklch(0.14 0.012 240)" strokeWidth="1.5"/>
              {/* Label */}
              <rect x={sx + 9} y={sy - 14} width={c.name.length * 6.2 + 8} height={14}
                rx="3" fill="oklch(0.20 0.014 240 / 0.9)"
                stroke="oklch(0.35 0.015 240)" strokeWidth="0.5"/>
              <text x={sx + 13} y={sy - 4}
                fontSize="9.5" fill="oklch(0.94 0.005 240)"
                fontFamily="Geist Mono, monospace">{c.name}</text>
            </g>
          );
        })}

        {/* Compass */}
        <g transform={`translate(${w - 36} 36)`}>
          <circle r="14" fill="oklch(0.2 0.014 240 / 0.8)"
            stroke="oklch(0.35 0.015 240)" strokeWidth="0.6"/>
          <path d="M 0 -10 L 3 0 L 0 -3 L -3 0 Z"
            fill="oklch(0.80 0.14 210)"/>
          <text x="0" y="-15" fontSize="8.5" textAnchor="middle"
            fill="oklch(0.65 0.012 240)"
            fontFamily="Geist Mono, monospace">N</text>
        </g>

        {/* Scale bar */}
        <g transform={`translate(24 ${h - 22})`}>
          <line x1="0" y1="0" x2="70" y2="0"
            stroke="oklch(0.55 0.012 240)" strokeWidth="1"/>
          <line x1="0" y1="-3" x2="0" y2="3"
            stroke="oklch(0.55 0.012 240)" strokeWidth="1"/>
          <line x1="70" y1="-3" x2="70" y2="3"
            stroke="oklch(0.55 0.012 240)" strokeWidth="1"/>
          <text x="35" y="12" fontSize="8.5" textAnchor="middle"
            fill="oklch(0.5 0.012 240)"
            fontFamily="Geist Mono, monospace">200 km</text>
        </g>
      </svg>
    </div>
  );
};

// ── Flood basin / terrain visualisation ───────────────────────────────────
const FloodModelViz = () => (
  <svg viewBox="0 0 760 340" width="100%" style={{ display: "block" }}>
    <defs>
      <linearGradient id="terrain" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stopColor="oklch(0.35 0.02 180)"/>
        <stop offset="100%" stopColor="oklch(0.22 0.015 240)"/>
      </linearGradient>
      <radialGradient id="floodRed">
        <stop offset="0%"   stopColor="oklch(0.66 0.22 25)" stopOpacity="0.7"/>
        <stop offset="100%" stopColor="oklch(0.66 0.22 25)" stopOpacity="0"/>
      </radialGradient>
      <radialGradient id="floodOrange">
        <stop offset="0%"   stopColor="oklch(0.72 0.2 45)" stopOpacity="0.55"/>
        <stop offset="100%" stopColor="oklch(0.72 0.2 45)" stopOpacity="0"/>
      </radialGradient>
      <pattern id="contour" width="760" height="340" patternUnits="userSpaceOnUse">
        <path d="M0 100 Q 200 80 400 110 T 760 90"  stroke="oklch(0.32 0.018 240)" strokeWidth="0.5" fill="none"/>
        <path d="M0 140 Q 200 120 400 150 T 760 130" stroke="oklch(0.32 0.018 240)" strokeWidth="0.5" fill="none"/>
        <path d="M0 180 Q 200 160 400 190 T 760 170" stroke="oklch(0.32 0.018 240)" strokeWidth="0.5" fill="none"/>
        <path d="M0 220 Q 200 200 400 230 T 760 210" stroke="oklch(0.32 0.018 240)" strokeWidth="0.5" fill="none"/>
        <path d="M0 260 Q 200 240 400 270 T 760 250" stroke="oklch(0.32 0.018 240)" strokeWidth="0.5" fill="none"/>
      </pattern>
    </defs>
    <rect width="760" height="340" fill="url(#terrain)"/>
    <rect width="760" height="340" fill="url(#contour)"/>
    {/* Rivers */}
    <path d="M 40 60 Q 140 110 220 150 T 400 220 Q 480 260 560 280 L 720 310"
      fill="none" stroke="oklch(0.70 0.12 220)" strokeWidth="3" opacity="0.75" strokeLinecap="round"/>
    <path d="M 180 40 Q 220 100 260 140 T 340 200"
      fill="none" stroke="oklch(0.70 0.12 220)" strokeWidth="1.8" opacity="0.6" strokeLinecap="round"/>
    <path d="M 500 50 Q 520 120 540 170 T 580 240"
      fill="none" stroke="oklch(0.70 0.12 220)" strokeWidth="1.8" opacity="0.6" strokeLinecap="round"/>
    {/* Flood zones */}
    <ellipse cx="240" cy="155" rx="110" ry="48" fill="url(#floodRed)"/>
    <ellipse cx="380" cy="210" rx="90"  ry="42" fill="url(#floodRed)"/>
    <ellipse cx="540" cy="270" rx="100" ry="40" fill="url(#floodOrange)"/>
    <ellipse cx="150" cy="90"  rx="70"  ry="34" fill="url(#floodOrange)"/>
    {/* Zone labels */}
    {[
      { x: 240, y: 155, id: "Z-01", r: "crit" },
      { x: 380, y: 210, id: "Z-02", r: "crit" },
      { x: 540, y: 270, id: "Z-03", r: "high" },
      { x: 150, y: 90,  id: "Z-04", r: "high" },
    ].map((z, i) => (
      <g key={i}>
        <circle cx={z.x} cy={z.y} r="4"
          fill={z.r === "crit" ? "oklch(0.66 0.22 25)" : "oklch(0.72 0.2 45)"}
          stroke="oklch(0.14 0.012 240)" strokeWidth="1.5"/>
        <rect x={z.x + 8} y={z.y - 16} width="36" height="14" rx="3"
          fill="oklch(0.2 0.014 240 / 0.9)" stroke="oklch(0.35 0.015 240)" strokeWidth="0.5"/>
        <text x={z.x + 12} y={z.y - 6} fontSize="9"
          fill="oklch(0.95 0.005 240)" fontFamily="Geist Mono, monospace">{z.id}</text>
      </g>
    ))}
    {/* Compass */}
    <g transform="translate(700 40)">
      <circle r="16" fill="oklch(0.2 0.014 240 / 0.8)" stroke="oklch(0.35 0.015 240)" strokeWidth="0.6"/>
      <path d="M 0 -12 L 4 0 L 0 -4 L -4 0 Z" fill="oklch(0.80 0.14 210)"/>
      <text x="0" y="-18" fontSize="9" textAnchor="middle"
        fill="oklch(0.65 0.012 240)" fontFamily="Geist Mono, monospace">N</text>
    </g>
    {/* Scale */}
    <g transform="translate(30 310)">
      <line x1="0" y1="0" x2="80" y2="0" stroke="oklch(0.65 0.012 240)" strokeWidth="1.2"/>
      <line x1="0"  y1="-3" x2="0"  y2="3" stroke="oklch(0.65 0.012 240)" strokeWidth="1.2"/>
      <line x1="80" y1="-3" x2="80" y2="3" stroke="oklch(0.65 0.012 240)" strokeWidth="1.2"/>
      <text x="40" y="14" fontSize="9" textAnchor="middle"
        fill="oklch(0.5 0.012 240)" fontFamily="Geist Mono, monospace">2 km</text>
    </g>
  </svg>
);

Object.assign(window, { PakistanMap, FloodModelViz, CITY_COORDS, RISK_TO_VIZ, buildCities });
