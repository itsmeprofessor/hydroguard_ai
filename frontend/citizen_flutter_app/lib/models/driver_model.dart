class DriverModel {
  final String plain;     // humanised feature name
  final String tech;      // "feature = value" label
  final String direction; // 'up' | 'down'
  final double weight;    // abs(shap)

  const DriverModel({
    required this.plain,
    required this.tech,
    required this.direction,
    required this.weight,
  });

  // Handles v3.3 shape { feature, shap, value } AND legacy { display_name, direction, weight }
  factory DriverModel.fromRaw(Map<String, dynamic> d) {
    if (d['shap'] != null) {
      final shap  = (d['shap'] as num).toDouble();
      final raw   = d['display_name'] as String? ?? d['feature'] as String? ?? 'Unknown factor';
      final plain = raw.replaceAll('_', ' ').split(' ')
          .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
          .join(' ');
      final value = d['value'];
      final tech  = value != null
          ? '${d['feature']} = ${(value as num).toStringAsFixed(2)}'
          : (d['feature'] as String? ?? '');
      return DriverModel(
          plain: plain, tech: tech, direction: shap >= 0 ? 'up' : 'down', weight: shap.abs());
    }
    // Legacy shape
    final w   = ((d['weight'] ?? d['importance'] ?? 0.0) as num).toDouble().abs();
    final dir = d['direction'] as String? ?? (w > 0 ? 'up' : 'down');
    final raw = d['display_name'] as String? ??
        d['plain'] as String? ??
        d['feature_label'] as String? ??
        (d['feature'] as String? ?? '').replaceAll('_', ' ');
    final plain = raw.split(' ')
        .map((w2) => w2.isEmpty ? w2 : '${w2[0].toUpperCase()}${w2.substring(1)}')
        .join(' ');
    final tech = d['tech'] as String? ?? '';
    return DriverModel(plain: plain, tech: tech, direction: dir, weight: w);
  }

  static List<DriverModel> fromRawList(List<dynamic> raw) {
    final list = raw
        .whereType<Map<String, dynamic>>()
        .map(DriverModel.fromRaw)
        .toList()
      ..sort((a, b) => b.weight.compareTo(a.weight));
    return list.take(4).toList();
  }
}
