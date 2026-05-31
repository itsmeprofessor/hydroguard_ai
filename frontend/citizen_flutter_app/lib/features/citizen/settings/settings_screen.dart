import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../shared/providers/auth_provider.dart';
import '../../../shared/providers/prefs_provider.dart';
import '../../../shared/providers/city_provider.dart';
import '../../../shared/widgets/hg_app_bar.dart';

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  bool _gps = false;
  bool _shareAnon = false;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final prefs  = ref.watch(prefsProvider);
    final auth   = ref.watch(authProvider);
    final user   = auth.user;

    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;

    return Scaffold(
      backgroundColor: bg,
      appBar: const HGAppBar(eyebrow: 'Settings', title: 'Personalize'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ---- Profile row ------------------------------------------------
            _buildProfileCard(context, isDark, prefs, user),
            const SizedBox(height: 20),

            // ---- Appearance -------------------------------------------------
            _SettingsGroup(
              title: 'Appearance',
              children: [
                _SettingsRow(
                  icon: Icons.palette_outlined,
                  iconBg: HGColors.violetSoft,
                  iconColor: HGColors.violet,
                  title: 'Theme',
                  subtitle: _themeName(prefs.theme),
                  showDivider: true,
                ),
                _buildThemePicker(isDark, prefs),
              ],
            ),
            const SizedBox(height: 12),

            // ---- Location & Language ----------------------------------------
            _SettingsGroup(
              title: 'Location & Language',
              children: [
                _SettingsRow(
                  icon: Icons.gps_fixed,
                  iconBg: HGColors.monitorSoft,
                  iconColor: HGColors.cyan,
                  title: 'Use GPS location',
                  subtitle: _gps ? 'On' : 'Off',
                  trailing: Switch.adaptive(
                    value: _gps,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => setState(() => _gps = v),
                  ),
                  onTap: () => setState(() => _gps = !_gps),
                ),
                _SettingsRow(
                  icon: Icons.location_city_outlined,
                  iconBg: HGColors.blueSoft,
                  iconColor: HGColors.blue,
                  title: 'Home city',
                  subtitle: prefs.city,
                  trailing: const Icon(Icons.chevron_right, size: 18, color: HGColors.mutedLight),
                  onTap: () => _showCityPicker(context, ref),
                ),
                _SettingsRow(
                  icon: Icons.language_outlined,
                  iconBg: HGColors.safeSoft,
                  iconColor: HGColors.safe,
                  title: 'Language',
                  subtitle: _langLabel(prefs.lang),
                  trailing: const Icon(Icons.chevron_right, size: 18, color: HGColors.mutedLight),
                  onTap: () => _showLanguagePicker(context, ref),
                ),
                const _SettingsRow(
                  icon: Icons.straighten_outlined,
                  iconBg: HGColors.watchSoft,
                  iconColor: HGColors.watch,
                  title: 'Units',
                  subtitle: 'Metric',
                  trailing: Text(
                    'Metric',
                    style: TextStyle(fontSize: 13, color: HGColors.mutedLight),
                  ),
                  showDivider: false,
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ---- Notifications -----------------------------------------------
            _SettingsGroup(
              title: 'Notifications',
              children: [
                _SettingsRow(
                  icon: Icons.notifications_outlined,
                  iconBg: HGColors.blueSoft,
                  iconColor: HGColors.blue,
                  title: 'Push notifications',
                  trailing: Switch.adaptive(
                    value: prefs.notif,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setNotif(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setNotif(!prefs.notif),
                ),
                _SettingsRow(
                  icon: Icons.warning_amber_outlined,
                  iconBg: HGColors.severeSoft,
                  iconColor: HGColors.severe,
                  title: 'Critical alerts only',
                  trailing: Switch.adaptive(
                    value: prefs.critOnly,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setCritOnly(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setCritOnly(!prefs.critOnly),
                ),
                _SettingsRow(
                  icon: Icons.bedtime_outlined,
                  iconBg: const Color(0xFFEDE9FE),
                  iconColor: HGColors.violet,
                  title: 'Quiet hours',
                  subtitle: '10 PM – 6 AM',
                  trailing: Switch.adaptive(
                    value: prefs.quiet,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setQuiet(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setQuiet(!prefs.quiet),
                ),
                _SettingsRow(
                  icon: Icons.sms_outlined,
                  iconBg: HGColors.safeSoft,
                  iconColor: HGColors.safe,
                  title: 'SMS fallback',
                  trailing: Switch.adaptive(
                    value: prefs.sms,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setSms(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setSms(!prefs.sms),
                  showDivider: false,
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ---- Accessibility -----------------------------------------------
            _SettingsGroup(
              title: 'Accessibility',
              children: [
                _SettingsRow(
                  icon: Icons.text_fields_outlined,
                  iconBg: HGColors.monitorSoft,
                  iconColor: HGColors.cyan,
                  title: 'Larger text',
                  trailing: Switch.adaptive(
                    value: prefs.bigText,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setBigText(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setBigText(!prefs.bigText),
                ),
                _SettingsRow(
                  icon: Icons.contrast_outlined,
                  iconBg: const Color(0xFF1A1A2E),
                  iconColor: Colors.white,
                  title: 'High contrast',
                  trailing: Switch.adaptive(
                    value: prefs.contrast,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => ref.read(prefsProvider.notifier).setContrast(v),
                  ),
                  onTap: () => ref.read(prefsProvider.notifier).setContrast(!prefs.contrast),
                ),
                _SettingsRow(
                  icon: Icons.record_voice_over_outlined,
                  iconBg: HGColors.warningSoft,
                  iconColor: HGColors.warning,
                  title: 'Voice alerts',
                  trailing: const Icon(Icons.chevron_right, size: 18, color: HGColors.mutedLight),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Voice alerts — coming soon'),
                        duration: Duration(seconds: 2),
                      ),
                    );
                  },
                  showDivider: false,
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ---- Privacy & data ---------------------------------------------
            _SettingsGroup(
              title: 'Privacy & data',
              children: [
                _SettingsRow(
                  icon: Icons.analytics_outlined,
                  iconBg: HGColors.blueSoft,
                  iconColor: HGColors.blue,
                  title: 'Share anonymous data',
                  subtitle: 'Helps improve flood predictions',
                  trailing: Switch.adaptive(
                    value: _shareAnon,
                    activeTrackColor: HGColors.blue,
                    onChanged: (v) => setState(() => _shareAnon = v),
                  ),
                  onTap: () => setState(() => _shareAnon = !_shareAnon),
                ),
                _SettingsRow(
                  icon: Icons.info_outline,
                  iconBg: HGColors.safeSoft,
                  iconColor: HGColors.safe,
                  title: 'About HydroGuard',
                  trailing: const Icon(Icons.chevron_right, size: 18, color: HGColors.mutedLight),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('HydroGuard v3.3.0 — Flood Intelligence Platform'),
                        duration: Duration(seconds: 3),
                      ),
                    );
                  },
                  showDivider: false,
                ),
              ],
            ),
            const SizedBox(height: 20),

            // ---- Sign out ---------------------------------------------------
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => ref.read(authProvider.notifier).logout(),
                icon: const Icon(Icons.logout, size: 16),
                label: const Text('Sign out'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: HGColors.severe,
                  side: const BorderSide(color: HGColors.severe),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  // ---- Profile card ---------------------------------------------------------

  Widget _buildProfileCard(
    BuildContext context,
    bool isDark,
    AppPrefs prefs,
    dynamic user,
  ) {
    final username = user?.username ?? 'User';
    final initial  = username.isNotEmpty ? username[0].toUpperCase() : 'U';

    return Container(
      decoration: BoxDecoration(
        color: isDark ? HGColors.cardDark : HGColors.cardLight,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: isDark ? HGColors.lineDark : HGColors.lineLight,
        ),
      ),
      child: InkWell(
        onTap: () => context.push('/citizen/profile'),
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              // Avatar
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    colors: [Color(0xFF6366F1), Color(0xFF06B6D4)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                child: Center(
                  child: Text(
                    initial,
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // User info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      username,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: isDark ? HGColors.textDark : HGColors.textLight,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${prefs.city} · HydroGuard',
                      style: const TextStyle(
                        fontSize: 13,
                        color: HGColors.mutedLight,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.chevron_right,
                size: 20,
                color: HGColors.mutedLight,
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ---- Theme picker ---------------------------------------------------------

  Widget _buildThemePicker(bool isDark, AppPrefs prefs) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      child: Row(
        children: ['light', 'dark', 'system'].map((v) {
          final label    = v == 'light' ? 'Light' : v == 'dark' ? 'Dark' : 'Auto';
          final selected = prefs.theme == v;
          final previewBg = v == 'dark'
              ? const Color(0xFF0B0F17)
              : const Color(0xFFF4F6FB);
          final barColor = v == 'dark'
              ? const Color(0xFF1E293B)
              : const Color(0xFFDBE7FE);

          return Expanded(
            child: GestureDetector(
              onTap: () => ref.read(prefsProvider.notifier).setTheme(v),
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: selected
                        ? HGColors.blue
                        : (isDark ? HGColors.lineDark : HGColors.lineLight),
                    width: selected ? 2 : 1,
                  ),
                ),
                child: Column(
                  children: [
                    // Mini screen preview
                    Container(
                      height: 48,
                      margin: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: previewBg,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            height: 4,
                            width: 32,
                            margin: const EdgeInsets.symmetric(vertical: 2),
                            decoration: BoxDecoration(
                              color: barColor,
                              borderRadius: BorderRadius.circular(2),
                            ),
                          ),
                          Container(
                            height: 4,
                            width: 20,
                            margin: const EdgeInsets.symmetric(vertical: 2),
                            decoration: BoxDecoration(
                              color: barColor,
                              borderRadius: BorderRadius.circular(2),
                            ),
                          ),
                        ],
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        selected ? '$label ✓' : label,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: selected
                              ? HGColors.blue
                              : (isDark
                                  ? HGColors.mutedDark
                                  : HGColors.mutedLight),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // ---- City picker ----------------------------------------------------------

  void _showCityPicker(BuildContext context, WidgetRef ref) {
    final searchCtrl = TextEditingController();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final isDark = Theme.of(context).brightness == Brightness.dark;
          return Container(
            height: MediaQuery.of(context).size.height * 0.75,
            decoration: BoxDecoration(
              color: isDark ? HGColors.cardDark : HGColors.cardLight,
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(24)),
            ),
            child: Column(
              children: [
                // Handle
                Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(
                    color: HGColors.lineLight,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                // Header
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 4, 12),
                  child: Row(
                    children: [
                      Text(
                        'Select city',
                        style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: isDark
                              ? HGColors.textDark
                              : HGColors.textLight,
                        ),
                      ),
                      const Spacer(),
                      IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                ),
                // Search
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: TextField(
                    controller: searchCtrl,
                    onChanged: (_) => setModalState(() {}),
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.search, size: 18),
                      hintText: 'Search city…',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 10,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                // City list
                Expanded(
                  child: Consumer(
                    builder: (_, ref2, __) {
                      final citiesAsync = ref2.watch(citiesListProvider);
                      return citiesAsync.when(
                        loading: () => const Center(
                            child: CircularProgressIndicator()),
                        error: (e, _) => const Center(
                            child: Text('Failed to load cities')),
                        data: (cities) {
                          final q = searchCtrl.text.toLowerCase();
                          final filtered = cities.where((c) {
                            final name =
                                (c['name'] as String? ?? '').toLowerCase();
                            final prov =
                                (c['province'] as String? ?? '').toLowerCase();
                            return q.isEmpty ||
                                name.contains(q) ||
                                prov.contains(q);
                          }).toList();
                          final prefs = ref2.watch(prefsProvider);
                          return ListView.builder(
                            itemCount: filtered.length,
                            itemBuilder: (_, i) {
                              final city = filtered[i];
                              final name =
                                  city['name'] as String? ?? '';
                              final prov =
                                  city['province'] as String? ?? '';
                              final selected = name == prefs.city;
                              return ListTile(
                                title: Text(name),
                                subtitle:
                                    prov.isNotEmpty ? Text(prov) : null,
                                trailing: selected
                                    ? const Icon(Icons.check,
                                        color: HGColors.blue)
                                    : null,
                                selected: selected,
                                selectedColor: HGColors.blue,
                                onTap: () {
                                  ref2
                                      .read(prefsProvider.notifier)
                                      .setCity(name);
                                  Navigator.pop(ctx);
                                },
                              );
                            },
                          );
                        },
                      );
                    },
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  // ---- Language picker ------------------------------------------------------

  static const _langs = [
    (code: 'en',  label: 'English',  native: 'English'),
    (code: 'ur',  label: 'Urdu',     native: 'اردو'),
    (code: 'pa',  label: 'Punjabi',  native: 'ਪੰਜਾਬੀ'),
    (code: 'ps',  label: 'Pashto',   native: 'پښتو'),
    (code: 'sd',  label: 'Sindhi',   native: 'سنڌي'),
    (code: 'bal', label: 'Balochi',  native: 'بلوچی'),
  ];

  void _showLanguagePicker(BuildContext context, WidgetRef ref) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) {
        final isDark = Theme.of(context).brightness == Brightness.dark;
        return Container(
          decoration: BoxDecoration(
            color: isDark ? HGColors.cardDark : HGColors.cardLight,
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: HGColors.lineLight,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 4, 8),
                child: Row(
                  children: [
                    Text(
                      'Select language',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: isDark
                            ? HGColors.textDark
                            : HGColors.textLight,
                      ),
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => Navigator.pop(context),
                    ),
                  ],
                ),
              ),
              Consumer(builder: (_, ref2, __) {
                final prefs = ref2.watch(prefsProvider);
                return ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: _langs.length,
                  separatorBuilder: (_, __) => Divider(
                    height: 1,
                    indent: 16,
                    color: isDark ? HGColors.lineDark : HGColors.lineLight,
                  ),
                  itemBuilder: (_, i) {
                    final lang = _langs[i];
                    final selected = lang.code == prefs.lang;
                    return ListTile(
                      title: Text(lang.label),
                      subtitle: Text(lang.native),
                      trailing: selected
                          ? const Icon(Icons.check, color: HGColors.blue)
                          : null,
                      selected: selected,
                      selectedColor: HGColors.blue,
                      onTap: () {
                        ref2
                            .read(prefsProvider.notifier)
                            .setLang(lang.code);
                        Navigator.pop(context);
                      },
                    );
                  },
                );
              }),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }

  // ---- Helpers --------------------------------------------------------------

  String _themeName(String theme) => switch (theme) {
        'light'  => 'Light',
        'dark'   => 'Dark',
        'system' => 'System (Auto)',
        _        => 'System (Auto)',
      };

  String _langLabel(String code) {
    for (final l in _langs) {
      if (l.code == code) return l.label;
    }
    return 'English';
  }
}

// ---------------------------------------------------------------------------
// _SettingsGroup
// ---------------------------------------------------------------------------

class _SettingsGroup extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _SettingsGroup({required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8, top: 4),
          child: Text(
            title,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.8,
              color: HGColors.mutedLight,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: isDark ? HGColors.cardDark : HGColors.cardLight,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight,
            ),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _SettingsRow
// ---------------------------------------------------------------------------

class _SettingsRow extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool showDivider;

  const _SettingsRow({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.showDivider = true,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Column(
      children: [
        InkWell(
          onTap: onTap,
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: iconBg,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: Icon(icon, size: 17, color: iconColor),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: isDark
                              ? HGColors.textDark
                              : HGColors.textLight,
                        ),
                      ),
                      if (subtitle != null)
                        Text(
                          subtitle!,
                          style: const TextStyle(
                            fontSize: 12,
                            color: HGColors.mutedLight,
                          ),
                        ),
                    ],
                  ),
                ),
                if (trailing != null) trailing!,
              ],
            ),
          ),
        ),
        if (showDivider)
          Divider(
            height: 1,
            indent: 62,
            color: isDark ? HGColors.lineDark : HGColors.lineLight,
          ),
      ],
    );
  }
}
