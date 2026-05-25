// HydroGuard AI — Landing page + Auth screens
const { useState, useEffect } = React;

// ── Landing Screen ─────────────────────────────────────────────────────────
const LandingScreen = ({ onEnter }) => {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch(API.BASE + "/health")
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setHealth(d); })
      .catch(() => {});
  }, []);

  return (
    <div className="landing" style={{ minHeight: "100vh" }}>
      {/* Nav */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "18px 32px", borderBottom: "1px solid var(--border)" }}>
        <div className="brand-mark"><BrandMark size={18}/></div>
        <div>
          <div className="brand-text">HydroGuard <span style={{ color: "var(--cyan)" }}>AI</span></div>
          <div className="brand-sub">Cloudburst · Flash Flood · Early Warning</div>
        </div>
        <div style={{ flex: 1 }}/>
        <div className="row" style={{ gap: 22, fontSize: 12.5, color: "var(--text-muted)" }}>
          <span style={{ cursor: "pointer" }}>Platform</span>
          <span style={{ cursor: "pointer" }}>Technology</span>
          <span style={{ cursor: "pointer" }}>Deployments</span>
          <span style={{ cursor: "pointer" }}>Docs</span>
        </div>
        <button className="btn" onClick={onEnter}><Icon name="lock"/>Sign in</button>
        <button className="btn btn-primary" onClick={onEnter}>Request demo<Icon name="arrow"/></button>
      </div>

      {/* Hero */}
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 40, padding: "60px 32px 40px", alignItems: "center", maxWidth: 1440, margin: "0 auto" }}>
        <div>
          <div className="row" style={{ gap: 8, marginBottom: 20 }}>
            <span className="chip crit">
              <span className="dot"/>
              {health ? `LIVE · ${health.model_loaded ? "MODEL ONLINE" : "TRAINING…"}` : "LIVE · CONNECTING"}
            </span>
            <span className="mono-sm dim">v{health?.version || "3.0.0"} · prod</span>
          </div>
          <h1 style={{ fontFamily: "var(--serif)", fontSize: "clamp(48px,6vw,80px)", lineHeight: 0.95, fontWeight: 400, margin: 0, letterSpacing: "-0.02em" }}>
            Predict before<br/>it <em style={{ fontStyle: "italic", color: "var(--cyan)" }}>strikes.</em>
          </h1>
          <p style={{ fontSize: 17, color: "var(--text-muted)", maxWidth: 560, marginTop: 22, lineHeight: 1.5 }}>
            HydroGuard AI is a mission-critical detection platform for cloudbursts and flash floods.
            Autoencoder + LSTM hybrid models fuse hydrometeorological sensor streams into
            sub-second risk signals that give response teams a significant advance lead time.
          </p>
          <div className="row mt-24" style={{ gap: 12 }}>
            <button className="btn btn-primary" onClick={onEnter}
              style={{ padding: "11px 18px", fontSize: 13 }}>
              View live dashboard<Icon name="arrow"/>
            </button>
            <button className="btn" style={{ padding: "11px 18px", fontSize: 13 }}>
              <Icon name="eye"/>Learn more
            </button>
          </div>
          <div className="row mt-24" style={{ gap: 28, color: "var(--text-muted)", fontSize: 12 }}>
            <div>
              <span className="mono" style={{ color: "var(--text)", fontSize: 22, fontWeight: 500 }}>92.4%</span>
              <span style={{ marginLeft: 6 }}>precision · F1 0.924</span>
            </div>
            <div>
              <span className="mono" style={{ color: "var(--text)", fontSize: 22, fontWeight: 500 }}>8</span>
              <span style={{ marginLeft: 6 }}>cities · Pakistan</span>
            </div>
            <div>
              <span className="mono" style={{ color: "var(--text)", fontSize: 22, fontWeight: 500 }}>{"<2s"}</span>
              <span style={{ marginLeft: 6 }}>inference latency</span>
            </div>
          </div>
        </div>

        {/* Hero card */}
        <div style={{ position: "relative" }}>
          <div className="card" style={{ padding: 16, borderRadius: 12, boxShadow: "0 40px 80px -30px rgba(0,0,0,0.7), 0 0 0 1px oklch(1 0 0 / 0.04) inset" }}>
            <div className="row between mb-12">
              <div className="row" style={{ gap: 8 }}>
                <span className="live">LIVE · ISB</span>
                <span className="mono-sm dim">· HydroGuard AI</span>
              </div>
              <span className={`status ${health?.model_loaded ? "ok" : "warn"}`}>
                <span className="dt"/>
                {health?.model_loaded ? "MODEL ONLINE" : "LOADING"}
              </span>
            </div>
            {/* Mini chart placeholder */}
            <div style={{ height: 120, background: "var(--bg-1)", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden" }}>
              <svg viewBox="0 0 400 100" width="100%" style={{ position: "absolute", inset: 0 }}>
                <defs>
                  <linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="oklch(0.80 0.14 210)" stopOpacity="0.3"/>
                    <stop offset="100%" stopColor="oklch(0.80 0.14 210)" stopOpacity="0"/>
                  </linearGradient>
                </defs>
                <path d="M 0,80 Q 40,70 80,65 T 160,55 T 240,40 T 280,20 T 320,15 L 320,100 L 0,100 Z"
                  fill="url(#hero-fill)"/>
                <path d="M 0,80 Q 40,70 80,65 T 160,55 T 240,40 T 280,20 T 320,15"
                  stroke="oklch(0.80 0.14 210)" strokeWidth="2" fill="none" strokeLinecap="round"/>
                <line x1="220" x2="400" y1="35" y2="35"
                  stroke="var(--crit)" strokeWidth="1" strokeDasharray="3 3" opacity="0.7"/>
              </svg>
            </div>
            <div className="grid g-3 mt-12" style={{ gap: 8 }}>
              <div style={{ padding: 10, background: "var(--bg-1)", borderRadius: 6 }}>
                <div className="mono-sm dim" style={{ fontSize: 9.5, letterSpacing: "0.14em" }}>STATUS</div>
                <div className="mono" style={{ fontSize: 16, color: health?.model_loaded ? "var(--ok)" : "var(--warn)", marginTop: 4 }}>
                  {health?.model_loaded ? "ONLINE" : "LOADING"}
                </div>
              </div>
              <div style={{ padding: 10, background: "var(--bg-1)", borderRadius: 6 }}>
                <div className="mono-sm dim" style={{ fontSize: 9.5, letterSpacing: "0.14em" }}>VERSION</div>
                <div className="mono" style={{ fontSize: 16, marginTop: 4 }}>
                  {health?.version || "—"}
                </div>
              </div>
              <div style={{ padding: 10, background: "var(--bg-1)", borderRadius: 6 }}>
                <div className="mono-sm dim" style={{ fontSize: 9.5, letterSpacing: "0.14em" }}>WS</div>
                <div className="mono" style={{ fontSize: 16, marginTop: 4 }}>
                  {health?.ws_connections ? Object.values(health.ws_connections).reduce((a, b) => a + b, 0) : "—"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Trust row */}
      <div style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", padding: "22px 32px" }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 4fr", alignItems: "center", gap: 32 }}>
          <div className="mono-sm dim" style={{ fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase" }}>Trusted by</div>
          <div className="row" style={{ gap: 42, fontSize: 13.5, color: "var(--text-muted)", fontWeight: 500, flexWrap: "wrap" }}>
            <span>NDMA · Pakistan</span>
            <span>PMD · Met Office</span>
            <span>CDA · Islamabad</span>
            <span>Punjab Disaster Mgmt</span>
            <span>Sindh PDMA</span>
            <span>KPK Smart City</span>
          </div>
        </div>
      </div>

      {/* Features */}
      <div style={{ maxWidth: 1440, margin: "0 auto", padding: "70px 32px" }}>
        <div className="mono-sm dim mb-12" style={{ letterSpacing: "0.14em", textTransform: "uppercase" }}>Capabilities</div>
        <h2 style={{ fontSize: "clamp(24px,3vw,40px)", margin: "0 0 50px", fontWeight: 500, letterSpacing: "-0.015em", maxWidth: 720 }}>
          A full operating picture for the moments weather turns hostile.
        </h2>
        <div className="grid g-3" style={{ gap: 16 }}>
          {[
            { ic: "brain",     t: "Hybrid Anomaly Detection",   b: "Autoencoder + LSTM hybrid continuously reconstructs the expected hydrometeorological state. When reality diverges, you are alerted first." },
            { ic: "radio",     t: "Real-time WebSocket Feed",    b: "Every prediction is broadcast over WebSocket to all connected dashboards — rainfall, pressure, wind and anomaly score in real time." },
            { ic: "cloudburst",t: "Cloudburst Detection Engine", b: "Dedicated pipeline for extreme precipitation with per-city monsoon-season calibration and physics-based thresholds." },
            { ic: "flood",     t: "Flash Flood Risk Modeling",   b: "HRI score fuses anomaly signal, rainfall intensity, and regional vulnerability into a 0-100 Hazard Risk Index." },
            { ic: "city",      t: "Multi-city Model Heads",      b: "Ten Pakistan cities with dedicated LSTM sequence buffers seeded from 25 years of historical data." },
            { ic: "shield",    t: "Early Warning Dispatch",      b: "Pre-staged SOPs can be dispatched to NDMA, PMD and municipal desks via JWT-secured API calls." },
          ].map((f, i) => (
            <div key={i} className="card" style={{ padding: 22 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--panel-2)", border: "1px solid var(--border)", display: "grid", placeItems: "center", color: "var(--cyan)" }}>
                <Icon name={f.ic} size={18}/>
              </div>
              <div style={{ fontSize: 15.5, fontWeight: 500, marginTop: 14, letterSpacing: "-0.005em" }}>{f.t}</div>
              <div style={{ color: "var(--text-muted)", marginTop: 6, fontSize: 13, lineHeight: 1.5 }}>{f.b}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Architecture strip */}
      <div style={{ maxWidth: 1440, margin: "0 auto", padding: "0 32px 80px" }}>
        <div className="card" style={{ padding: 28 }}>
          <div className="row between mb-16">
            <div>
              <div className="mono-sm dim" style={{ letterSpacing: "0.14em", textTransform: "uppercase" }}>System Architecture</div>
              <div style={{ fontSize: 22, fontWeight: 500, marginTop: 6 }}>
                Signal → Model → Decision — in under 2 seconds.
              </div>
            </div>
            <button className="btn">FastAPI docs<Icon name="externalLink"/></button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 30px 1fr 30px 1fr 30px 1fr", alignItems: "stretch", gap: 0, marginTop: 20 }}>
            {[
              { t: "Ingest",         l: "CSV · REST · auto-fill", ic: "radio" },
              { t: "Fuse & normalize",l: "Pandas · NumPy",        ic: "zap" },
              { t: "AE + LSTM",      l: "Hybrid anomaly score",   ic: "brain" },
              { t: "Dispatch",       l: "WS · REST · JWT",        ic: "shield" },
            ].map((s, i, a) => (
              <React.Fragment key={i}>
                <div style={{ padding: "18px 16px", background: "var(--bg-1)", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <div className="row" style={{ gap: 8, color: "var(--cyan)" }}>
                    <Icon name={s.ic} size={14}/>
                    <span className="mono-sm" style={{ letterSpacing: "0.14em", textTransform: "uppercase", fontSize: 10 }}>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 500, marginTop: 8 }}>{s.t}</div>
                  <div className="mono-sm muted" style={{ marginTop: 2, fontSize: 11 }}>{s.l}</div>
                </div>
                {i < a.length - 1 && (
                  <div style={{ display: "grid", placeItems: "center", color: "var(--text-dim)" }}>
                    <Icon name="arrow" size={14}/>
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* CTA */}
      <div style={{ maxWidth: 1440, margin: "0 auto", padding: "0 32px 80px" }}>
        <div style={{ padding: "50px 40px", borderRadius: 12, background: "linear-gradient(135deg, oklch(0.30 0.14 240), oklch(0.22 0.08 220))", border: "1px solid oklch(0.5 0.14 240 / 0.3)", position: "relative", overflow: "hidden" }}>
          <div style={{ fontFamily: "var(--serif)", fontSize: "clamp(28px,3vw,46px)", lineHeight: 1, letterSpacing: "-0.015em" }}>
            Real-time intelligence.<br/><em style={{ color: "var(--cyan)" }}>Real-world protection.</em>
          </div>
          <div style={{ color: "oklch(0.85 0.04 240)", marginTop: 12, fontSize: 15, maxWidth: 620 }}>
            HydroGuard AI integrates with your existing disaster-response workflows
            via JWT-secured REST and WebSocket APIs. Start a session to explore the live dashboard.
          </div>
          <div className="row mt-24" style={{ gap: 12 }}>
            <button className="btn btn-primary" onClick={onEnter}>
              Open dashboard<Icon name="arrow"/>
            </button>
            <a href={API.BASE + "/docs"} target="_blank" rel="noopener noreferrer">
              <button className="btn" style={{ background: "transparent", color: "white", borderColor: "oklch(1 0 0 / 0.3)" }}>
                API documentation<Icon name="externalLink"/>
              </button>
            </a>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ borderTop: "1px solid var(--border)", padding: "24px 32px", color: "var(--text-dim)", fontSize: 12 }}>
        <div className="row between" style={{ maxWidth: 1440, margin: "0 auto" }}>
          <span>© 2026 HydroGuard AI · Government-grade disaster monitoring</span>
          <div className="row" style={{ gap: 16 }}>
            <a href={API.BASE + "/docs"} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--text-dim)", textDecoration: "none" }}>API Docs</a>
            <span className="mono-sm">v{health?.version || "3.0.0"}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Auth Screen ─────────────────────────────────────────────────────────────
const AuthScreen = ({ onLogin, onBack }) => {
  const [mode, setMode]         = useState("login");   // login | register
  const [email, setEmail]       = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole]         = useState("USER");
  const [showPw, setShowPw]     = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const submit = async () => {
    setError("");
    if (!email || !password) { setError("Email and password are required."); return; }
    if (mode === "register" && !username) { setError("Username is required."); return; }
    setLoading(true);
    try {
      await onLogin(email, password, mode === "register" ? username : undefined, mode === "register" ? role : undefined);
    } catch (e) {
      setError(e.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => { if (e.key === "Enter") submit(); };

  return (
    <div style={{
      minHeight: "100vh",
      background: "radial-gradient(900px 500px at 50% -10%, oklch(0.30 0.14 240 / 0.4), transparent 60%), var(--bg)",
      display: "grid",
      gridTemplateColumns: "1fr 480px",
    }}>
      {/* Left panel */}
      <div style={{ padding: "40px 48px", display: "flex", flexDirection: "column", justifyContent: "space-between", borderRight: "1px solid var(--border)" }}>
        <div className="row" style={{ gap: 10, cursor: "pointer" }} onClick={onBack}>
          <div className="brand-mark"><BrandMark size={18}/></div>
          <div>
            <div className="brand-text">HydroGuard <span style={{ color: "var(--cyan)" }}>AI</span></div>
            <div className="brand-sub">Secure operator portal</div>
          </div>
        </div>
        <div>
          <div className="mono-sm dim mb-12" style={{ letterSpacing: "0.14em", textTransform: "uppercase" }}>Operations</div>
          <h2 style={{ fontFamily: "var(--serif)", fontSize: "clamp(28px,3vw,48px)", lineHeight: 1.05, margin: 0, fontWeight: 400, letterSpacing: "-0.01em", maxWidth: 560 }}>
            Detect cloudbursts and flash floods before they strike.
          </h2>
          <div className="grid g-3 mt-24" style={{ gap: 10, maxWidth: 600 }}>
            <div className="card" style={{ padding: 12 }}>
              <div className="row between">
                <span className="mono-sm dim" style={{ fontSize: 10, letterSpacing: "0.12em" }}>MODEL</span>
                <span className="status ok"><span className="dt"/>ONLINE</span>
              </div>
              <div className="mono" style={{ fontSize: 18, marginTop: 6, color: "var(--ok)" }}>AE+LSTM</div>
            </div>
            <div className="card" style={{ padding: 12 }}>
              <div className="row between">
                <span className="mono-sm dim" style={{ fontSize: 10, letterSpacing: "0.12em" }}>PRECISION</span>
              </div>
              <div className="mono" style={{ fontSize: 18, marginTop: 6 }}>92.4%</div>
            </div>
            <div className="card" style={{ padding: 12 }}>
              <div className="row between">
                <span className="mono-sm dim" style={{ fontSize: 10, letterSpacing: "0.12em" }}>CITIES</span>
              </div>
              <div className="mono" style={{ fontSize: 18, marginTop: 6 }}>8 active</div>
            </div>
          </div>
        </div>
        <div className="mono-sm dim">Authorized use only · All activity logged</div>
      </div>

      {/* Right panel — form */}
      <div style={{ padding: "40px 40px", display: "flex", flexDirection: "column", justifyContent: "center", background: "var(--bg-1)" }}>
        {/* Mode tabs */}
        <div className="seg mb-12" style={{ alignSelf: "flex-start" }}>
          <button className={mode === "login" ? "on" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
          <button className={mode === "register" ? "on" : ""} onClick={() => { setMode("register"); setError(""); }}>Register</button>
        </div>

        <div style={{ fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em" }}>
          {mode === "login" ? "Sign in" : "Create account"}
        </div>
        <div className="muted mt-8" style={{ marginBottom: 24 }}>
          {mode === "login"
            ? "Authenticate to access the operations portal."
            : "Register a new operator account."}
        </div>

        {error && <ErrorState message={error}/>}

        {/* Email */}
        <label className="field-label">Email address</label>
        <div className="field-input mb-12">
          <Icon name="mail" size={14}/>
          <input
            type="email" value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={handleKey}
            placeholder="operator@ndma.gov.pk"
            autoComplete="email" autoFocus
          />
        </div>

        {/* Username (register only) */}
        {mode === "register" && (
          <>
            <label className="field-label">Username</label>
            <div className="field-input mb-12">
              <Icon name="user" size={14}/>
              <input
                type="text" value={username}
                onChange={e => setUsername(e.target.value)}
                onKeyDown={handleKey}
                placeholder="operator_name"
                autoComplete="username"
              />
            </div>
          </>
        )}

        {/* Password */}
        <label className="field-label">Password</label>
        <div className="field-input mb-12">
          <Icon name="lock" size={14}/>
          <input
            type={showPw ? "text" : "password"}
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={handleKey}
            placeholder={mode === "register" ? "Min. 8 characters" : "••••••••"}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          <button style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-dim)", padding: 0 }}
            onClick={() => setShowPw(v => !v)}>
            <Icon name="eye" size={14}/>
          </button>
        </div>

        {/* Role selector (register only) */}
        {mode === "register" && (
          <>
            <label className="field-label mt-4">Role</label>
            <div className="row mt-8 mb-12" style={{ gap: 6 }}>
              {["USER", "ANALYST", "ADMIN"].map(r => (
                <button key={r} onClick={() => setRole(r)} className="btn" style={{
                  flex: 1, justifyContent: "center", padding: "10px",
                  textTransform: "capitalize",
                  borderColor: role === r ? "var(--hydro)" : "var(--border)",
                  background: role === r ? "var(--hydro-soft)" : "var(--panel)",
                  color: role === r ? "var(--text)" : "var(--text-muted)",
                }}>{r}</button>
              ))}
            </div>
          </>
        )}

        <button
          className="btn btn-primary mt-16"
          onClick={submit}
          disabled={loading}
          style={{ justifyContent: "center", padding: "11px", fontSize: 13 }}>
          {loading ? <><Spinner size={14}/>{mode === "login" ? "Signing in…" : "Creating account…"}</> : (
            <>{mode === "login" ? "Sign in" : "Create account"}<Icon name="arrow"/></>
          )}
        </button>

        <hr className="hr mt-24"/>
        <div className="mono-sm muted row between">
          <span style={{ cursor: "pointer" }} onClick={onBack}>← Back to landing</span>
          {mode === "login" && (
            <span style={{ cursor: "pointer" }} onClick={() => setMode("register")}>
              New here? Register →
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { LandingScreen, AuthScreen });
