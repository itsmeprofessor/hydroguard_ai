class Endpoints {
  Endpoints._();

  // Auth
  static const String login    = '/auth/login';
  static const String register = '/auth/register';
  static const String refresh  = '/auth/refresh';
  static const String me       = '/auth/me';
  static const String logout   = '/auth/logout';

  // Cities v2
  static const String cities         = '/api/v2/cities';
  static const String citiesOverview = '/api/v2/cities/overview';
  static const String citiesRefresh  = '/api/v2/cities/refresh';

  static String cityRisk(String slug)     => '/api/v2/cities/$slug/risk';
  static String cityForecast(String slug) => '/api/v2/cities/$slug/forecast';
  static String cityAlerts(String slug)   => '/api/v2/cities/$slug/alerts';
  static String cityStatus(String slug)   => '/api/v2/cities/$slug/status';
  static String cityTrain(String slug)    => '/api/v2/cities/$slug/train';
  static String cityPredict(String slug)  => '/api/v2/cities/$slug/predict';

  // System
  static const String health    = '/health';
  static const String anomalies = '/anomalies';

  // WebSocket — append ?token=<jwt> for authenticated channels
  static const String wsAnomalies = '/ws/anomalies';
  static const String wsRiskMap   = '/ws/risk-map';
  static const String wsHealth    = '/ws/health';
}
