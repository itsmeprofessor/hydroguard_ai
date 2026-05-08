// Citizen-app — Settings screen
// Theme toggle, searchable city picker, notifications, language, etc.

const PK_CITIES = [
  { name: "Islamabad", region: "Capital Territory", pop: "1.1M", risk: "high" },
  { name: "Rawalpindi", region: "Punjab", pop: "2.1M", risk: "high" },
  { name: "Lahore", region: "Punjab", pop: "13.0M", risk: "med" },
  { name: "Karachi", region: "Sindh", pop: "16.0M", risk: "high" },
  { name: "Peshawar", region: "KPK", pop: "1.9M", risk: "med" },
  { name: "Quetta", region: "Balochistan", pop: "1.0M", risk: "low" },
  { name: "Multan", region: "Punjab", pop: "1.9M", risk: "med" },
  { name: "Faisalabad", region: "Punjab", pop: "3.2M", risk: "low" },
  { name: "Hyderabad", region: "Sindh", pop: "1.7M", risk: "med" },
  { name: "Sialkot", region: "Punjab", pop: "0.7M", risk: "low" },
  { name: "Gujranwala", region: "Punjab", pop: "2.0M", risk: "low" },
  { name: "Murree", region: "Punjab", pop: "23K", risk: "high" },
  { name: "Gilgit", region: "GB", pop: "0.2M", risk: "high" },
  { name: "Skardu", region: "GB", pop: "0.2M", risk: "med" },
  { name: "Mirpur", region: "AJK", pop: "0.5M", risk: "med" },
  { name: "Muzaffarabad", region: "AJK", pop: "0.7M", risk: "high" },
];

const LANGUAGES = [
  { code: "en", label: "English", native: "English" },
  { code: "ur", label: "Urdu", native: "اردو" },
  { code: "pa", label: "Punjabi", native: "ਪੰਜਾਬੀ" },
  { code: "ps", label: "Pashto", native: "پښتو" },
  { code: "sd", label: "Sindhi", native: "سنڌي" },
  { code: "bal", label: "Balochi", native: "بلوچی" },
];

// ── Reusable rows ──────────────────────────────────────────
const SettingsGroup = ({ title, children }) => (
  <div className="set-group">
    <div className="set-group-title">{title}</div>
    <div className="set-group-bd">{children}</div>
  </div>
);

const SetRow = ({ icon, iconBg, iconColor, title, sub, right, onClick, danger }) => (
  <button className={`set-row ${danger ? "danger" : ""} ${onClick ? "tappable" : ""}`} onClick={onClick}>
    <div className="set-row-ic" style={{ background: iconBg, color: iconColor }}>
      <CIcon name={icon} size={17}/>
    </div>
    <div className="set-row-tx">
      <div className="t">{title}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
    <div className="set-row-rt">{right}</div>
  </button>
);

// iOS-style toggle
const Toggle = ({ on, onChange, tone = "blue" }) => (
  <span className={`set-toggle ${on ? "on" : ""} ${tone}`} onClick={(e) => { e.stopPropagation(); onChange(!on); }} role="switch" aria-checked={on}>
    <span className="knob"/>
  </span>
);

// Sheet (modal) container — slides up from bottom of phone
const Sheet = ({ open, onClose, title, children, height = "78%" }) => {
  if (!open) return null;
  return (
    <div className="set-sheet-scrim" onClick={onClose}>
      <div className="set-sheet" style={{ height }} onClick={(e) => e.stopPropagation()}>
        <div className="set-sheet-grab"/>
        <div className="set-sheet-head">
          <h3>{title}</h3>
          <button className="set-sheet-x" onClick={onClose}><CIcon name="x" size={16}/></button>
        </div>
        <div className="set-sheet-bd">{children}</div>
      </div>
    </div>
  );
};

