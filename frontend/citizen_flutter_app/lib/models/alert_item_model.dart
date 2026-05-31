import 'driver_model.dart';

class AlertItemModel {
  final String id;
  final String kind;     // 'safe' | 'monitor' | 'watch' | 'warning' | 'severe'
  final String title;
  final String relativeTime;
  final String? rawTime;
  final String description;
  final String source;   // "HydroGuard ML" | "Heuristic estimate"
  final String inferMode;
  final List<DriverModel> drivers;
  final int    hriScore;
  final int    alertTier;
  final String tierLabel;
  final String stability;

  const AlertItemModel({
    required this.id,
    required this.kind,
    required this.title,
    required this.relativeTime,
    this.rawTime,
    required this.description,
    required this.source,
    required this.inferMode,
    required this.drivers,
    required this.hriScore,
    required this.alertTier,
    required this.tierLabel,
    required this.stability,
  });

  factory AlertItemModel.fromJson(Map<String, dynamic> json) {
    const bandToKind = {
      'Severe': 'severe', 'High': 'warning', 'Moderate': 'watch', 'Low': 'monitor',
    };
    final riskBand  = json['risk_band'] as String? ?? json['risk_level'] as String? ?? 'Low';
    final kind      = bandToKind[riskBand] ?? 'monitor';
    final hri       = (json['hri_score'] as num?)?.toInt() ?? 0;
    final city      = json['city'] as String? ?? json['city_slug'] as String? ?? '';
    final src       = json['source'] == 'heuristic' ? 'Heuristic estimate' : 'HydroGuard ML';
    final infer     = json['inference_mode'] == 'mc_dropout' ? 'MC Dropout' : 'Deterministic';

    final tierLabel = json['alert_tier_label'] as String? ?? 'NORMAL';
    final tier      = tierLabel == 'ALERT' ? 4 : tierLabel == 'ADVISORY' ? 2 : 1;

    final rawTime   = json['inferred_at'] as String? ?? json['created_at'] as String?;

    final title = switch (riskBand) {
      'Severe'   => 'Cloudburst alert · $city',
      'High'     => 'Flash flood warning · $city',
      'Moderate' => 'Heavy rain advisory · $city',
      _          => 'Monitor · $city',
    };

    final degraded = json['degraded_reason'] as String?;
    final desc = 'HRI $hri/100 · $src · $infer.'
        '${degraded != null ? ' Note: $degraded.' : ''}';

    return AlertItemModel(
      id:           json['inference_id'] as String? ??
          json['id']?.toString() ??
          DateTime.now().millisecondsSinceEpoch.toString(),
      kind:         kind,
      title:        title,
      relativeTime: _relTime(rawTime),
      rawTime:      rawTime,
      description:  desc,
      source:       src,
      inferMode:    infer,
      drivers:      DriverModel.fromRawList(json['drivers'] as List? ?? []),
      hriScore:     hri,
      alertTier:    tier,
      tierLabel:    tierLabel,
      stability:    json['prediction_stability'] as String? ?? 'stable',
    );
  }

  static String _relTime(String? isoStr) {
    if (isoStr == null) return '—';
    try {
      final diff = DateTime.now().difference(DateTime.parse(isoStr));
      if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24)   return '${diff.inHours}h ago';
      return '${diff.inDays}d ago';
    } catch (_) {
      return '—';
    }
  }
}
