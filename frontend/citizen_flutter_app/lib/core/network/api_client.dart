import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../storage/secure_storage.dart';
import 'endpoints.dart';

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  late final Dio _dio;
  bool _initialized = false;

  void init(String baseUrl) {
    if (_initialized) return;
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      // Flutter web uses XHR where connectTimeout = total request timeout.
      // Forecast endpoint calls WeatherAPI which can take 8-10s.
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 60),
    ));
    _dio.interceptors.add(_AuthInterceptor(_dio));
    if (kDebugMode) {
      _dio.interceptors.add(LogInterceptor(requestBody: false, responseBody: false));
    }
    _initialized = true;
  }

  Dio get dio => _dio;

  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? queryParameters}) =>
      _dio.get<T>(path, queryParameters: queryParameters);

  Future<Response<T>> post<T>(String path, {dynamic data}) =>
      _dio.post<T>(path,
        data: data,
        options: Options(headers: {'Content-Type': 'application/json'}),
      );
}

class _AuthInterceptor extends Interceptor {
  _AuthInterceptor(this._dio);
  final Dio _dio;

  // Serialises concurrent refresh attempts: null = no refresh in flight.
  // Any subsequent 401 awaits this completer instead of launching a second refresh.
  Completer<void>? _refreshCompleter;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    // skipAuth: skip token injection for the refresh call itself
    if (options.extra['skipAuth'] == true) {
      handler.next(options);
      return;
    }
    final token = await SecureStorage.instance.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401) {
      handler.next(err);
      return;
    }

    // Another refresh is already in flight — await it, then retry.
    if (_refreshCompleter != null) {
      try {
        await _refreshCompleter!.future;
        final token = await SecureStorage.instance.getAccessToken();
        err.requestOptions.headers['Authorization'] = 'Bearer $token';
        final retried = await _dio.fetch(err.requestOptions);
        handler.resolve(retried);
      } catch (_) {
        handler.next(err);
      }
      return;
    }

    // Start a new refresh.
    _refreshCompleter = Completer<void>();
    try {
      final refreshToken = await SecureStorage.instance.getRefreshToken();
      if (refreshToken == null) throw Exception('No refresh token');

      final response = await _dio.post(
        Endpoints.refresh,
        data: {'refresh_token': refreshToken},
        options: Options(
          headers: {'Content-Type': 'application/json'},
          extra: {'skipAuth': true},
        ),
      );
      final newAccess  = response.data['access_token']  as String;
      final newRefresh = response.data['refresh_token'] as String;
      await SecureStorage.instance.saveTokens(
        accessToken: newAccess,
        refreshToken: newRefresh,
      );
      _refreshCompleter!.complete();

      // Retry original request with new token.
      err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
      final retried = await _dio.fetch(err.requestOptions);
      handler.resolve(retried);
    } catch (_) {
      _refreshCompleter!.completeError('refresh_failed');
      await SecureStorage.instance.clearAll();
      handler.next(err); // propagate; router redirect reacts to authProvider state
    } finally {
      _refreshCompleter = null;
    }
  }
}
