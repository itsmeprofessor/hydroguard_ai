import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';

class AdminShell extends StatelessWidget {
  final Widget child;
  const AdminShell({super.key, required this.child});

  static const _tabs = [
    _TabItem(
        label: 'Dashboard',
        icon: Icons.dashboard_outlined,
        active: Icons.dashboard_rounded,
        path: '/admin/dashboard'),
    _TabItem(
        label: 'HRI',
        icon: Icons.analytics_outlined,
        active: Icons.analytics_rounded,
        path: '/admin/hri'),
    _TabItem(
        label: 'Alerts',
        icon: Icons.notifications_outlined,
        active: Icons.notifications_rounded,
        path: '/admin/alerts'),
    _TabItem(
        label: 'Map',
        icon: Icons.map_outlined,
        active: Icons.map_rounded,
        path: '/admin/map'),
    _TabItem(
        label: 'More',
        icon: Icons.more_horiz_outlined,
        active: Icons.more_horiz_rounded,
        path: '/admin/more'),
  ];

  @override
  Widget build(BuildContext context) {
    final location   = GoRouterState.of(context).matchedLocation;
    final idx        = _tabs.indexWhere((t) => location.startsWith(t.path));
    final currentIdx = idx < 0 ? 0 : idx;
    final isDark     = Theme.of(context).brightness == Brightness.dark;

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
                              ? HGColors.violet
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
                                ? HGColors.violet
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
