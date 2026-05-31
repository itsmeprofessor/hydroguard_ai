import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';

class CitizenShell extends StatelessWidget {
  final Widget child;
  const CitizenShell({super.key, required this.child});

  static const _tabs = [
    _TabItem(
        label: 'Home',
        icon: Icons.home_outlined,
        active: Icons.home_rounded,
        path: '/citizen/home'),
    _TabItem(
        label: 'Forecast',
        icon: Icons.wb_sunny_outlined,
        active: Icons.wb_sunny_rounded,
        path: '/citizen/forecast'),
    _TabItem(
        label: 'Map',
        icon: Icons.map_outlined,
        active: Icons.map_rounded,
        path: '/citizen/map'),
    _TabItem(
        label: 'Learn',
        icon: Icons.school_outlined,
        active: Icons.school_rounded,
        path: '/citizen/learn'),
    _TabItem(
        label: 'Settings',
        icon: Icons.settings_outlined,
        active: Icons.settings_rounded,
        path: '/citizen/settings'),
  ];

  @override
  Widget build(BuildContext context) {
    final location  = GoRouterState.of(context).matchedLocation;
    final idx       = _tabs.indexWhere((t) => location.startsWith(t.path));
    final currentIdx = idx < 0 ? 0 : idx;
    final isDark    = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: child,
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: isDark ? HGColors.cardDark : HGColors.cardLight,
          border: Border(
            top: BorderSide(
                color: isDark ? HGColors.lineDark : HGColors.lineLight),
          ),
        ),
        child: SafeArea(
          child: SizedBox(
            height: 64,
            child: Row(
              children: List.generate(_tabs.length, (i) {
                final t      = _tabs[i];
                final active = i == currentIdx;
                return Expanded(
                  child: InkWell(
                    onTap: () => context.go(t.path),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          active ? t.active : t.icon,
                          size: 24,
                          color: active
                              ? HGColors.blue
                              : (isDark
                                  ? HGColors.mutedDark
                                  : HGColors.mutedLight),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          t.label,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: active
                                ? FontWeight.w600
                                : FontWeight.w400,
                            color: active
                                ? HGColors.blue
                                : (isDark
                                    ? HGColors.mutedDark
                                    : HGColors.mutedLight),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

class _TabItem {
  final String label, path;
  final IconData icon, active;
  const _TabItem({
    required this.label,
    required this.icon,
    required this.active,
    required this.path,
  });
}
