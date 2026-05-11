# HydroGuard AI — Citizen Flutter App

Mobile citizen app for Pakistan flood early-warning. Mirrors the web citizen app design
with full backend integration.

## Screens
| Screen | Description |
|--------|-------------|
| **Home** | HRI gauge, scenario hero (safe/warn/crit), weather stats, 7-day forecast strip |
| **Forecast** | Area chart, 7-day breakdown cards with risk, temperature, rainfall |
| **Alerts** | Filter pills, alert cards with expandable "Safety steps", Rescue 1122 CTA |
| **Learn** | Cloudburst guide, 6 expandable topic cards, emergency contacts with call buttons |
| **Settings** | City picker sheet, dark mode, language (6), units, notifications, about |

## Setup

```bash
cd frontend/citizen_flutter_app
flutter pub get
flutter run
```

## API configuration

By default the app targets `http://10.0.2.2:8000` (Android emulator → host machine port 8000).

| Environment | URL |
|-------------|-----|
| Android emulator | `http://10.0.2.2:8000` |
| Physical device (same WiFi) | `http://192.168.x.x:8000` |
| Production | `https://your-domain.com` |

Override at build time:
```bash
flutter run --dart-define=API_BASE=http://192.168.1.100:8000
```

## Backend endpoints used

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v2/cities` | City list |
| GET | `/api/v2/cities/{city}/risk` | Current risk |
| GET | `/cities/{city}/forecast` | 7-day forecast (v1) |
| GET | `/api/v2/cities/{city}/alerts` | Recent alerts |
| GET | `/health` | API health / About info |

## Dependencies

- `provider` — state management
- `http` — API calls with retry + TTL cache
- `shared_preferences` — city / theme / prefs persistence
- `url_launcher` — tel: links for emergency contacts
- `intl` — date formatting
- `flutter_animate` — entrance animations
