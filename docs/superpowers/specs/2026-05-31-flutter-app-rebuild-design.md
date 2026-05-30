# HydroGuard AI — Flutter App Rebuild Design Spec
**Date:** 2026-05-31  
**Status:** Approved  
**Target:** `frontend/citizen_flutter_app/` (empty directory, start fresh with `flutter create`)

---

## 1. Project Overview

Full Flutter rebuild of the HydroGuard AI mobile/web app. Replaces the empty `citizen_flutter_app` directory with a production-quality app matching the JSX prototype at `D:\Programming\FYP\frontend design for fyp\Hydroguard App (5)\`.

The app serves two roles from a single binary:
- **Citizen shell** — flood risk monitoring, alerts, map, education, settings
- **Admin shell** — system operations, city HRI monitoring, model health

Role is determined from the JWT `role` field returned at login. Routing is enforced by GoRouter redirect guard.

**Backend:** FastAPI at `http://localhost:8000` (dev) / same-origin via nginx (production web build).  
**Flutter SDK:** 3.41.7 / Dart 3.11.5  
**Build target:** Web (`flutter build web`) + mobile (Android/iOS).

---

## 2. Tech Stack (exact versions)

```yaml
flutter_riverpod: ^2.6.1
dio: ^5.7.0
go_router: ^14.6.2
flutter_secure_storage: ^9.2.2
fl_chart: ^0.70.2
google_fonts: ^6.2.1
flutter_map: ^7.0.2
latlong2: ^0.9.1
web_socket_channel: ^3.0.1
shared_preferences: ^2.3.3
intl: ^0.19.0
```

---

## 3. Directory Structure

```
lib/
  main.dart
  core/
    theme/
      app_theme.dart        — ThemeData light/dark, color constants
      colors.dart           — all HG color tokens as static Color fields
      text_styles.dart      — Inter (sans) + JetBrains Mono text styles
    network/
      api_client.dart       — Dio singleton, auth interceptor, base URL
      endpoints.dart        — all URL string constants
    router/
      app_router.dart       — GoRouter, redirect guard, route definitions
    storage/
      secure_storage.dart   — flutter_secure_storage wrapper (tokens + role)
      local_storage.dart    — shared_preferences wrapper (profile, prefs)
  models/
    user_model.dart
    city_risk_model.dart    — buildCityPayload equivalent
    forecast_day_model.dart — buildForecastDays equivalent
    alert_item_model.dart   — transformAlert equivalent
    city_overview_model.dart
    driver_model.dart       — transformDrivers equivalent
    health_model.dart
  repositories/
    auth_repository.dart
    city_repository.dart
    admin_repository.dart
  shared/
    providers/
      auth_provider.dart
      city_provider.dart
      theme_provider.dart
      prefs_provider.dart
      ws_provider.dart
    widgets/
      hg_skeleton.dart
      hg_error_card.dart
      risk_pill.dart
      severity_ladder.dart
      hg_app_bar.dart
      bottom_sheet_modal.dart
  features/
    auth/
      login_screen.dart
      signup_screen.dart     — 2-step: credentials → city picker
      forgot_password_screen.dart
    citizen/
      shell/citizen_shell.dart — bottom nav (Home/Forecast/Map/Learn/Settings)
      home/home_screen.dart
      forecast/forecast_screen.dart
      alerts/alerts_screen.dart
      map/map_screen.dart
      learn/learn_screen.dart
      settings/settings_screen.dart
      profile/profile_screen.dart
    admin/
      shell/admin_shell.dart  — bottom nav (Dashboard/HRI/Alerts/Map/More)
      dashboard/dashboard_screen.dart
      city_hri/city_hri_screen.dart
      alerts/admin_alerts_screen.dart
      map/admin_map_screen.dart
      more/admin_more_screen.dart
```

---

## 4. Design System

### 4.1 Color Tokens

Translated from `v2-tokens.css`:

