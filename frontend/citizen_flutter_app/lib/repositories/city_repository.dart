import '../core/network/api_client.dart';
import '../core/network/endpoints.dart';
import '../models/city_risk_model.dart';
import '../models/forecast_day_model.dart';
import '../models/alert_item_model.dart';
import '../models/city_overview_model.dart';

class CityRepository {
  final ApiClient _api = ApiClient.instance;

  Future<List<Map<String, dynamic>>> getCities() async {
    final res  = await _api.get(Endpoints.cities);
    final data = res.data as Map<String, dynamic>;
    return (data['cities'] as List).cast<Map<String, dynamic>>();
  }

  Future<List<CityOverviewModel>> getOverview() async {
    final res  = await _api.get(Endpoints.citiesOverview);
    final data = res.data as Map<String, dynamic>;
    final list = data['cities'] as List? ?? data['overview'] as List? ?? [];
    return list.cast<Map<String, dynamic>>().map(CityOverviewModel.fromJson).toList();
  }

  Future<CityRiskModel> getCityRisk(String slug) async {
    final res = await _api.get(Endpoints.cityRisk(slug));
    return CityRiskModel.fromJson(res.data as Map<String, dynamic>);
  }

  Future<List<ForecastDayModel>> getForecast(String slug) async {
    final res  = await _api.get(Endpoints.cityForecast(slug));
    final data = res.data as Map<String, dynamic>;
    final list = data['forecast'] as List? ?? [];
    return list.cast<Map<String, dynamic>>().map(ForecastDayModel.fromJson).toList();
  }

  Future<List<AlertItemModel>> getAlerts(String slug, {int n = 20}) async {
    final res  = await _api.get(Endpoints.cityAlerts(slug), queryParameters: {'n': n});
    final data = res.data as Map<String, dynamic>;
    final list = data['alerts'] as List? ?? [];
    return list.cast<Map<String, dynamic>>().map(AlertItemModel.fromJson).toList();
  }
}
