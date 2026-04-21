# HydroGuard-AI — Phase 1 + 3 + 4 + 5 integration guide

Full stabilization + UI unification bundle for your Flutter app, HTML
dashboard, and FastAPI backend.

## What this bundle contains

```
README.md                             ← this file
cleanup_old_widgets.sh                ← remove stale widget files safely

lib/                                  ← Flutter code (drop into weather_anomaly_app/lib)
├── main.dart                         ← REPLACE
├── core/theme/design_system.dart     ← NEW (1:1 with dashboard CSS tokens)
├── providers/
│   ├── location_provider.dart        ← REPLACE (was 0-byte in archive)
│   └── weather_provider.dart         ← REPLACE (was 0-byte in archive)
├── screens/
│   ├── splash_screen.dart            ← REPLACE (enters AppShell)
│   ├── home_screen.dart              ← REPLACE (dashboard-style)
│   ├── analytics_screen.dart         ← NEW
│   ├── history_screen.dart           ← REPLACE (filter + detail sheet)
│   └── settings_screen.dart          ← REPLACE (backend URL presets)
├── shell/
│   └── app_shell.dart                ← NEW (topbar + bottom nav)
└── widgets/dashboard/
    ├── dashboard_card.dart           ← NEW
    ├── metric_card.dart              ← NEW
    ├── primitives.dart               ← NEW (RiskMeter/ScoreBar/Banner/Badge…)
    └── charts.dart                   ← NEW (fl_chart styled as Chart.js)

backend/
├── analytics_aliases.py              ← NEW → app/api/routes/
├── MAIN_PY_PATCHES.md                ← CORS + router registration snippet
└── smoke_test.sh                     ← verify every endpoint in < 5 s

web_dashboard/
└── settings_presets_patch.html       ← optional: add 3 URL presets to admin panel
```

## Install order

### 1. Backend (do this first)

```bash
cd backend/

# Copy the alias routes module
cp path/to/bundle/backend/analytics_aliases.py app/api/routes/

# Patch app/main.py per backend/MAIN_PY_PATCHES.md
#   - Add CORSMiddleware
#   - Register analytics_aliases.router

# Restart
uvicorn app.main:app --reload
```

Verify:

```bash
chmod +x path/to/bundle/backend/smoke_test.sh
path/to/bundle/backend/smoke_test.sh http://127.0.0.1:8000
```

You should see 7 green checkmarks. If `/predict` fails, check the backend
log — the smoke test sends a minimal valid payload, and any failure there
usually means a schema mismatch in your `PredictionResponse`.

### 2. Flutter app

```bash
cd frontend/weather_anomaly_app

# Drop in all lib/ files, preserving paths.
# Overwrite the 5 REPLACE files; create new directories for NEW files.

# Clean up stale widgets (safe — script checks for imports first)
chmod +x path/to/bundle/cleanup_old_widgets.sh
path/to/bundle/cleanup_old_widgets.sh

flutter clean
flutter pub get
flutter analyze           # expect 0 errors
flutter run
```

### 3. HTML dashboard (optional — for preset UI parity)

Merge `web_dashboard/settings_presets_patch.html` into
`frontend/web_dashboard/admin_dashboard/index.html` as instructed in the
comment header. Or skip it — the dashboard already works once the backend
aliases are live.

## Provider contract (verified against your real files)

The new screens reference these members only. All exist on your providers:

- **`LocationProvider`**: `initialize()`, `getCurrentLocation()`,
  `setCity(String)` (sync void), `latitude`, `longitude`, `currentCity`,
  `currentRegion`, `currentCountry`, `currentPosition`, `isLoading`, `error`,
  `permissionGranted`, `clearError()`
- **`WeatherProvider`**: `fetchWeatherAndAnalyze(...)`, `analyzeAnomaly()`,
  `refresh(...)`, `fetchByCity(String, String)`, `loadAnomalyHistory()` (no
  args), `checkApiHealth()`, `updateLocation(LocationProvider)`,
  `testExtremeWeather()`, `setMockDataMode(bool)`, `clearErrors()`,
  `currentWeather`, `currentAnomaly`, `anomalyHistory`, `weatherStatus`,
  `anomalyStatus`, `weatherError`, `anomalyError`, `isApiHealthy`,
  `isOffline`, `useMockData`, `isLoading`, `hasData`, `hasAnomaly`,
  `lastUpdated`, `cacheTimestamp`, `cacheAgeDescription`
