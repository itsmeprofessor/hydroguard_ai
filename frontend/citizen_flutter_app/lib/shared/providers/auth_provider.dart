import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/storage/secure_storage.dart';
import '../../models/user_model.dart';
import '../../repositories/auth_repository.dart';

class AuthState {
  final UserModel? user;
  final bool isLoading;
  final String? error;

  const AuthState({this.user, this.isLoading = false, this.error});

  bool get isAuthenticated => user != null;
  bool get isAdmin => user?.isAdmin ?? false;

  AuthState copyWith({UserModel? user, bool? isLoading, String? error}) => AuthState(
    user:      user      ?? this.user,
    isLoading: isLoading ?? this.isLoading,
    error:     error,
  );
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier() : super(const AuthState(isLoading: true)) {
    _init();
  }

  final _repo = AuthRepository();

  Future<void> _init() async {
    final hasTokens = await SecureStorage.instance.hasTokens();
    if (!hasTokens) {
      state = const AuthState();
      return;
    }
    try {
      final user = await _repo.me();
      state = AuthState(user: user);
    } catch (_) {
      await SecureStorage.instance.clearAll();
      state = const AuthState();
    }
  }

  Future<void> login(String email, String password) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      await _repo.login(email, password);
      final user = await _repo.me();
      state = AuthState(user: user);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _extractError(e));
      rethrow;
    }
  }

  Future<void> register(String email, String username, String password) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      await _repo.register(email, username, password);
      final user = await _repo.me();
      state = AuthState(user: user);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: _extractError(e));
      rethrow;
    }
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AuthState();
  }

  String _extractError(Object e) {
    final msg = e.toString();
    if (msg.contains('401')) return 'Invalid email or password.';
    if (msg.contains('409') || msg.contains('already')) return 'Email or username already taken.';
    if (msg.contains('SocketException') || msg.contains('Connection')) return 'Cannot reach server.';
    return 'An error occurred. Please try again.';
  }
}

final authProvider =
    StateNotifierProvider<AuthNotifier, AuthState>((_) => AuthNotifier());