```dart
// Severity
static const safe     = Color(0xFF22C55E);
static const monitor  = Color(0xFF06B6D4);
static const watch    = Color(0xFFEAB308);
static const warning  = Color(0xFFF97316);
static const severe   = Color(0xFFEF4444);
static const evac     = Color(0xFFB91C1C);

// Soft backgrounds (light)
static const safeSoft    = Color(0xFFDCFCE7);
static const monitorSoft = Color(0xFFCFFAFE);
static const watchSoft   = Color(0xFFFEF3C7);
static const warningSoft = Color(0xFFFFEDD5);
static const severeSoft  = Color(0xFFFEE2E2);

// Brand
static const blue   = Color(0xFF2563EB);
static const cyan   = Color(0xFF0891B2);
static const violet = Color(0xFF7C3AED);

// Backgrounds
static const bgLight   = Color(0xFFF4F6FB);
static const bgDark    = Color(0xFF07090E);
static const cardLight = Color(0xFFFFFFFF);
static const cardDark  = Color(0xFF131823);

// Text
static const textLight = Color(0xFF0B1220);
static const textDark  = Color(0xFFF6F8FB);
static const muted     = Color(0xFF5B6573);
```

### 4.2 Typography

- **Sans:** `Inter` via `google_fonts` (all weights)
- **Mono:** `JetBrains Mono` via `google_fonts` (numbers, HRI scores, mono labels)

### 4.3 Risk Band → Scenario Mapping

```dart
enum RiskBand { low, moderate, high, severe }

extension RiskBandX on RiskBand {
  String get scenario => const {
    RiskBand.low:      'safe',
    RiskBand.moderate: 'watch',
    RiskBand.high:     'warning',
    RiskBand.severe:   'severe',
  }[this]!;
  
  Color get color => const {
    RiskBand.low:      Color(0xFF22C55E),
    RiskBand.moderate: Color(0xFFEAB308),
    RiskBand.high:     Color(0xFFF97316),
    RiskBand.severe:   Color(0xFFEF4444),
  }[this]!;
}
```

### 4.4 Home Screen Background Gradient

Scenario-driven gradient applied to Home screen container:
- `safe`    → `#E0F2FE` → `#F4F6FB` at 280px
- `watch`   → `#FEF3C7` → `#F4F6FB` at 280px
- `warning` → `#FFEDD5` → `#F4F6FB` at 280px
- `severe`  → `#FEE2E2` → `#FECACA` at 200px → `#F4F6FB` at 380px

---

## 5. Core Infrastructure

### 5.1 API Client (`api_client.dart`)

Dio singleton configured with:
- `baseUrl`: from `--dart-define=API_BASE` (empty string for web same-origin, `http://localhost:8000` for dev)
- **Auth interceptor**: injects `Authorization: Bearer <token>` on every request
- **401 handler**: calls `POST /auth/refresh`, retries original request once, force-logs out if refresh fails
- **No `Content-Type: application/json` on GET requests** (prevents CORS preflight)
- `connectTimeout`: 10s, `receiveTimeout`: 30s

### 5.2 Secure Storage

Stores: `access_token`, `refresh_token`, `role`, `username`.

### 5.3 GoRouter (`app_router.dart`)

```
/splash          — checks auth state, redirects
/login           — AuthV2 Login view
/signup          — AuthV2 Signup view (2-step)
/forgot-password — AuthV2 Forgot view

/citizen         — CitizenShell (ShellRoute)
  /citizen/home
  /citizen/forecast
  /citizen/map
  /citizen/learn
  /citizen/settings
  /citizen/profile

/admin           — AdminShell (ShellRoute)
  /admin/dashboard
  /admin/hri
  /admin/alerts
  /admin/map
  /admin/more
```

**Redirect guard logic:**
- No token → `/login`
- Token + role=USER → `/citizen/home` (if on root/splash)
- Token + role=ADMIN → `/admin/dashboard` (if on root/splash)
- Non-admin accessing `/admin/*` → `/citizen/home`

### 5.4 WebSocket Service (`ws_provider.dart`)

Manages three WebSocket connections:
- `/ws/anomalies?token=<jwt>` — alert events → prepend to alerts list
- `/ws/risk-map?token=<jwt>` — risk-map updates (admin dashboard)
- `/ws/health` — public health stream → update health state

Start all on login. Stop all on logout. Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s).

---

## 6. Data Models

### 6.1 CityRiskModel (`city_risk_model.dart`)

**Critical:** `alert_tier` from backend returns a dict `{ min, max, level, label, tier }` — NOT an int. Use `alert_tier_label` as the reliable field:

