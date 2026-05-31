import 'package:intl/intl.dart';

class ForecastDayModel {
  final String dateStr;
  final String dayName;
  final String levelKey;
  final String riskBand;
  final int    hriScore;
  final double? prcp;
  final double? maxTemp;
  final double? minTemp;
  final int?   chanceRain;
  final int?   eventProb;  // percentage
  final bool   isAlert;

  const ForecastDayModel({
    required this.dateStr,
    required this.dayName,
    required this.levelKey,
    required this.riskBand,
    required this.hriScore,
    this.prcp,
    this.maxTemp,
    this.minTemp,
    this.chanceRain,
    this.eventProb,
    required this.isAlert,
  });

  factory ForecastDayModel.fromJson(Map<String, dynamic> json) {
    const bandToScenario = {
      'Low': 'safe', 'Moderate': 'watch', 'High': 'warning', 'Severe': 'severe',
    };
    final riskBand = json['risk_band'] as String? ?? 'Low';
    final levelKey = bandToScenario[riskBand] ?? 'safe';
    final dateStr  = json['date'] as String? ?? '';
    String dayName = json['day_name'] as String? ?? '';
    if (dayName.isEmpty && dateStr.isNotEmpty) {
      try {
        dayName = DateFormat('EEE').format(DateTime.parse('${dateStr}T00:00:00'));
      } catch (_) {
        dayName = dateStr;
      }
    }

    double? ep;
    final raw = json['event_probability'];
    if (raw != null) ep = ((raw as num).toDouble() * 100).roundToDouble();

    return ForecastDayModel(
      dateStr:    dateStr,
      dayName:    dayName,
      levelKey:   levelKey,
      riskBand:   riskBand,
      hriScore:   (json['hri_score'] as num?)?.toInt() ?? 0,
      prcp:       (json['daily_precip_mm'] as num?)?.toDouble(),
      maxTemp:    (json['max_temp_c'] as num?)?.toDouble(),
      minTemp:    (json['min_temp_c'] as num?)?.toDouble(),
      chanceRain: (json['daily_chance_rain'] as num?)?.toInt(),
      eventProb:  ep?.toInt(),
      isAlert:    json['is_alert'] as bool? ?? false,
    );
  }
}
