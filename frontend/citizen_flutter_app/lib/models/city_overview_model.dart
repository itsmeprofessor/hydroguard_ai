class CityOverviewModel {
  final String slug;
  final String name;
  final String riskBand;
  final String levelKey;
  final int    hriScore;
  final String alertTierLabel;
  final String source;
  final bool   isHeuristic;

  const CityOverviewModel({
    required this.slug,
    required this.name,
    required this.riskBand,
    required this.levelKey,
    required this.hriScore,
    required this.alertTierLabel,
    required this.source,
    required this.isHeuristic,
  });

  factory CityOverviewModel.fromJson(Map<String, dynamic> json) {
    const bandToScenario = {
      'Low': 'safe', 'Moderate': 'watch', 'High': 'warning', 'Severe': 'severe',
    };
    final riskBand = json['risk_band'] as String? ?? 'Low';
    final src      = json['source'] as String? ?? 'model';
    return CityOverviewModel(
      slug:           json['slug'] as String? ?? json['city_slug'] as String? ?? '',
      name:           json['name'] as String? ?? '',
      riskBand:       riskBand,
      levelKey:       bandToScenario[riskBand] ?? 'safe',
      hriScore:       (json['hri_score'] as num?)?.toInt() ?? 0,
      alertTierLabel: json['alert_tier_label'] as String? ?? 'NORMAL',
      source:         src,
      isHeuristic:    src == 'heuristic',
    );
  }
}