```dart
factory CityRiskModel.fromJson(Map<String, dynamic> json) {
  final tierLabel = json['alert_tier_label'] as String? ?? 'NORMAL';
  final alertTier = tierLabel == 'ALERT' ? 4 : tierLabel == 'ADVISORY' ? 2 : 1;
  
  final riskBand = json['risk_band'] as String? ?? 'Low';
  final levelKey = _riskBandToScenario[riskBand] ?? 'safe';
  
  final wi = json['weather_inputs'] as Map<String, dynamic>? ?? {};
  final sc = json['sequence_context'] as Map<String, dynamic>? ?? {};
  
  return CityRiskModel(
    // Identity
    levelKey: levelKey,
    level: _scenarioToLevel[levelKey] ?? 'Safe',
    riskBand: riskBand,
    city: json['city'] as String? ?? '',
    citySlug: json['city_slug'] as String? ?? '',
    inferredAt: json['inferred_at'] as String?,
    
    // Risk
    hriScore: (json['hri_score'] as num?)?.toInt() ?? 0,
    uncertainty: ((json['uncertainty'] ?? json['epistemic_uncertainty'] ?? 0.0) as num).toDouble(),
    alertTier: alertTier,
    alertTierLabel: tierLabel,
    pushNotification: json['push_notification'] as bool? ?? false,
    isAlert: json['is_alert'] as bool? ?? false,
    eventProbability: (json['event_probability'] as num?)?.toDouble() ?? 0.0,
    
    // Model state
    stability: json['prediction_stability'] as String? ?? 'stable',
    source: json['source'] as String? ?? 'model',
    isHeuristic: json['source'] == 'heuristic',
    inferenceMode: json['inference_mode'] as String? ?? 'mc_dropout',
    mcCompleted: (json['mc_samples_completed'] as num?)?.toInt() ?? 0,
    mcRequested: (json['mc_samples_requested'] as num?)?.toInt() ?? 0,
    tcnActive: sc['tcn_active'] != false,
    bufferSize: (sc['buffer_size'] as num?)?.toInt() ?? 0,
    requiredSize: (sc['required_size'] as num?)?.toInt() ?? 30,
    modelVersion: json['model_version'] as String? ?? '',
    degradedReason: json['degraded_reason'] as String?,
    
    // Weather inputs
    prcp: (wi['prcp'] as num?)?.toDouble(),
    tavg: (wi['tavg'] as num?)?.toDouble(),
    humidity: (wi['humidity'] as num?)?.toDouble(),
    pressure: (wi['pressure'] as num?)?.toDouble(),
    wspd: (wi['wspd'] as num?)?.toDouble(),
    cloudCover: (wi['cloud_cover'] as num?)?.toDouble(),
    
    // Drivers (SHAP)
    drivers: DriverModel.fromRawList(json['drivers'] as List? ?? []),
  );
}
```

### 6.2 DriverModel

Handles both v3.3 shape `{ feature, shap, value }` and legacy `{ display_name, direction, weight }`:

```dart
factory DriverModel.fromRaw(Map<String, dynamic> d) {
  if (d['shap'] != null) {
    final shap = (d['shap'] as num).toDouble();
    final featureName = d['display_name'] as String? ?? d['feature'] as String? ?? 'Unknown';
    final plain = featureName.replaceAll('_', ' ').split(' ')
        .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}').join(' ');
    return DriverModel(
      plain: plain,
      tech: d['value'] != null ? '${d['feature']} = ${(d['value'] as num).toStringAsFixed(2)}' : d['feature'] as String? ?? '',
      direction: shap >= 0 ? 'up' : 'down',
      weight: shap.abs(),
    );
  }
  // legacy shape
  ...
}
```

### 6.3 ForecastDayModel

Maps `GET /api/v2/cities/{slug}/forecast` → `{ date, risk_band, hri_score, daily_precip_mm, max_temp_c, min_temp_c, daily_chance_rain }`.

### 6.4 AlertItemModel

Transforms raw predict_v2 results from `/alerts` endpoint and WebSocket events. Key fields: `id` (from `inference_id`), `kind` (from `risk_band`), `title`, `relativeTime` (from `inferred_at`), `drivers`, `hriScore`, `tierLabel`.

---

## 7. Screen Specifications

### 7.1 Auth Screens

**Login:**
- Dark background with blue/cyan radial gradient SVG overlay (as prototype)
- HydroGuard logo (water drop icon + wordmark)
- Email + password fields, show/hide password toggle
- "Forgot password?" link → ForgotPassword screen
- Submit → `POST /auth/login` → stores tokens + role → GoRouter redirect

