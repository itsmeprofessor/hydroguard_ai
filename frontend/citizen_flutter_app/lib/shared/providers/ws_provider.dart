import 'dart:async';
import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../core/network/endpoints.dart';
import '../../core/storage/secure_storage.dart';

class WsService {
  WsService._();
  static final WsService instance = WsService._();

  WebSocketChannel? _anomaliesChannel;
  WebSocketChannel? _healthChannel;

  // Track subscriptions so we can cancel before reconnecting
  StreamSubscription<dynamic>? _anomaliesSub;
  StreamSubscription<dynamic>? _healthSub;

  final _anomaliesController = StreamController<Map<String, dynamic>>.broadcast();
  final _healthController    = StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get anomaliesStream => _anomaliesController.stream;
  Stream<Map<String, dynamic>> get healthStream    => _healthController.stream;

  String _wsBase(String apiBase) {
    if (apiBase.isEmpty) return '';
    return apiBase.replaceFirst(RegExp(r'^http'), 'ws');
  }

  Future<void> startAll(String apiBase) async {
    final token = await SecureStorage.instance.getAccessToken();
    final base  = _wsBase(apiBase);
    _connectAnomalies(base, token);
    _connectHealth(base);
  }

  void _connectAnomalies(String base, String? token) {
    // Cancel old subscription before creating a new channel
    _anomaliesSub?.cancel();
    _anomaliesChannel?.sink.close();

    try {
      final uri = base.isEmpty
          ? Uri(scheme: 'ws', host: '', path: Endpoints.wsAnomalies,
                query: token != null ? 'token=$token' : null)
          : Uri.parse('$base${Endpoints.wsAnomalies}${token != null ? '?token=$token' : ''}');

      _anomaliesChannel = WebSocketChannel.connect(uri);
      _anomaliesSub = _anomaliesChannel!.stream.listen(
        (msg) {
          try {
            final data = jsonDecode(msg as String) as Map<String, dynamic>;
            _anomaliesController.add(data['data'] as Map<String, dynamic>? ?? data);
          } catch (_) {}
        },
        onDone: () => Future.delayed(const Duration(seconds: 3),
            () => _connectAnomalies(base, token)),
        onError: (_) => Future.delayed(const Duration(seconds: 3),
            () => _connectAnomalies(base, token)),
        cancelOnError: false,
      );
    } catch (_) {}
  }

  void _connectHealth(String base) {
    // Cancel old subscription before creating a new channel
    _healthSub?.cancel();
    _healthChannel?.sink.close();

    try {
      final uri = base.isEmpty
          ? Uri(scheme: 'ws', host: '', path: Endpoints.wsHealth)
          : Uri.parse('$base${Endpoints.wsHealth}');

      _healthChannel = WebSocketChannel.connect(uri);
      _healthSub = _healthChannel!.stream.listen(
        (msg) {
          try {
            final data = jsonDecode(msg as String) as Map<String, dynamic>;
            _healthController.add(data['data'] as Map<String, dynamic>? ?? data);
          } catch (_) {}
        },
        onDone: () => Future.delayed(const Duration(seconds: 5),
            () => _connectHealth(base)),
        onError: (_) => Future.delayed(const Duration(seconds: 5),
            () => _connectHealth(base)),
        cancelOnError: false,
      );
    } catch (_) {}
  }

  void stopAll() {
    _anomaliesSub?.cancel();
    _healthSub?.cancel();
    _anomaliesChannel?.sink.close();
    _healthChannel?.sink.close();
    _anomaliesSub = null;
    _healthSub    = null;
    _anomaliesChannel = null;
    _healthChannel    = null;
  }
}

final wsServiceProvider = Provider<WsService>((_) => WsService.instance);
