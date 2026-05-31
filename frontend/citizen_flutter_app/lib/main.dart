import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/network/api_client.dart';
import 'core/storage/local_storage.dart';
import 'core/theme/app_theme.dart';
import 'core/router/app_router.dart';
import 'shared/providers/theme_provider.dart';

// API base URL — set via --dart-define=API_BASE=http://localhost:8000
// Empty string for same-origin web build served by nginx
const String _apiBase =
    String.fromEnvironment('API_BASE', defaultValue: 'http://localhost:8000');

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await LocalStorage.instance.init();
  ApiClient.instance.init(_apiBase);
  runApp(const ProviderScope(child: HydroGuardApp()));
}

class HydroGuardApp extends ConsumerWidget {
  const HydroGuardApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router    = ref.watch(routerProvider);
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'HydroGuard',
      debugShowCheckedModeBanner: false,
      theme:      AppTheme.light(),
      darkTheme:  AppTheme.dark(),
      themeMode:  themeMode,
      routerConfig: router,
    );
  }
}