**Signup (2-step):**
- Step 1: Full name, username (alphanumeric/underscore), email, phone (UI only), password (min 8, strength meter), confirm password, terms checkbox
- API call `POST /auth/register` happens after Step 1 validation. On success → Step 2.
- Step 2: City picker grid from API cities list. "Get started" → navigates to citizen home.
- Step indicator (2 dots) in top bar.

**Forgot Password:**
- Back button, lock icon, "contact administrator" message with email link.

### 7.2 Citizen Home Screen

Components (top to bottom):
1. **App bar** — avatar icon (→ Settings), "Good day · [City]" dropdown, bell icon with badge
2. **Hero section** — gradient background, `[scenario] level` label with colored dot, alert tier chip + stability chip + heuristic badge, headline text, paragraph
3. **Severity ladder** — 6-segment colored bar (Safe/Monitor/Watch/Warning/Severe/Evac) with current segment highlighted
4. **Live metrics row** — Rainfall/Temp/HRI with trend indicators
5. **AI confidence card** — "HydroGuard ML · forecast confidence", body text, progress bar, percentage
6. **Live weather card** — city + source label, weather icon + temp + condition + feels-like, rain, humidity/wind/pressure/cloud stats row
7. **Risk trajectory card** — `fl_chart LineChart` with solid past line + dashed projection (3 synthetic forward points via linear extrapolation from last 2 real points) + confidence band shading. Data sourced from last N alerts' HRI scores.
8. **SHAP drivers panel** — renders only when `alertTier >= 3`. Up/down arrow + plain name + tech label + weight bar per driver.
9. **Event lifecycle bar** — renders when `alertTier >= 2`. 7-stage horizontal stepper (Monitoring→Formation→Escalation→Escalation→Active→Peak→Stabilizing→Recovery), current stage derived from `hriToLifecycle(hriScore)`.
10. **CTA banner** — renders when `levelKey` is watch/warning/severe. "Safety steps" + "Share" buttons.
11. **I'm safe button** — renders when warning/severe.
12. **Next days mini-bar** — Today + 4 days from forecast, weather icon + mm. Taps to Forecast tab.
13. **Advice cards** — 2-3 contextual advice items keyed by `levelKey` from `HG_ADVICE` constants.
14. **Family safety quick-actions** — 4 buttons: Check circle / Emergency kit / Rescue 1122 / Report issue.

**HG_STABILITY constants (Dart):**
```dart
const stability = {
  'stable':     (label: 'Stable prediction',       tone: 'safe'),
  'warming_up': (label: 'Model warming up',         tone: 'watch'),
  'degraded':   (label: 'Reduced confidence mode',  tone: 'warning'),
};
```

**HG_TIERS constants (Dart):**
```dart
const tiers = {
  1: (label: 'NORMAL',   tone: 'safe'),
  2: (label: 'ADVISORY', tone: 'watch'),
  3: (label: 'ADVISORY', tone: 'watch'),
  4: (label: 'ALERT',    tone: 'warning'),
  5: (label: 'ALERT',    tone: 'severe'),
};
```

**HG_LIFECYCLE (7 stages):** Monitoring · Formation · Escalation · Active · Peak risk · Stabilizing · Recovery  
`hriToLifecycle(hri)`: ≤5→monitoring, ≤20→formation, ≤50→escalation, ≤75→active, else→peak

### 7.3 Citizen Forecast Screen

1. **App bar** — "Forecast" / city name / share icon
2. **Daily precipitation hero** — `fl_chart BarChart`, 7 bars, today's bar colored by risk band, others blue gradient. Bar heights from `daily_precip_mm`.
3. **7-day outlook rows** — date, weather icon (colored by risk band), condition label, % flood probability OR % chance of rain, precipitation mm.
4. **Compare with other cities** — horizontal bar chart from `/api/v2/cities/overview`, sorted descending HRI, current city labeled "(you)".

### 7.4 Citizen Alerts Screen

1. **App bar** — "Tier [N] · [LABEL]" / city / filter icon
2. **Evacuation banner** — renders only when `levelKey == severe`
3. **Alert level ladder** — same 6-segment bar, current level label highlighted + underlined
4. **Alert feed** — `ListView` of alert cards. Each card: colored left stripe, title, relative timestamp, risk pill, source label, description. First alert (if warning/severe) shows SHAP drivers inline.
5. **WebSocket** — prepends new events from `/ws/anomalies` in real time, list capped at 20.
6. **Alert history** — simple count card with 7-bar sparkline.

### 7.5 Citizen Map Screen

