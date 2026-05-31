import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

// On web, flutter_secure_storage v9 initializes IndexedDB crypto keys
// asynchronously on first read. This blocks every Dio request (interceptor
// calls getAccessToken() before each request) and causes an infinite spinner.
// Fix: use SharedPreferences (localStorage, no crypto overhead) on web.
// Native mobile/desktop keeps flutter_secure_storage with proper encryption.
class SecureStorage {
  SecureStorage._();
  static final SecureStorage instance = SecureStorage._();

  static const _native = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _kAccess   = 'hg_access_token';
  static const _kRefresh  = 'hg_refresh_token';
  static const _kRole     = 'hg_role';
  static const _kUsername = 'hg_username';

  SharedPreferences? _webPrefs;
  Future<SharedPreferences> _prefs() async =>
      _webPrefs ??= await SharedPreferences.getInstance();

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
    String? role,
    String? username,
  }) async {
    if (kIsWeb) {
      final p = await _prefs();
      await Future.wait([
        p.setString(_kAccess, accessToken),
        p.setString(_kRefresh, refreshToken),
        if (role != null)     p.setString(_kRole,     role),
        if (username != null) p.setString(_kUsername, username),
      ]);
    } else {
      await Future.wait([
        _native.write(key: _kAccess,   value: accessToken),
        _native.write(key: _kRefresh,  value: refreshToken),
        if (role != null)     _native.write(key: _kRole,     value: role),
        if (username != null) _native.write(key: _kUsername, value: username),
      ]);
    }
  }

  Future<String?> getAccessToken() async {
    if (kIsWeb) return (await _prefs()).getString(_kAccess);
    return _native.read(key: _kAccess);
  }

  Future<String?> getRefreshToken() async {
    if (kIsWeb) return (await _prefs()).getString(_kRefresh);
    return _native.read(key: _kRefresh);
  }

  Future<String?> getRole() async {
    if (kIsWeb) return (await _prefs()).getString(_kRole);
    return _native.read(key: _kRole);
  }

  Future<String?> getUsername() async {
    if (kIsWeb) return (await _prefs()).getString(_kUsername);
    return _native.read(key: _kUsername);
  }

  Future<void> clearAll() async {
    if (kIsWeb) {
      final p = await _prefs();
      await Future.wait([
        p.remove(_kAccess), p.remove(_kRefresh),
        p.remove(_kRole),   p.remove(_kUsername),
      ]);
    } else {
      await _native.deleteAll();
    }
  }

  Future<bool> hasTokens() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }
}
