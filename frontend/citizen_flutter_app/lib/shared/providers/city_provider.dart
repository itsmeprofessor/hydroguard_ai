import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../models/city_risk_model.dart';
import '../../models/forecast_day_model.dart';
import '../../models/alert_item_model.dart';
import '../../models/city_overview_model.dart';
import '../../repositories/city_repository.dart';
import 'prefs_provider.dart';

final _cityRepo = CityRepository();

/// Current city slug derived from prefs
final currentCitySlugProvider = Provider<String>((ref) {
  final city = ref.watch(prefsProvider).city;
  return city
      .toLowerCase()
      .replaceAll(RegExp(r'\s+'), '_')
      .replaceAll(RegExp(r'[^a-z0-9_]'), '');
});

/// City risk — refreshable, per-slug family
final cityRiskProvider =
    FutureProvider.autoDispose.family<CityRiskModel, String>((ref, slug) async {
  return _cityRepo.getCityRisk(slug);
});

/// Forecast — per-slug family
final forecastProvider = FutureProvider.autoDispose
    .family<List<ForecastDayModel>, String>((ref, slug) async {
  return _cityRepo.getForecast(slug);
});

/// Alerts — StateNotifier supporting WS prepend
class AlertsNotifier extends StateNotifier<List<AlertItemModel>> {
  AlertsNotifier(String slug) : super([]) {
    _load(slug);
  }

  Future<void> _load(String slug) async {
    try {
      final list = await _cityRepo.getAlerts(slug);
      if (mounted) state = list;
    } catch (_) {}
  }

  void prepend(AlertItemModel item) {
    state = [item, ...state].take(20).toList();
  }
}

final alertsProvider = StateNotifierProvider.autoDispose
    .family<AlertsNotifier, List<AlertItemModel>, String>(
  (ref, slug) => AlertsNotifier(slug),
);

/// Cities list (raw maps from /cities)
final citiesListProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return _cityRepo.getCities();
});

/// Cities overview
final overviewProvider =
    FutureProvider<List<CityOverviewModel>>((ref) async {
  return _cityRepo.getOverview();
});
