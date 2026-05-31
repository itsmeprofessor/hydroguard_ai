import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../repositories/admin_repository.dart';
import '../../../shared/providers/admin_provider.dart';
import '../../../shared/providers/auth_provider.dart';
import '../../../shared/providers/ws_provider.dart';

class AdminMoreScreen extends ConsumerStatefulWidget {
  const AdminMoreScreen({super.key});

  @override
  ConsumerState<AdminMoreScreen> createState() => _AdminMoreScreenState();
}

class _AdminMoreScreenState extends ConsumerState<AdminMoreScreen> {
  bool _refreshing    = false;
  bool _wsLive        = false;

  @override
  void initState() {
    super.initState();
    WsService.instance.healthStream.listen((data) {
      if (!mounted) return;
      setState(() => _wsLive = true);
      Future.delayed(const Duration(seconds: 5),
          () { if (mounted) setState(() => _wsLive = false); });
    });
  }

  Future<void> _doRefresh() async {
    setState(() => _refreshing = true);
    try {
      await AdminRepository().refreshCityRegistry();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('City registry refreshed')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  Future<void> _confirmSignOut() async {
    // Use dialogCtx (not outer context) so Navigator.pop closes the dialog,
    // not the GoRouter shell behind it.
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You will be returned to the login screen.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(true),
            style: TextButton.styleFrom(foregroundColor: HGColors.severe),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await ref.read(authProvider.notifier).logout();
    }
  }

  static String _initials(String username) {
    final parts = username.trim().split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    }
    return username
        .substring(0, username.length.clamp(0, 2))
        .toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final isDark     = Theme.of(context).brightness == Brightness.dark;
    final authState  = ref.watch(authProvider);
    final healthAsync = ref.watch(healthProvider);

    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final bg         = isDark ? HGColors.bgDark : HGColors.bgLight;

    final username = authState.user?.username ?? 'Admin';
    final email    = authState.user?.email ?? '';
    final initials = _initials(username);

    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        child: Column(
          children: [
            // App bar
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 14),
              color: cardColor,
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('More',
                            style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w800,
                                color: textColor)),
                        Text('Admin settings',
                            style: TextStyle(
                                fontSize: 12, color: mutedColor)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding:
                    const EdgeInsets.fromLTRB(16, 16, 16, 32),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 1. User profile card
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: cardColor,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                            color: isDark
                                ? HGColors.lineDark
                                : HGColors.lineLight),
                      ),
                      child: Row(
                        children: [
                          // Avatar
                          Container(
                            width: 52,
                            height: 52,
                            decoration: const BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: LinearGradient(
                                colors: [
                                  HGColors.violet,
                                  HGColors.blue
                                ],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                            ),
                            child: Center(
                              child: Text(initials,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w800,
                                      fontSize: 18)),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment:
                                  CrossAxisAlignment.start,
                              children: [
                                Text(username,
                                    style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.w700,
                                        color: textColor)),
                                if (email.isNotEmpty)
                                  Text(email,
                                      style: TextStyle(
                                          fontSize: 12,
                                          color: mutedColor)),
                              ],
                            ),
                          ),
                          // ADMIN badge
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [
                                  HGColors.violet,
                                  HGColors.blue
                                ],
                              ),
                              borderRadius:
                                  BorderRadius.circular(999),
                            ),
                            child: const Text('ADMIN',
                                style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 1.0)),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),

                    // 2. System status
                    _SectionLabel(label: 'System status',
                        isDark: isDark),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: cardColor,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: isDark
                                ? HGColors.lineDark
                                : HGColors.lineLight),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Health status pill
                          healthAsync.when(
                            data: (h) {
                              final isOk = h.status == 'ok' || h.status == 'healthy';
                              final col  = isOk
                                  ? HGColors.safe
                                  : HGColors.watch;
                              final lbl  = isOk
                                  ? 'All systems operational'
                                  : 'Degraded — check logs';
                              return Container(
                                padding:
                                    const EdgeInsets.symmetric(
                                        horizontal: 10,
                                        vertical: 5),
                                decoration: BoxDecoration(
                                  color: col
                                      .withValues(alpha: 0.15),
                                  borderRadius:
                                      BorderRadius.circular(999),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Container(
                                      width: 7,
                                      height: 7,
                                      decoration: BoxDecoration(
                                          shape:
                                              BoxShape.circle,
                                          color: col),
                                    ),
                                    const SizedBox(width: 6),
                                    Text(lbl,
                                        style: TextStyle(
                                            fontSize: 12,
                                            fontWeight:
                                                FontWeight.w600,
                                            color: col)),
                                  ],
                                ),
                              );
                            },
                            loading: () => Container(
                              padding:
                                  const EdgeInsets.symmetric(
                                      horizontal: 10,
                                      vertical: 5),
                              decoration: BoxDecoration(
                                color: const Color(0x20888888),
                                borderRadius:
                                    BorderRadius.circular(999),
                              ),
                              child: Text('Checking…',
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: mutedColor)),
                            ),
                            error: (_, __) => Text(
                                'Status unavailable',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: mutedColor)),
                          ),
                          const SizedBox(height: 12),
                          // WS stream
                          Row(
                            children: [
                              Icon(Icons.wifi_rounded,
                                  size: 16,
                                  color: _wsLive
                                      ? HGColors.safe
                                      : mutedColor),
                              const SizedBox(width: 6),
                              Text(
                                  _wsLive
                                      ? 'WebSocket · Live'
                                      : 'WebSocket · Waiting…',
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: _wsLive
                                          ? HGColors.safe
                                          : mutedColor)),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),

                    // 3. Operations
                    _SectionLabel(
                        label: 'Operations', isDark: isDark),
                    const SizedBox(height: 8),
                    Container(
                      decoration: BoxDecoration(
                        color: cardColor,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: isDark
                                ? HGColors.lineDark
                                : HGColors.lineLight),
                      ),
                      child: ListTile(
                        leading: Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.orange
                                .withValues(alpha: 0.15),
                            borderRadius:
                                BorderRadius.circular(10),
                          ),
                          child: const Icon(
                              Icons.location_city_rounded,
                              size: 18,
                              color: Colors.orange),
                        ),
                        title: Text('Refresh city registry',
                            style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                                color: textColor)),
                        subtitle: Text(
                            'POST /api/v2/cities/refresh',
                            style: TextStyle(
                                fontSize: 11,
                                color: mutedColor)),
                        trailing: _refreshing
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2),
                              )
                            : Icon(
                                Icons.chevron_right_rounded,
                                color: mutedColor),
                        onTap:
                            _refreshing ? null : _doRefresh,
                      ),
                    ),
                    const SizedBox(height: 20),

                    // 4. About
                    _SectionLabel(
                        label: 'About', isDark: isDark),
                    const SizedBox(height: 8),
                    Container(
                      decoration: BoxDecoration(
                        color: cardColor,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: isDark
                                ? HGColors.lineDark
                                : HGColors.lineLight),
                      ),
                      child: Column(
                        children: [
                          _AboutRow(
                            isDark: isDark,
                            textColor: textColor,
                            mutedColor: mutedColor,
                            label: 'App version',
                            value: 'v3.3.0',
                          ),
                          Divider(
                              height: 1,
                              color: isDark
                                  ? HGColors.lineDark
                                  : HGColors.lineLight),
                          _AboutRow(
                            isDark: isDark,
                            textColor: textColor,
                            mutedColor: mutedColor,
                            label: 'Backend',
                            value: healthAsync.whenOrNull(
                                    data: (h) =>
                                        (h.status == 'ok' || h.status == 'healthy')
                                            ? 'healthy'
                                            : h.status) ??
                                '—',
                          ),
                          Divider(
                              height: 1,
                              color: isDark
                                  ? HGColors.lineDark
                                  : HGColors.lineLight),
                          ListTile(
                            dense: true,
                            leading: const Icon(
                                Icons.open_in_new_rounded,
                                size: 18,
                                color: HGColors.blue),
                            title: Text('API docs',
                                style: TextStyle(
                                    fontSize: 13,
                                    color: textColor)),
                            subtitle: Text(
                                'http://localhost:8000/docs',
                                style: TextStyle(
                                    fontSize: 11,
                                    color: mutedColor)),
                            onTap: () =>
                                ScaffoldMessenger.of(context)
                                    .showSnackBar(
                              const SnackBar(
                                  content: Text(
                                      'Open http://localhost:8000/docs in browser — API documentation')),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 28),

                    // 5. View as Citizen
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () => context.go('/citizen/home'),
                        icon: const Icon(Icons.person_outline_rounded, size: 18),
                        label: const Text('View as Citizen',
                            style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600)),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: HGColors.blue,
                          side: const BorderSide(color: HGColors.blue),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // 6. Sign out
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        onPressed: _confirmSignOut,
                        style: OutlinedButton.styleFrom(
                          foregroundColor: HGColors.severe,
                          side: const BorderSide(
                              color: HGColors.severe),
                          padding: const EdgeInsets.symmetric(
                              vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius:
                                  BorderRadius.circular(12)),
                        ),
                        child: const Text('Sign out',
                            style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String label;
  final bool isDark;
  const _SectionLabel({required this.label, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Text(label,
        style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.5,
            color:
                isDark ? HGColors.mutedDark : HGColors.mutedLight));
  }
}

class _AboutRow extends StatelessWidget {
  final bool isDark;
  final Color textColor;
  final Color mutedColor;
  final String label;
  final String value;
  const _AboutRow({
    required this.isDark,
    required this.textColor,
    required this.mutedColor,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Text(label,
                style: TextStyle(
                    fontSize: 13, color: textColor)),
          ),
          Text(value,
              style:
                  TextStyle(fontSize: 13, color: mutedColor)),
        ],
      ),
    );
  }
}
