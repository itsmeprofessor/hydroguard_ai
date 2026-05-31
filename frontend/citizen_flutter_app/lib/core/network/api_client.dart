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
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      // Do NOT set Content-Type globally — GET requests must not send it (CORS)
    ));
    _dio.interceptors.add(_AuthInterceptor(_dio));
    if (kDebugMode) {
      _dio.interceptors.add(LogInterceptor(requestBody: false, responseBody: false));
    }
    _initialized = true;
  }

  Dio get dio => _dio;

  // GET helper — never adds Content-Type
  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? queryParameters}) =>
      _dio.get<T>(path, queryParameters: queryParameters);

  // POST helper — adds Content-Type for POST
  Future<Response<T>> post<T>(String path, {dynamic data}) =>
      _dio.post<T>(path,
        data: data,
        options: Options(headers: {'Content-Type': 'application/json'}),
      );
}

class _AuthInterceptor extends Interceptor {
  _AuthInterceptor(this._dio);
  final Dio _dio;
  bool _refreshing = false;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await SecureStorage.instance.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401 && !_refreshing) {
      _refreshing = true;
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
        // Retry original request
        err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
        final retried = await _dio.fetch(err.requestOptions);
        handler.resolve(retried);
        return;
      } catch (_) {
        await SecureStorage.instance.clearAll();
        // Signal session expired — router redirect handles navigation
      } finally {
        _refreshing = false;
      }
    }
    handler.next(err);
  }
}
