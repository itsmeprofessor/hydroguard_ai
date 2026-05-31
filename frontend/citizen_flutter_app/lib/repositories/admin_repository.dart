import '../core/network/api_client.dart';
import '../core/network/endpoints.dart';
import '../models/health_model.dart';

class AdminRepository {
  final ApiClient _api = ApiClient.instance;

  Future<HealthModel> getHealth() async {
    final res = await _api.get(Endpoints.health);
    return HealthModel.fromJson(res.data as Map<String, dynamic>);
  }

  Future<int> getAnomalyCount() async {
    final res  = await _api.get(Endpoints.anomalies,
        queryParameters: {'anomalies_only': 'true', 'limit': 1});
    final data = res.data as Map<String, dynamic>;
    return (data['total'] as num?)?.toInt() ?? 0;
  }

  Future<void> refreshCityRegistry() async {
    await _api.post(Endpoints.citiesRefresh);
  }

  Future<void> trainCity(String slug) async {
    await _api.post(Endpoints.cityTrain(slug));
  }
}
