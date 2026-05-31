class HealthModel {
  final String status;
  final int trainedCities;
  final int totalCities;
  final List<String> criticalDriftCities;
  final List<String> warnDriftCities;
  final Map<String, int> wsConnections;

  const HealthModel({
    required this.status,
    required this.trainedCities,
    required this.totalCities,
    required this.criticalDriftCities,
    required this.warnDriftCities,
    required this.wsConnections,
  });

  factory HealthModel.fromJson(Map<String, dynamic> json) {
    final cm    = json['city_models']    as Map<String, dynamic>? ?? {};
    final drift = json['drift']          as Map<String, dynamic>? ?? {};
    final ws    = json['ws_connections'] as Map<String, dynamic>? ?? {};
    return HealthModel(
      status:              json['status'] as String? ?? 'ok',
      trainedCities:       (cm['trained_cities'] as num?)?.toInt() ?? 0,
      totalCities:         (cm['total_cities'] as num?)?.toInt() ?? 0,
      criticalDriftCities: (drift['critical_cities'] as List?)?.cast<String>() ?? [],
      warnDriftCities:     (drift['warn_cities'] as List?)?.cast<String>() ?? [],
      wsConnections:       ws.map((k, v) => MapEntry(k, (v as num).toInt())),
    );
  }

  int get totalWsClients => wsConnections.values.fold(0, (a, b) => a + b);
  bool get hasCriticalDrift => criticalDriftCities.isNotEmpty;
  bool get hasWarnDrift => warnDriftCities.isNotEmpty;
  String get driftStatus => hasCriticalDrift ? 'critical' : hasWarnDrift ? 'warn' : 'ok';
  double get modelCoveragePct => totalCities > 0 ? trainedCities / totalCities : 0.0;
}