1. **Full-bleed `flutter_map` with OpenStreetMap tiles** (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`)
2. **City marker** — blue pulsing circle + pin at city lat/lon from API. Lat/lon available in city metadata (`CITY_METADATA` in backend has lat/lon for all 6 cities).
3. **3 static shelter POIs** — marked with green cross icons at hardcoded offsets from city center. Disclaimer: "Example locations — actual GIS integration required."
4. **Layer switcher** — 4 buttons (Radar/Sensors/Shelters/Routes) — toggle visibility of POI layers (all decorative/demo).
5. **Search bar overlay** — UI only, no actual geocoding.
6. **Live status pill** — top-left, shows current city + risk level.
7. **Bottom sheet** — 3 POI rows: Nearest shelter / Emergency hospital / Rescue 1122 (tel:1122 link).

### 7.6 Citizen Learn Screen

Fully static content (no API calls):
1. **Prep score ring** — `fl_chart` ring / custom `CustomPainter` circle. Score = done/total × 100. Persisted to SharedPreferences.
2. **Readiness checklist** — 7 items (kit/plan/contacts/route/docs/water/radio), toggle state stored in SharedPreferences.
3. **Guide cards grid** — 6 cards in 2-column grid, gradient header + title + duration label.
4. **Quiz CTA card** — "Test what you know" → show coming soon SnackBar.

### 7.7 Citizen Settings Screen

Groups:
- **Appearance** — theme picker (Light/Dark/Auto) with 3 visual mock cards showing preview
- **Location & Language** — GPS toggle, city picker (opens bottom sheet with search + list from API), language picker (6 options in bottom sheet), Units (Metric, read-only)
- **Notifications** — 4 toggles: Push notifications / Critical alerts only / Quiet hours / SMS fallback
- **Accessibility** — Larger text / High-contrast / Voice alerts
- **Privacy** — Share anonymous data toggle / About HydroGuard row
- **Sign out** button

All prefs stored in SharedPreferences via `prefsProvider`.

### 7.8 Citizen Profile Screen

- **App bar** — back to Settings, "Profile" title, edit/save/cancel icon
- **Avatar hero** — gradient initials avatar (8 themes selectable), photo upload (local only), display name, "Member since [month year]", stats row (home city / role / prep score)
- **Account information** (read-only from API): username, email, account type — labeled "From server"
- **Personal information** (SharedPreferences): display name, phone, CNIC, DOB, blood type — labeled "Saved locally on this device"
- **Address**: street address, city picker
- **Emergency contact**: name, relationship, phone
- **Medical notes**: free text
- Edit mode: all local fields become editable inline. Save button at bottom.

### 7.9 Admin Dashboard Screen

1. **App bar** — user icon (→ profile), "ADMIN · Operations · NDMA" + city + drift chip, bell with badge
2. **Hero KPI row** — Active alerts (from `/anomalies?anomalies_only=true&limit=1` → `total`) / Models live (from `/health` → `city_models.trained_cities / total_cities`) / WS clients (from `/health` → `ws_connections` summed)
3. **System health bars** — 3 bars: HRI engine (trained/total %) / Data ingest (WeatherAPI live) / Drift monitor (PSI status from `/health.drift`)
4. **Per-city model state** — first 4 cities from overview, source pill (Model/Heuristic) + stability label + HRI score
5. **Live event feed** — top 5 cities sorted by HRI, colored dot + risk level + HRI
6. **Operations quick-actions** — 4 buttons: Issue Alert (→ predict endpoint, simple SnackBar for now) / HRI Models (→ City HRI tab) / Dispatch (coming soon) / Reports (coming soon)
7. **National HRI grid** — dark card, top 6 cities sorted by HRI, bar + score + risk band label

### 7.10 Admin City HRI Screen

1. **App bar** — back arrow, "City HRI" / trained count
2. **Band distribution bar** — horizontal segmented bar showing proportion by risk band (Severe/Warning/Watch/Monitor/Low risk)
3. **Legend chips** — count + color per band
4. **Full city list** (all cities from overview, sorted descending HRI):
   - Colored dot + city slug (3 chars) + city name
   - Small label: "Heuristic mode — no trained model" OR "[TIER_LABEL] · ML update live"
   - HRI score (colored by band)
   - Risk pill

### 7.11 Admin Alerts Screen

Same structure as Citizen Alerts screen. WebSocket connected to `/ws/anomalies`.

### 7.12 Admin Map Screen

Same as Citizen Map screen. No admin-specific additions.

### 7.13 Admin More Screen

1. **User profile row** — avatar initials, username, email, ADMIN chip
2. **System status** — backend health pill from `/ws/health` WebSocket
3. **Operations**:
   - "Refresh city registry" → `POST /api/v2/cities/refresh` (admin auth), shows success/error SnackBar
4. **About**:
   - App version (from build metadata or hardcoded "v3.3.0")
   - Backend version (from `/health`)
   - API docs link (open `/docs` in browser)
5. **Sign out** button

---

## 8. State Management

All state via Riverpod providers:

| Provider | Type | Scope |
|---|---|---|
| `authProvider` | `StateNotifier<AuthState>` | global — auth status + user |
| `cityProvider` | `StateNotifier<CityState>` | global — selected city + risk data |
| `themeProvider` | `StateNotifier<ThemeMode>` | global — light/dark/system |
| `prefsProvider` | `StateNotifier<AppPrefs>` | global — city pref, lang, notification toggles |
| `citiesListProvider` | `FutureProvider` | cities list from API |
| `overviewProvider` | `FutureProvider` | cities overview from API |
| `forecastProvider(slug)` | `FutureProvider.family` | 7-day forecast per city |
| `alertsProvider(slug)` | `StateNotifier` | alerts list + WS prepend |
| `healthProvider` | `StateNotifier` | health data from WS stream |
| `wsProvider` | `Provider` | WsService singleton |

---

## 9. API Integration

### Endpoints Used

| Screen | Endpoint |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/register`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout` |
| Home | `GET /api/v2/cities/{slug}/risk` (refresh on pull-to-refresh) |
| Forecast | `GET /api/v2/cities/{slug}/forecast`, `GET /api/v2/cities/overview` |
| Alerts | `GET /api/v2/cities/{slug}/alerts?n=20`, `WS /ws/anomalies` |
| Map | City lat/lon from cities list (embedded in city metadata) |
| Settings | `GET /api/v2/cities` (city picker) |
| Admin Dashboard | `GET /health`, `GET /anomalies?anomalies_only=true&limit=1`, `GET /api/v2/cities/overview`, `WS /ws/health` |
| Admin City HRI | `GET /api/v2/cities/overview` |
| Admin More | `POST /api/v2/cities/refresh` |

### CORS Rules

- Use `Authorization: Bearer <token>` header
- Do NOT set `Content-Type: application/json` on GET requests
- Backend allows `*` origin — no credentials mode on web

---

## 10. WebSocket Integration

`WsService` class manages all 3 WebSocket channels:

```dart
class WsService {
  void startAll(String token) {
    _connectAnomalies(token);  // → alertsProvider.prepend()
    _connectRiskMap(token);    // → overviewProvider.refresh()
    _connectHealth();          // → healthProvider.update()
  }
  
  void stopAll() { /* close all channels */ }
}
```

Lifecycle:
- `startAll()` called after successful login
- `stopAll()` called on logout
- Auto-reconnect with exponential backoff on disconnect (1s → 2s → 4s → 8s → max 30s)

---

## 11. Build Orchestration

Three-wave agent build to avoid context overflow and file conflicts:

**Wave 1 (Foundation):** `flutter create` + pubspec.yaml + all core infrastructure + all models + all repositories + all providers + auth screens + both shell widgets + empty screen stubs for all screens.

**Wave 2 (Citizen screens) + Wave 3 (Admin screens):** Run in parallel. Each agent reads Wave 1 output and fills in only `lib/features/citizen/` or `lib/features/admin/`. No shared file writes.

**Wave 4 (QA):** `flutter analyze --no-fatal-infos`, verify zero compile errors.

---

## 12. Constraints

- All API calls go through `ApiClient` (Dio) — no direct `http` package usage
- `flutter_secure_storage` for tokens/role only; user prefs and local profile in `SharedPreferences`
- No `Content-Type: application/json` on GET requests
- `alert_tier` field from backend must use `alert_tier_label` for normalization (not `alert_tier.level`)
- `source == "heuristic"` means heuristic mode; any other value (including "city_model") is model-backed
- Map screen uses `flutter_map` + OSM tiles — not SVG
- WebSocket auth uses `?token=<jwt>` query param — not Authorization header (browsers cannot send custom headers on WS)
- All screens handle loading skeleton state and error state with retry
- `flutter build web` with `--dart-define=API_BASE=''` for production nginx deployment