- **`SettingsProvider`**: unchanged. Screen uses `apiUrl`, `setApiUrl`,
  `notificationsEnabled`, `setNotificationsEnabled`, `autoRefresh`,
  `setAutoRefresh`, `refreshInterval`, `resetToDefaults`.

## Dependencies

**Zero new packages required.** Every import in the new code
(`fl_chart`, `geocoding`, `geolocator`, `google_fonts`, `hive_flutter`,
`intl`, `provider`) is already declared in your `pubspec.yaml`.

### One compatibility note

The new widgets use `Color.withValues(alpha: ...)` — the non-deprecated
API introduced in **Flutter 3.27 / Dart SDK ≥ 3.6**. Your pubspec allows
any `sdk: '>=3.0.0 <4.0.0'`, so the actual behavior depends on which
Flutter you have installed.

Check with:

```bash
flutter --version
```

- **Flutter ≥ 3.27**: compiles cleanly.
- **Flutter < 3.27**: you'll see ~14 errors like
  `The method 'withValues' isn't defined for the type 'Color'`.
  Fix with a one-shot sed:

  ```bash
  cd frontend/weather_anomaly_app
  grep -rl "withValues" lib/ | \
    xargs sed -i 's/\.withValues(alpha: \([^)]*\))/\.withOpacity(\1)/g'
  ```

## Backend endpoint mapping

| Client calls                | Backend route       | Source             |
|-----------------------------|---------------------|--------------------|
| `GET /health`               | existed             | `system.py`        |
| `GET /model/info`           | existed             | `system.py`        |
| `POST /predict`             | existed             | `prediction.py`    |
| `POST /predict/batch`       | existed             | `prediction.py`    |
| `GET /anomalies?…`          | existed             | `anomalies.py`     |
| `GET /anomalies/statistics` | existed             | `anomalies.py`     |
| `GET /database/statistics`  | added by patch      | `analytics_aliases.py` |
| `GET /analytics`            | added by patch      | `analytics_aliases.py` |

The Flutter app only needs `/health`, `/predict`, `/anomalies`, and
`/risk-map`. The two alias routes are purely for the HTML dashboard.

## Demo-day checklist

- **Localhost mode**: Flutter Settings → tap `Localhost` preset →
  `Test /health`. Green OK means the whole stack is wired.
- **LAN mode (phone demo)**: Edit `lib/screens/settings_screen.dart`
  line ~31 — change `192.168.1.100:8000` to your laptop's actual LAN IP
  (find with `ip a | grep inet` on Linux or `ipconfig` on Windows).
  Or just type the real IP once into the custom input field — Hive
  persists it across restarts.
- **Deployed mode**: Edit the deployed preset URL on line ~32 to your
  actual Render / Railway / ngrok URL.

## Runtime URL switching

Settings screen → pick a preset, or paste a custom URL, tap the ✓ icon →
the SettingsProvider persists to Hive and immediately calls
`AnomalyApiService.setBaseUrl(...)`. Next API call uses the new URL.
No app restart required.

## What's intentionally NOT done (per your non-negotiables)

- No Riverpod / Bloc migration
- No Flutter port of the HTML dashboard
- No ML model retraining or schema changes
- No new architectural layers (no GoRouter, no DI container, no
  clean-architecture rewrite)
- No visual changes to the HTML dashboard beyond the optional settings patch

## Files you can safely delete after drop-in

The `cleanup_old_widgets.sh` script handles this, but for reference:

- `lib/widgets/hri_gauge.dart` — nothing imports it anymore
- `lib/widgets/metric_card.dart` — replaced by `widgets/dashboard/metric_card.dart`
- `lib/utils/app_theme.dart` — replaced by `core/theme/design_system.dart`

The script only deletes these if no file outside the deleted set still
imports them, so you can run it safely.
