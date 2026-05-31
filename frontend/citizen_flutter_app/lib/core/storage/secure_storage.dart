import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  SecureStorage._();
  static final SecureStorage instance = SecureStorage._();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _keyAccess   = 'hg_access_token';
  static const _keyRefresh  = 'hg_refresh_token';
  static const _keyRole     = 'hg_role';
  static const _keyUsername = 'hg_username';

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
    String? role,
    String? username,
  }) async {
    await Future.wait([
      _storage.write(key: _keyAccess,  value: accessToken),
      _storage.write(key: _keyRefresh, value: refreshToken),
      if (role != null)     _storage.write(key: _keyRole,     value: role),
      if (username != null) _storage.write(key: _keyUsername, value: username),
    ]);
  }

  Future<String?> getAccessToken()  => _storage.read(key: _keyAccess);
  Future<String?> getRefreshToken() => _storage.read(key: _keyRefresh);
  Future<String?> getRole()         => _storage.read(key: _keyRole);
  Future<String?> getUsername()     => _storage.read(key: _keyUsername);

  Future<void> clearAll() => _storage.deleteAll();

  Future<bool> hasTokens() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }
}
