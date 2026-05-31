import 'driver_model.dart';

const _riskBandToScenario = {
  'Low':      'safe',
  'Moderate': 'watch',
  'High':     'warning',
  'Severe':   'severe',
};

const _scenarioToLevel = {
  'safe':    'Safe',
  'watch':   'Watch',
  'warning': 'Warning',
  'severe':  'Severe',
};

class CityRiskModel {
  // Identity
  final String levelKey;
  final String level;
  final String riskBand;
  final String city;
  final String citySlug;
  final String? inferredAt;

  // Risk
  final int    hriScore;
  final double uncertainty;
  final int    alertTier;       // normalised 1/2/4 from alertTierLabel
  final String alertTierLabel;  // "NORMAL" | "ADVISORY" | "ALERT"
  final bool   pushNotification;
  final bool   isAlert;
  final double eventProbability;

  // Model state
  final String  stability;      // "stable" | "warming_up" | "degraded"
  final String  source;         // "city_model" | "heuristic" | etc.
  final bool    isHeuristic;
  final String  inferenceMode;  // "mc_dropout" | "fallback_deterministic"
  final int     mcCompleted;
  final int     mcRequested;
  final bool    tcnActive;
  final int     bufferSize;
  final int     requiredSize;
  final String  modelVersion;
  final String? degradedReason;

  // Weather inputs
  final double? prcp;
  final double? tavg;
  final double? humidity;
  final double? pressure;
  final double? wspd;
  final double? cloudCover;

  // SHAP drivers
  final List<DriverModel> drivers;

  const CityRiskModel({
    required this.levelKey,
    required this.level,
    required this.riskBand,
    required this.city,
    required this.citySlug,
    this.inferredAt,
    required this.hriScore,
    required this.uncertainty,
    required this.alertTier,
    required this.alertTierLabel,
    required this.pushNotification,
    required this.isAlert,
    required this.eventProbability,
    required this.stability,
    required this.source,
    required this.isHeuristic,
    required this.inferenceMode,
    required this.mcCompleted,
    required this.mcRequested,
    required this.tcnActive,
    required this.bufferSize,
    required this.requiredSize,
    required this.modelVersion,
    this.degradedReason,
    this.prcp,
    this.tavg,
    this.humidity,
    this.pressure,
    this.wspd,
    this.cloudCover,
    required this.drivers,
  });

  factory CityRiskModel.fromJson(Map<String, dynamic> json) {
    // alert_tier_label is the reliable field — alert_tier may be dict or int
    final tierLabel = json['alert_tier_label'] as String? ?? 'NORMAL';
    final alertTier = tierLabel == 'ALERT' ? 4 : tierLabel == 'ADVISORY' ? 2 : 1;

    final riskBand = json['risk_band'] as String? ?? 'Low';
    final levelKey = _riskBandToScenario[riskBand] ?? 'safe';

    final wi = json['weather_inputs'] as Map<String, dynamic>? ?? {};
    final sc = json['sequence_context'] as Map<String, dynamic>? ?? {};

    return CityRiskModel(
      levelKey:         levelKey,
      level:            _scenarioToLevel[levelKey] ?? 'Safe',
      riskBand:         riskBand,
      city:             json['city'] as String? ?? '',
      citySlug:         json['city_slug'] as String? ?? '',
      inferredAt:       json['inferred_at'] as String?,

      hriScore:         (json['hri_score'] as num?)?.toInt() ?? 0,
      uncertainty:      ((json['uncertainty'] ??
          json['epistemic_uncertainty'] ?? 0.0) as num).toDouble(),
      alertTier:        alertTier,
      alertTierLabel:   tierLabel,
      pushNotification: json['push_notification'] as bool? ?? false,
      isAlert:          json['is_alert'] as bool? ?? false,
      eventProbability: (json['event_probability'] as num?)?.toDouble() ?? 0.0,

      stability:        json['prediction_stability'] as String? ?? 'stable',
      source:           json['source'] as String? ?? 'model',
      isHeuristic:      json['source'] == 'heuristic',
      inferenceMode:    json['inference_mode'] as String? ?? 'mc_dropout',
      mcCompleted:      (json['mc_samples_completed'] as num?)?.toInt() ?? 0,
      mcRequested:      (json['mc_samples_requested'] as num?)?.toInt() ?? 0,
      tcnActive:        sc['tcn_active'] != false,
      bufferSize:       (sc['buffer_size'] as num?)?.toInt() ?? 0,
      requiredSize:     (sc['required_size'] as num?)?.toInt() ?? 30,
      modelVersion:     json['model_version'] as String? ?? '',
      degradedReason:   json['degraded_reason'] as String?,

      prcp:       (wi['prcp'] as num?)?.toDouble(),
      tavg:       (wi['tavg'] as num?)?.toDouble(),
      humidity:   (wi['humidity'] as num?)?.toDouble(),
      pressure:   (wi['pressure'] as num?)?.toDouble(),
      wspd:       (wi['wspd'] as num?)?.toDouble(),
      cloudCover: (wi['cloud_cover'] as num?)?.toDouble(),

      drivers: DriverModel.fromRawList(json['drivers'] as List? ?? []),
    );
  }

  // HRI → lifecycle stage
  String get lifecycleStage {
    if (hriScore <= 5)  return 'monitoring';
    if (hriScore <= 20) return 'formation';
    if (hriScore <= 50) return 'escalation';
    if (hriScore <= 75) return 'active';
    return 'peak';
  }

  // Confidence percentage for the AI card
  int get confidencePct {
    if (inferenceMode == 'mc_dropout' && mcRequested > 0) {
      return ((mcCompleted / mcRequested) * 100).round().clamp(0, 100);
    }
    return ((1.0 - uncertainty) * 100).round().clamp(0, 100);
  }
}
