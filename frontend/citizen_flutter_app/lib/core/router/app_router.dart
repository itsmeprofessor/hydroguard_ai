import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../shared/providers/auth_provider.dart';
import '../../features/auth/login_screen.dart';
import '../../features/auth/signup_screen.dart';
import '../../features/auth/forgot_password_screen.dart';
import '../../features/citizen/shell/citizen_shell.dart';
import '../../features/citizen/home/home_screen.dart';
import '../../features/citizen/forecast/forecast_screen.dart';
import '../../features/citizen/map/map_screen.dart';
import '../../features/citizen/learn/learn_screen.dart';
import '../../features/citizen/settings/settings_screen.dart';
import '../../features/citizen/profile/profile_screen.dart';
import '../../features/citizen/alerts/alerts_screen.dart';
import '../../features/admin/shell/admin_shell.dart';
import '../../features/admin/dashboard/dashboard_screen.dart';
import '../../features/admin/city_hri/city_hri_screen.dart';
import '../../features/admin/alerts/admin_alerts_screen.dart';
import '../../features/admin/map/admin_map_screen.dart';
import '../../features/admin/more/admin_more_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/splash',
    redirect: (context, state) {
      final loading  = authState.isLoading;
      final authed   = authState.isAuthenticated;
      final isAdmin  = authState.isAdmin;
      final location = state.matchedLocation;

      // While loading, stay on splash; redirect everything else to splash
      if (loading) return location == '/splash' ? null : '/splash';

      // Done loading — always leave splash
      if (location == '/splash') {
        return authed
            ? (isAdmin ? '/admin/dashboard' : '/citizen/home')
            : '/login';
      }

      if (!authed) {
        const publicRoutes = ['/login', '/signup', '/forgot-password'];
        if (!publicRoutes.contains(location)) return '/login';
        return null;
      }

      // Authenticated — leave auth screens
      if (location == '/login' || location == '/signup') {
        return isAdmin ? '/admin/dashboard' : '/citizen/home';
      }

      // Block non-admin from admin routes
      if (location.startsWith('/admin') && !isAdmin) return '/citizen/home';

      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const _SplashScreen()),
      GoRoute(path: '/login',  builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/signup', builder: (_, __) => const SignupScreen()),
      GoRoute(
          path: '/forgot-password',
          builder: (_, __) => const ForgotPasswordScreen()),

      // Citizen shell
      ShellRoute(
        builder: (_, __, child) => CitizenShell(child: child),
        routes: [
          GoRoute(
              path: '/citizen/home',
              builder: (_, __) => const HomeScreen()),
          GoRoute(
              path: '/citizen/forecast',
              builder: (_, __) => const ForecastScreen()),
          GoRoute(
              path: '/citizen/map',
              builder: (_, __) => const CitizenMapScreen()),
          GoRoute(
              path: '/citizen/learn',
              builder: (_, __) => const LearnScreen()),
          GoRoute(
              path: '/citizen/settings',
              builder: (_, __) => const SettingsScreen()),
          GoRoute(
              path: '/citizen/alerts',
              builder: (_, __) => const AlertsScreen()),
          GoRoute(
              path: '/citizen/profile',
              builder: (_, __) => const ProfileScreen()),
        ],
      ),

      // Admin shell
      ShellRoute(
        builder: (_, __, child) => AdminShell(child: child),
        routes: [
          GoRoute(
              path: '/admin/dashboard',
              builder: (_, __) => const AdminDashboardScreen()),
          GoRoute(
              path: '/admin/hri',
              builder: (_, __) => const CityHriScreen()),
          GoRoute(
              path: '/admin/alerts',
              builder: (_, __) => const AdminAlertsScreen()),
          GoRoute(
              path: '/admin/map',
              builder: (_, __) => const AdminMapScreen()),
          GoRoute(
              path: '/admin/more',
              builder: (_, __) => const AdminMoreScreen()),
        ],
      ),
    ],
  );
});

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();
  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
}