// ── City picker ────────────────────────────────────────────
const CityPicker = ({ value, onSelect, onClose }) => {
  const [q, setQ]               = React.useState("");
  const [apiCities, setApiCities] = React.useState(null); // null = loading
  const [error, setError]       = React.useState(null);

  // Fetch dynamic city list from /cities. Fall back to PK_CITIES static list
  // if the API is unreachable.
  React.useEffect(() => {
    if (!window.HydroAPI) { setApiCities(null); return; }
    HydroAPI.getCities()
      .then(list => {
        // Map backend city dicts to the picker's expected shape
        const enriched = (list || []).map(c => {
          const fallback = PK_CITIES.find(p => p.name === c.name) || {};
          return {
            name:   c.name,
            region: c.province || fallback.region || "—",
            pop:    c.population || fallback.pop  || "—",
            risk:   fallback.risk || "med",
            hasModel: c.has_model,
          };
        });
        setApiCities(enriched.length ? enriched : PK_CITIES);
      })
      .catch(err => {
        console.warn("CityPicker: falling back to static list", err);
        setError(err.message);
        setApiCities(PK_CITIES);
      });
  }, []);

  const source = apiCities || PK_CITIES;
  const filtered = source.filter(c =>
    c.name.toLowerCase().includes(q.toLowerCase()) ||
    (c.region || "").toLowerCase().includes(q.toLowerCase())
  );
  const recents = source.slice(0, 3).map(c => c.name);
  const riskLabel = { high: "High flood risk", med: "Moderate risk", low: "Low risk" };
  const riskKind  = { high: "crit",            med: "warn",            low: "safe"      };

  return (
    <>
      <div className="set-search">
        <CIcon name="search" size={16} color="var(--c-muted)"/>
        <input
          type="text"
          placeholder="Search city or region…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        {q && <button onClick={() => setQ("")} className="set-search-x"><CIcon name="x" size={14}/></button>}
      </div>

      {!q && (
        <div className="set-recents">
          <div className="set-recents-h">Recent</div>
          <div className="set-recents-row">
            {recents.map(r => (
              <button key={r} className={`set-pill ${r === value ? "on" : ""}`} onClick={() => { onSelect(r); onClose(); }}>
                <CIcon name="pin" size={11}/>{r}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="set-recents-h">{q ? `Results · ${filtered.length}` : "All cities"}</div>
      <div className="set-city-list">
        {filtered.length === 0 && (
          <div className="set-empty">No matches for "{q}"</div>
        )}
        {filtered.map(c => (
          <button
            key={c.name}
            className={`set-city ${c.name === value ? "on" : ""}`}
            onClick={() => { onSelect(c.name); onClose(); }}
          >
            <div className="set-city-tx">
              <div className="n">{c.name}</div>
              <div className="r">{c.region} · {c.pop}</div>
            </div>
            <span className={`pill-chip ${riskKind[c.risk]}`}>
              <span className="dt"/>{riskLabel[c.risk]}
            </span>
            {c.name === value && <CIcon name="check" size={16} color="var(--c-blue)"/>}
          </button>
        ))}
      </div>
    </>
  );
};

// ── Language picker ────────────────────────────────────────
const LangPicker = ({ value, onSelect, onClose }) => (
  <div className="set-city-list">
    {LANGUAGES.map(l => (
      <button
        key={l.code}
        className={`set-city ${l.code === value ? "on" : ""}`}
        onClick={() => { onSelect(l.code); onClose(); }}
      >
        <div className="set-city-tx">
          <div className="n">{l.label}</div>
          <div className="r">{l.native}</div>
        </div>
        {l.code === value && <CIcon name="check" size={16} color="var(--c-blue)"/>}
      </button>
    ))}
  </div>
);

// ── Settings screen ────────────────────────────────────────
const SettingsScreen = ({ prefs, setPrefs, scenario }) => {
  const [openSheet, setOpenSheet] = React.useState(null); // 'city' | 'lang'

  const langLabel = LANGUAGES.find(l => l.code === prefs.lang)?.label ?? "English";
  const dark = prefs.theme === "dark";

  return (
    <div className={`citizen scr-settings ${dark ? "dark" : ""}`} style={{ minHeight: "100%" }}>
      <div style={{ height: 50 }}/>
      <div className="app-header">
        <div className="greet">
          <div className="hi">Settings</div>
          <div className="city">Personalize your app</div>
        </div>
        <button className="icbtn" aria-label="Search"><CIcon name="search" size={18}/></button>
      </div>

      <div className="scr-padding">
        {/* Profile card */}
        <div className="set-profile">
          <div className="ava">A</div>
          <div className="set-profile-tx">
            <div className="n">Ayesha Khan</div>
            <div className="s">{prefs.city} · HydroGuard since Mar 2024</div>
          </div>
          <button className="set-profile-edit"><CIcon name="chevron" size={16}/></button>
        </div>

        {/* Appearance */}
        <SettingsGroup title="Appearance">
          <SetRow
            icon="moon"
            iconBg="var(--c-set-icbg-violet)"
            iconColor="#7C3AED"
            title="Dark mode"
            sub="Easier on the eyes at night"
            right={<Toggle on={dark} onChange={(v) => setPrefs({ theme: v ? "dark" : "light" })}/>}
          />
          <div className="set-divider"/>
          <div className="set-theme-preview">
            {[
              { v: "light", label: "Light", bg: "#F2F4F8", fg: "#0F1A2B", chip: "#DBE7FE" },
              { v: "dark", label: "Dark", bg: "#0E1117", fg: "#F2F4F8", chip: "#1E293B" },
            ].map(t => (
              <button
                key={t.v}
                className={`set-theme-card ${prefs.theme === t.v ? "on" : ""}`}
                onClick={() => setPrefs({ theme: t.v })}
                style={{ background: t.bg, color: t.fg }}
              >
                <div className="set-theme-mock">
                  <div className="set-theme-bar" style={{ background: t.chip }}/>
                  <div className="set-theme-bar short" style={{ background: t.chip }}/>
                </div>
                <div className="set-theme-label">
                  <span>{t.label}</span>
                  {prefs.theme === t.v && <CIcon name="check" size={13}/>}
                </div>
              </button>
            ))}
          </div>
        </SettingsGroup>

        {/* Location */}
        <SettingsGroup title="Location">
          <SetRow
            icon="pin"
            iconBg="var(--c-set-icbg-blue)"
            iconColor="var(--c-blue)"
            title="Current city"
            sub="Forecasts and alerts for this area"
            right={<><span className="set-row-val">{prefs.city}</span><CIcon name="chevron" size={14} color="var(--c-dim)"/></>}
            onClick={() => setOpenSheet("city")}
          />
          <div className="set-divider"/>
          <SetRow
            icon="globe"
            iconBg="var(--c-set-icbg-cyan)"
            iconColor="var(--c-cyan)"
            title="Language"
            sub="Forecast text and alerts"
            right={<><span className="set-row-val">{langLabel}</span><CIcon name="chevron" size={14} color="var(--c-dim)"/></>}
            onClick={() => setOpenSheet("lang")}
          />
          <div className="set-divider"/>
          <SetRow
            icon="sliders"
            iconBg="var(--c-set-icbg-amber)"
            iconColor="#D97706"
            title="Units"
            sub="Rainfall in mm, temp in °C"
            right={<>
              <span className="set-row-seg">
                <span className="on">Metric</span>
                <span>Imperial</span>
              </span>
            </>}
          />
        </SettingsGroup>

        {/* Notifications */}
        <SettingsGroup title="Notifications">
          <SetRow
            icon="bell"
            iconBg="var(--c-set-icbg-blue)"
            iconColor="var(--c-blue)"
            title="Push notifications"
            sub={prefs.notifications ? "On — alerts ring even on silent" : "Off — you won't get alerts"}
            right={<Toggle on={prefs.notifications} onChange={(v) => setPrefs({ notifications: v })}/>}
          />
          <div className="set-divider"/>
          <SetRow
            icon="alert"
            iconBg="var(--c-set-icbg-rose)"
            iconColor="var(--c-crit)"
            title="Critical alerts only"
            sub="Skip watch-level updates"
            right={<Toggle on={prefs.criticalOnly} onChange={(v) => setPrefs({ criticalOnly: v })} tone="rose"/>}
          />
          <div className="set-divider"/>
          <SetRow
            icon="moon"
            iconBg="var(--c-set-icbg-violet)"
            iconColor="#7C3AED"
            title="Quiet hours"
            sub="10 PM – 6 AM · critical alerts still ring"
            right={<Toggle on={prefs.quietHours} onChange={(v) => setPrefs({ quietHours: v })}/>}
          />
          <div className="set-divider"/>
          <SetRow
            icon="phone"
            iconBg="var(--c-set-icbg-emerald)"
            iconColor="#16A34A"
            title="SMS fallback"
            sub="Text alerts when offline"
            right={<Toggle on={prefs.sms} onChange={(v) => setPrefs({ sms: v })}/>}
          />
        </SettingsGroup>

        {/* Privacy */}
        <SettingsGroup title="Privacy & data">
          <SetRow
            icon="shieldCheck"
            iconBg="var(--c-set-icbg-emerald)"
            iconColor="#16A34A"
            title="Share anonymous data"
            sub="Helps us improve forecasts in your area"
            right={<Toggle on={prefs.shareData} onChange={(v) => setPrefs({ shareData: v })}/>}
          />
          <div className="set-divider"/>
          <SetRow
            icon="info"
            iconBg="var(--c-set-icbg-blue)"
            iconColor="var(--c-blue)"
            title="About HydroGuard"
            sub="Version 2.4.1"
            right={<CIcon name="chevron" size={14} color="var(--c-dim)"/>}
          />
        </SettingsGroup>

        {/* Sign out */}
        <button
          className="set-signout"
          onClick={() => {
            ["hg-tab", "hg-city", "hg-theme", "hg-prefs"].forEach(function(k) {
              localStorage.removeItem(k);
            });
            window.location.reload();
          }}
        >
          <CIcon name="logOut" size={16}/>Sign out
        </button>

        <div style={{ height: 12 }}/>
      </div>

      <Sheet open={openSheet === "city"} onClose={() => setOpenSheet(null)} title="Select city">
        <CityPicker value={prefs.city} onSelect={(c) => setPrefs({ city: c })} onClose={() => setOpenSheet(null)}/>
      </Sheet>
      <Sheet open={openSheet === "lang"} onClose={() => setOpenSheet(null)} title="Language" height="62%">
        <LangPicker value={prefs.lang} onSelect={(c) => setPrefs({ lang: c })} onClose={() => setOpenSheet(null)}/>
      </Sheet>
    </div>
  );
};

Object.assign(window, { SettingsScreen, PK_CITIES, LANGUAGES });
