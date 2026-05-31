import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../models/health_model.dart';
import '../../models/city_overview_model.dart';
import '../../repositories/admin_repository.dart';
import '../../repositories/city_repository.dart';

final _adminRepo = AdminRepository();
final _cityRepo  = CityRepository();

final healthProvider = FutureProvider.autoDispose<HealthModel>((ref) async {
  return _adminRepo.getHealth();
});

final anomalyCountProvider = FutureProvider.autoDispose<int>((ref) async {
  return _adminRepo.getAnomalyCount();
});

final adminOverviewProvider =
    FutureProvider.autoDispose<List<CityOverviewModel>>((ref) async {
  return _cityRepo.getOverview();
});
