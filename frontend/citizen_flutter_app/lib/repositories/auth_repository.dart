import '../core/network/api_client.dart';
import '../core/network/endpoints.dart';
import '../core/storage/secure_storage.dart';
import '../models/user_model.dart';

class AuthRepository {
  final ApiClient _api = ApiClient.instance;

  Future<Map<String, dynamic>> login(String email, String password) async {
    final res = await _api.post(Endpoints.login,
        data: {'email': email, 'password': password});
    final data = res.data as Map<String, dynamic>;
    await SecureStorage.instance.saveTokens(
      accessToken:  data['access_token']  as String,
      refreshToken: data['refresh_token'] as String,
      role:         data['role']          as String?,
      username:     data['username']      as String?,
    );
    return data;
  }

  Future<Map<String, dynamic>> register(
      String email, String username, String password) async {
    final res = await _api.post(Endpoints.register,
        data: {'email': email, 'username': username, 'password': password});
    final data = res.data as Map<String, dynamic>;
    await SecureStorage.instance.saveTokens(
      accessToken:  data['access_token']  as String,
      refreshToken: data['refresh_token'] as String,
      role:         data['role']          as String?,
      username:     data['username']      as String?,
    );
    return data;
  }

  Future<UserModel> me() async {
    final res = await _api.get(Endpoints.me);
    return UserModel.fromJson(res.data as Map<String, dynamic>);
  }

  Future<void> logout() async {
    try {
      await _api.post(Endpoints.logout);
    } catch (_) {}
    await SecureStorage.instance.clearAll();
  }
}
