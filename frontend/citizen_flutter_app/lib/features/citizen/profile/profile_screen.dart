import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../core/storage/local_storage.dart';
import '../../../shared/providers/auth_provider.dart';
import '../../../shared/providers/prefs_provider.dart';

// ---------------------------------------------------------------------------
// Avatar theme data
// ---------------------------------------------------------------------------

const _themes = [
  ('indigo',  [Color(0xFF6366F1), Color(0xFF06B6D4)]),
  ('blue',    [Color(0xFF2563EB), Color(0xFF0EA5E9)]),
  ('violet',  [Color(0xFF7C3AED), Color(0xFFDB2777)]),
  ('emerald', [Color(0xFF059669), Color(0xFF22C55E)]),
  ('amber',   [Color(0xFFD97706), Color(0xFFF59E0B)]),
  ('rose',    [Color(0xFFE11D48), Color(0xFFF97316)]),
];

List<Color> _colorsForAccent(String? accent) {
  for (final t in _themes) {
    if (t.$1 == accent) return t.$2;
  }
  return _themes[0].$2;
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  bool _editing = false;
  Map<String, String> _local  = {};
  Map<String, String> _draft  = {};

  @override
  void initState() {
    super.initState();
    final raw = LocalStorage.instance.localProfile;
    if (raw != null) {
      try {
        final decoded = jsonDecode(raw) as Map<String, dynamic>;
        _local = decoded.map((k, v) => MapEntry(k, v.toString()));
      } catch (_) {}
    }
  }

  void _startEdit() => setState(() {
        _draft   = Map.from(_local);
        _editing = true;
      });

  void _cancel() => setState(() {
        _editing = false;
        _draft   = {};
      });

  void _save() {
    setState(() {
      _local   = Map.from(_draft);
      _editing = false;
    });
    LocalStorage.instance.setLocalProfile(jsonEncode(_local));
  }

  // ---- Helpers ---------------------------------------------------------------

  String _memberSince(String? createdAt) {
    if (createdAt == null) return '—';
    try {
      final dt = DateTime.parse(createdAt);
      const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
      ];
      return '${months[dt.month - 1]} ${dt.year}';
    } catch (_) {
      return '—';
    }
  }

  // ---- Build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final isDark    = Theme.of(context).brightness == Brightness.dark;
    final authState = ref.watch(authProvider);
    final prefs     = ref.watch(prefsProvider);
    final user      = authState.user;

    final accent  = _local['accent'] ?? 'indigo';
    final colors  = _colorsForAccent(accent);
    final display = _local['displayName']?.isNotEmpty == true
        ? _local['displayName']!
        : (user?.username ?? 'User');
    final initial = display[0].toUpperCase();

    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;

    return Scaffold(
      backgroundColor: bg,
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ---- Custom app bar ----------------------------------------
            SafeArea(
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.arrow_back),
                      color: isDark ? HGColors.textDark : HGColors.textLight,
                      onPressed: () => context.pop(),
                    ),
                    Expanded(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Profile',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: isDark
                                  ? HGColors.textDark
                                  : HGColors.textLight,
                            ),
                          ),
                          const Text(
                            'Personal details',
                            style: TextStyle(
                              fontSize: 11,
                              color: HGColors.mutedLight,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_editing)
                      IconButton(
                        icon: const Icon(Icons.check),
                        color: HGColors.blue,
                        onPressed: _save,
                      )
                    else
                      IconButton(
                        icon: const Icon(Icons.edit_outlined),
                        color: isDark
                            ? HGColors.textDark
                            : HGColors.textLight,
                        onPressed: _startEdit,
                      ),
                  ],
                ),
              ),
            ),

            // ---- Avatar hero section -----------------------------------
            _buildAvatarHero(
              context,
              isDark:  isDark,
              colors:  colors,
              initial: initial,
              display: display,
              accent:  accent,
              user:    user,
            ),

            // ---- Stats row -------------------------------------------
            _buildStatsRow(context, isDark, prefs, user),

            // ---- Content sections ------------------------------------
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Account information (read-only, from server)
                  _InfoGroup(
                    title: 'Account information',
                    badge: 'From server',
                    badgeColor: HGColors.blue,
                    children: [
                      _InfoField(
                        label: 'Username',
                        value: user?.username ?? '—',
                      ),
                      _InfoField(
                        label: 'Email',
                        value: user?.email ?? '—',
                      ),
                      _InfoField(
                        label: 'Account type',
                        value: (user?.role ?? 'user').toLowerCase(),
                        isLast: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Personal information (saved locally)
                  _InfoGroup(
                    title: 'Personal information',
                    badge: 'Saved locally',
                    badgeColor: HGColors.safe,
                    children: [
                      _personalField(
                        'displayName', 'Display name'),
                      _personalField('phone', 'Phone'),
                      _personalField('cnic', 'CNIC'),
                      _personalField('dob', 'Date of birth'),
                      _personalField('bloodType', 'Blood type',
                          isLast: true),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Address
                  _InfoGroup(
                    title: 'Address',
                    badge: 'Saved locally',
                    badgeColor: HGColors.safe,
                    children: [
                      _editing
                          ? _EditField(
                              label: 'Street address',
                              value: _draft['address'] ?? '',
                              maxLines: 2,
                              onChanged: (v) =>
                                  setState(() => _draft['address'] = v),
                            )
                          : _InfoField(
                              label: 'Street address',
                              value: _local['address'] ?? '—',
                            ),
                      _InfoField(
                        label: 'City',
                        value: prefs.city,
                        isLast: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Emergency contact
                  _InfoGroup(
                    title: 'Emergency contact',
                    badge: 'Saved locally',
                    badgeColor: HGColors.safe,
                    children: [
                      _personalField(
                          'emergencyName', 'Name'),
                      _personalField(
                          'emergencyRel', 'Relationship'),
                      _personalField(
                          'emergencyPhone', 'Phone',
                          isLast: true),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Medical notes
                  _InfoGroup(
                    title: 'Medical notes',
                    badge: 'Saved locally',
                    badgeColor: HGColors.safe,
                    children: [
                      _editing
                          ? _EditField(
                              label: 'Medical notes',
                              value: _draft['medical'] ?? '',
                              maxLines: 3,
                              onChanged: (v) =>
                                  setState(() => _draft['medical'] = v),
                            )
                          : _InfoField(
                              label: 'Medical notes',
                              value: _local['medical'] ?? '—',
                              isLast: true,
                            ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Bottom action row
                  _buildActions(),
                  const SizedBox(height: 32),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ---- Avatar hero ----------------------------------------------------------

  Widget _buildAvatarHero(
    BuildContext context, {
    required bool isDark,
    required List<Color> colors,
    required String initial,
    required String display,
    required String accent,
    required dynamic user,
  }) {
    final memberSince = _memberSince(user?.createdAt);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            colors[0].withValues(alpha: isDark ? 0.15 : 0.08),
            colors[1].withValues(alpha: isDark ? 0.08 : 0.04),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        children: [
          // Avatar
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: colors,
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              boxShadow: [
                BoxShadow(
                  color: colors[0].withValues(alpha: 0.4),
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Center(
              child: Text(
                initial,
                style: const TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
            ),
          ),

          // Theme swatches (edit mode only)
          if (_editing) ...[
            const SizedBox(height: 12),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: _themes.map((t) {
                final isSelected = (t.$1 == (_draft['accent'] ?? 'indigo'));
                return GestureDetector(
                  onTap: () => setState(() => _draft['accent'] = t.$1),
                  child: Container(
                    width: 24,
                    height: 24,
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: LinearGradient(
                        colors: t.$2,
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      border: isSelected
                          ? Border.all(
                              color: Colors.white,
                              width: 2,
                            )
                          : null,
                      boxShadow: isSelected
                          ? [
                              BoxShadow(
                                color:
                                    t.$2[0].withValues(alpha: 0.5),
                                blurRadius: 6,
                              )
                            ]
                          : null,
                    ),
                  ),
                );
              }).toList(),
            ),
          ],

          const SizedBox(height: 12),
          Text(
            display,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: isDark ? HGColors.textDark : HGColors.textLight,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Member since $memberSince',
            style: const TextStyle(
              fontSize: 13,
              color: HGColors.mutedLight,
            ),
          ),
        ],
      ),
    );
  }

  // ---- Stats row ------------------------------------------------------------

  Widget _buildStatsRow(
    BuildContext context,
    bool isDark,
    AppPrefs prefs,
    dynamic user,
  ) {
    final role = user?.role?.toLowerCase() ?? 'user';
    final cardColor = isDark ? HGColors.cardDark : HGColors.cardLight;
    final lineColor = isDark ? HGColors.lineDark : HGColors.lineLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 0),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: lineColor),
      ),
      child: Row(
        children: [
          _StatCell(
            label: 'Home city',
            value: prefs.city,
            textColor: textColor,
          ),
          VerticalDivider(width: 1, color: lineColor),
          _StatCell(
            label: 'Role',
            value: role,
            textColor: textColor,
          ),
          VerticalDivider(width: 1, color: lineColor),
          _StatCell(
            label: 'Prep score',
            value: _local['prepScore'] ?? '—',
            textColor: textColor,
          ),
        ],
      ),
    );
  }

  // ---- Bottom actions -------------------------------------------------------

  Widget _buildActions() {
    if (_editing) {
      return Row(
        children: [
          Expanded(
            child: OutlinedButton(
              onPressed: _cancel,
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: const Text('Cancel'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: FilledButton(
              onPressed: _save,
              style: FilledButton.styleFrom(
                backgroundColor: HGColors.blue,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: const Text('Save changes'),
            ),
          ),
        ],
      );
    }

    return SizedBox(
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
    );
  }

  // ---- Personal field helper ------------------------------------------------

  Widget _personalField(String key, String label, {bool isLast = false}) {
    if (_editing) {
      return _EditField(
        label: label,
        value: _draft[key] ?? '',
        onChanged: (v) => setState(() => _draft[key] = v),
      );
    }
    return _InfoField(
      label: label,
      value: _local[key] ?? '—',
      isLast: isLast,
    );
  }
}

// ---------------------------------------------------------------------------
// _StatCell
// ---------------------------------------------------------------------------

class _StatCell extends StatelessWidget {
  final String label;
  final String value;
  final Color textColor;

  const _StatCell({
    required this.label,
    required this.value,
    required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        child: Column(
          children: [
            Text(
              value,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: textColor,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                color: HGColors.mutedLight,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _InfoGroup
// ---------------------------------------------------------------------------

class _InfoGroup extends StatelessWidget {
  final String title;
  final String badge;
  final Color? badgeColor;
  final List<Widget> children;

  const _InfoGroup({
    required this.title,
    required this.badge,
    this.badgeColor,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    final isDark    = Theme.of(context).brightness == Brightness.dark;
    final lineColor = isDark ? HGColors.lineDark : HGColors.lineLight;
    final cardColor = isDark ? HGColors.cardDark : HGColors.cardLight;
    final color     = badgeColor ?? HGColors.blue;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8, top: 4),
          child: Row(
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.8,
                  color: HGColors.mutedLight,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  badge,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: color,
                  ),
                ),
              ),
            ],
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: cardColor,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: lineColor),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _InfoField  (read-only)
// ---------------------------------------------------------------------------

class _InfoField extends StatelessWidget {
  final String label;
  final String value;
  final bool isLast;

  const _InfoField({
    required this.label,
    required this.value,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final isDark    = Theme.of(context).brightness == Brightness.dark;
    final lineColor = isDark ? HGColors.lineDark : HGColors.lineLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 120,
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 13,
                    color: HGColors.mutedLight,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  value,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: textColor,
                  ),
                ),
              ),
            ],
          ),
        ),
        if (!isLast)
          Divider(height: 1, indent: 16, color: lineColor),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _EditField  (editable)
// ---------------------------------------------------------------------------

class _EditField extends StatelessWidget {
  final String label;
  final String value;
  final ValueChanged<String> onChanged;
  final int maxLines;

  const _EditField({
    required this.label,
    required this.value,
    required this.onChanged,
    this.maxLines = 1,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: TextFormField(
        initialValue: value,
        onChanged: onChanged,
        maxLines: maxLines,
        style: const TextStyle(fontSize: 14),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: const TextStyle(
            fontSize: 13,
            color: HGColors.mutedLight,
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 12,
            vertical: 10,
          ),
        ),
      ),
    );
  }
}
