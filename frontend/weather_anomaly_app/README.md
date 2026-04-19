# 🌦️ Weather Anomaly Detection App

A beautiful, cross-platform Flutter application for real-time weather anomaly detection and flash flood early warning.

## ✨ Features

- 📍 **Auto Location Detection** - Automatically fetches user's location on startup
- 🌡️ **Live Weather Data** - Fetches real-time weather from OpenWeatherMap API
- 🤖 **AI-Powered Analysis** - Sends data to your trained ML model for anomaly detection
- 🚨 **Cloudburst Alerts** - Special warnings for flash flood conditions
- 📊 **Detailed Metrics** - View all weather parameters and anomaly scores
- 📜 **History Tracking** - Keep track of past anomalies
- 🌙 **Dark/Light Mode** - Beautiful UI with theme support
- 📱 **Cross-Platform** - Works on Android, iOS, Windows, macOS, Linux, and Web

## 📸 Screenshots

| Home Screen | Anomaly Alert | Settings |
|-------------|---------------|----------|
| Weather Card | Cloudburst Warning | API Config |

## 🚀 Getting Started

### Prerequisites

- Flutter SDK 3.0+
- Dart 3.0+
- Android Studio / VS Code
- Your backend server running

### Installation

1. **Clone the repository**
```bash
cd weather_anomaly_app
```

2. **Install dependencies**
```bash
flutter pub get
```

3. **Configure API Keys**

Edit `lib/utils/constants.dart`:
```dart
// Get free API key from: https://openweathermap.org/api
static const String openWeatherApiKey = 'YOUR_API_KEY_HERE';

// Your backend server URL
static const String anomalyApiBaseUrl = 'http://YOUR_SERVER_IP:8000';
```

4. **Run the app**
```bash
# For Android/iOS
flutter run

# For Web
flutter run -d chrome

# For Windows
flutter run -d windows

# For macOS
flutter run -d macos
```

## 🔧 Configuration

### Backend Server URL

The app needs to connect to your Python FastAPI backend:

1. **Same machine (development)**:
   ```dart
   static const String anomalyApiBaseUrl = 'http://127.0.0.1:8000';
   ```

2. **Local network (mobile testing)**:
   ```dart
   // Use your computer's local IP
   static const String anomalyApiBaseUrl = 'http://192.168.1.100:8000';
   ```

3. **Production (deployed server)**:
   ```dart
   static const String anomalyApiBaseUrl = 'https://your-server.com';
   ```

### Weather API

Get a free API key from [OpenWeatherMap](https://openweathermap.org/api):
1. Create an account
2. Go to API Keys section
3. Generate a new key
4. Add to `constants.dart`

## 📁 Project Structure

```
lib/
├── main.dart                 # App entry point
├── models/
│   ├── weather_data.dart     # Weather data model
│   └── anomaly_result.dart   # Anomaly result model
├── providers/
│   ├── location_provider.dart    # Location state management
│   ├── weather_provider.dart     # Weather & anomaly state
│   └── settings_provider.dart    # App settings
├── services/
│   ├── weather_api_service.dart  # Weather API calls
│   └── anomaly_api_service.dart  # Backend API calls
├── screens/
│   ├── splash_screen.dart    # Loading screen
│   ├── home_screen.dart      # Main dashboard
│   ├── settings_screen.dart  # Settings page
│   └── history_screen.dart   # Anomaly history
├── widgets/
│   ├── weather_card.dart         # Weather display
│   ├── anomaly_status_card.dart  # Anomaly status
│   ├── weather_details_grid.dart # Weather details
│   └── cloudburst_alert.dart     # Alert banner
└── utils/
    ├── app_theme.dart        # Theme configuration
    └── constants.dart        # App constants
```

## 🎨 UI Features

### Risk Level Colors
- 🟢 **LOW** - Green (#10B981)
- 🟡 **MEDIUM** - Orange (#F59E0B)
- 🔴 **HIGH** - Red (#EF4444)
- 🟣 **CRITICAL** - Purple (#7C3AED)

### Animations
- Smooth transitions using `flutter_animate`
- Pull-to-refresh for data updates
- Shake animation for cloudburst alerts
- Fade-in animations for cards

## 🔌 API Integration

### Weather Data Flow
```
1. App starts
   ↓
2. Get user location (GPS)
   ↓
3. Fetch weather from OpenWeatherMap
   ↓
4. Convert to API format
   ↓
5. Send to your ML backend (/predict)
   ↓
6. Display anomaly results
```

### API Endpoints Used
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check server status |
| `/predict` | POST | Analyze weather data |
| `/anomalies` | GET | Get history |

## 📱 Platform-Specific Setup

### Android
Add to `android/app/src/main/AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.INTERNET" />
```

### iOS
Add to `ios/Runner/Info.plist`:
```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>This app needs location access to show local weather</string>
<key>NSLocationAlwaysUsageDescription</key>
<string>This app needs location access to monitor weather</string>
```

### Web
No additional configuration needed.

### Windows/macOS/Linux
Location services may require additional permissions depending on the OS.

## 🧪 Testing

### Test with Mock Data
In `weather_provider.dart`, set:
```dart
bool _useMockData = true;  // Use mock data without API
```

### Test Extreme Weather
Use the "Test Alert" button on the home screen to simulate extreme weather conditions.

## 🔒 Privacy

- Location data is only used locally to fetch weather
- No personal data is sent to external servers
- Weather data is sent only to your configured backend

## 🐛 Troubleshooting

### "API Offline" message
- Make sure your Python backend is running
- Check the API URL in settings
- Ensure your device can reach the server

### Location not working
- Check location permissions in device settings
- Make sure GPS is enabled
- Try restarting the app

### Weather not loading
- Verify OpenWeatherMap API key is correct
- Check internet connection
- API might have rate limits (1000 calls/day free)

## 📄 License

MIT License

## 👨‍💻 Author

**Zain** - NUML Islamabad

## 🙏 Credits

- [Flutter](https://flutter.dev/)
- [OpenWeatherMap](https://openweathermap.org/)
- [Provider](https://pub.dev/packages/provider)
- [Geolocator](https://pub.dev/packages/geolocator)
