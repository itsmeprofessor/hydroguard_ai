import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../models/health_model.dart';
import '../../../models/city_overview_model.dart';
import '../../../shared/providers/admin_provider.dart';
import '../../../shared/providers/auth_provider.dart';
import '../../../shared/providers/prefs_provider.dart';
import '../../../shared/widgets/hg_skeleton.dart';
import '../../../shared/widgets/hg_error_card.dart';

class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark        = Theme.of(context).brightness == Brightness.dark;
    final authState     = ref.watch(authProvider);
    final prefs         = ref.watch(prefsProvider);
    final healthAsync   = ref.watch(healthProvider);
    final countAsync    = ref.watch(anomalyCountProvider);
    final overviewAsync = ref.watch(adminOverviewProvider);

    final now      = TimeOfDay.now();
    final timeStr  = '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    final initials = _initials(authState.user?.username ?? 'A');
    final cityLabel = prefs.city.toLowerCase();

    final elevatedCount = overviewAsync.valueOrNull
        ?.where((c) => c.hriScore >= 20).length ?? 0;

    return Scaffold(
      backgroundColor: isDark ? HGColors.bgDark : HGColors.bgLight,
      body: SafeArea(
        child: Column(
          children: [
            _buildAppBar(context, ref, isDark, initials, cityLabel,
                countAsync),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async {
                  ref.invalidate(healthProvider);
                  ref.invalidate(anomalyCountProvider);
                  ref.invalidate(adminOverviewProvider);
                },
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Hero KPI
                      healthAsync.when(
                        data: (h) => _HeroCard(health: h, timeStr: timeStr,
                            isDark: isDark, elevatedCount: elevatedCount),
                        loading: () => const HGSkeleton(height: 160, borderRadius: 20),
                        error: (e, _) => HGErrorCard(
                            message: 'Health unavailable: $e'),
                      ),
                      const SizedBox(height: 20),
                      _sectionHeader(context, isDark, 'System health',
                          'City HRI →', () => context.go('/admin/hri')),
                      const SizedBox(height: 10),
                      healthAsync.when(
                        data: (h) => _HealthBarsCard(health: h, isDark: isDark),
                        loading: () => const HGSkeleton(height: 130, borderRadius: 16),
                        error: (_, __) => const SizedBox.shrink(),
                      ),
                      const SizedBox(height: 20),
                      _sectionHeader(context, isDark, 'Per-city model state',
                          'All cities →', () => context.go('/admin/hri')),
                      const SizedBox(height: 10),
                      overviewAsync.when(
                        data: (cities) =>
                            _ModelStateCard(cities: cities, isDark: isDark),
                        loading: () => const HGSkeleton(height: 140, borderRadius: 16),
                        error: (_, __) => const SizedBox.shrink(),
                      ),
                      const SizedBox(height: 20),
                      _sectionHeader(context, isDark, 'Current situation',
                          'Alerts →', () => context.go('/admin/alerts')),
                      const SizedBox(height: 10),
                      overviewAsync.when(
                        data: (cities) =>
                            _LiveEventFeedCard(cities: cities, isDark: isDark),
                        loading: () => const HGSkeleton(height: 120, borderRadius: 16),
                        error: (_, __) => const SizedBox.shrink(),
                      ),
                      const SizedBox(height: 20),
                      _sectionHeader(context, isDark, 'Operations', null, null),
                      const SizedBox(height: 10),
                      _OperationsGrid(context: context, isDark: isDark,
                          city: cityLabel),
                      const SizedBox(height: 20),
                      _sectionHeader(
                          context, isDark, 'National situation', null, null),
                      const SizedBox(height: 10),
                      overviewAsync.when(
                        data: (cities) =>
                            _NationalHriCard(cities: cities, isDark: isDark),
                        loading: () => const HGSkeleton(height: 240, borderRadius: 20),
                        error: (_, __) => const SizedBox.shrink(),
                      ),
                      const SizedBox(height: 12),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAppBar(
    BuildContext context,
    WidgetRef ref,
    bool isDark,
    String initials,
    String cityLabel,
    AsyncValue<int> countAsync,
  ) {
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final count     = countAsync.valueOrNull ?? 0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: isDark ? HGColors.cardDark : HGColors.cardLight,
      child: Row(
        children: [
          // Avatar → more
          GestureDetector(
            onTap: () => context.push('/admin/more'),
            child: Container(
              width: 40,
              height: 40,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: [HGColors.violet, HGColors.blue],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: Center(
                child: Text(initials,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 14)),
              ),
            ),
          ),
          const SizedBox(width: 12),
          // Center info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [HGColors.violet, HGColors.blue],
                        ),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Text('ADMIN',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.0)),
                    ),
                    const SizedBox(width: 6),
                    Text('Operations · NDMA',
                        style: TextStyle(
                            fontSize: 11,
                            color: isDark
                                ? HGColors.mutedDark
                                : HGColors.mutedLight)),
                  ],
                ),
                const SizedBox(height: 2),
                Text('$cityLabel command',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: textColor)),
              ],
            ),
          ),
          // Bell + badge
          Stack(
            clipBehavior: Clip.none,
            children: [
              Icon(Icons.notifications_outlined,
                  size: 26,
                  color: isDark ? HGColors.mutedDark : HGColors.mutedLight),
              if (count > 0)
                Positioned(
                  right: -4,
                  top: -4,
                  child: Container(
                    width: 16,
                    height: 16,
                    decoration: const BoxDecoration(
                        color: HGColors.severe, shape: BoxShape.circle),
                    child: Center(
                      child: Text(
                        count > 9 ? '9+' : '$count',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sectionHeader(
    BuildContext context,
    bool isDark,
    String title,
    String? actionLabel,
    VoidCallback? onAction,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(title,
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: isDark ? HGColors.mutedDark : HGColors.mutedLight,
                letterSpacing: 0.5)),
        if (actionLabel != null)
          GestureDetector(
            onTap: onAction,
            child: Text(actionLabel,
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: HGColors.blue)),
          ),
      ],
    );
  }

  static String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    }
    return name.substring(0, name.length.clamp(0, 2)).toUpperCase();
  }
}

// ─── Hero KPI card ────────────────────────────────────────────────────────────

class _HeroCard extends StatelessWidget {
  final HealthModel health;
  final String timeStr;
  final bool isDark;
  final int elevatedCount;

  const _HeroCard({
    required this.health,
    required this.timeStr,
    required this.isDark,
    required this.elevatedCount,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Stack(
          children: [
            // Decorative orbs
            Positioned(
              top: -30,
              left: -30,
              child: Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: HGColors.violet.withValues(alpha: 0.2),
                ),
              ),
            ),
            Positioned(
              bottom: -20,
              right: -20,
              child: Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: HGColors.blue.withValues(alpha: 0.2),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Eyebrow + drift chip
                  Row(
                    children: [
                      Text('System status · $timeStr',
                          style: const TextStyle(
                              fontSize: 12,
                              color: Color(0xFF94A3B8),
                              letterSpacing: 0.3)),
                      const SizedBox(width: 8),
                      _DriftChip(driftStatus: health.driftStatus),
                    ],
                  ),
                  const SizedBox(height: 18),
                  // KPI row
                  IntrinsicHeight(
                    child: Row(
                      children: [
                        Expanded(
                            child: _KpiItem(
                          label: 'Elevated Cities',
                          subLabel: 'HRI ≥ 20',
                          value: '$elevatedCount',
                          valueColor: elevatedCount >= 3
                              ? HGColors.severe
                              : elevatedCount >= 1
                                  ? HGColors.warning
                                  : HGColors.safe,
                        )),
                        const VerticalDivider(
                            color: Color(0x30FFFFFF), width: 1),
                        Expanded(
                            child: _KpiItem(
                          label: 'Models live',
                          value:
                              '${health.trainedCities} / ${health.totalCities}',
                          valueColor: Colors.white,
                        )),
                        const VerticalDivider(
                            color: Color(0x30FFFFFF), width: 1),
                        Expanded(
                            child: _KpiItem(
                          label: 'WS clients',
                          value: '${health.totalWsClients}',
                          valueColor: Colors.white,
                        )),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DriftChip extends StatelessWidget {
  final String driftStatus;
  const _DriftChip({required this.driftStatus});

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (driftStatus) {
      'critical' => (HGColors.severe, 'drift critical'),
      'warn'     => (HGColors.watch, 'drift warn'),
      _          => (HGColors.safe, 'drift ok'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: color)),
    );
  }
}

class _KpiItem extends StatelessWidget {
  final String label;
  final String? subLabel;
  final String value;
  final Color valueColor;

  const _KpiItem({
    required this.label,
    required this.value,
    required this.valueColor,
    this.subLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(value,
            style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w800,
                color: valueColor,
                fontFamily: 'monospace')),
        const SizedBox(height: 4),
        Text(label,
            textAlign: TextAlign.center,
            style: const TextStyle(
                fontSize: 11,
                color: Color(0xFF94A3B8))),
        if (subLabel != null) ...[
          const SizedBox(height: 2),
          Text(subLabel!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 10,
                  color: Color(0xFF64748B))),
        ],
      ],
    );
  }
}

// ─── System health bars ───────────────────────────────────────────────────────

class _HealthBarsCard extends StatelessWidget {
  final HealthModel health;
  final bool isDark;
  const _HealthBarsCard({required this.health, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final cardColor = isDark ? HGColors.cardDark : HGColors.cardLight;
    final driftPct  = switch (health.driftStatus) {
      'critical' => 0.30,
      'warn'     => 0.50,
      _          => 0.90,
    };
    final driftColor = switch (health.driftStatus) {
      'critical' => HGColors.severe,
      'warn'     => HGColors.watch,
      _          => HGColors.safe,
    };
    final driftLabel = switch (health.driftStatus) {
      'critical' => 'Critical',
      'warn'     => 'Warn',
      _          => 'OK',
    };
    final driftCityCount =
        health.criticalDriftCities.length + health.warnDriftCities.length;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Column(
        children: [
          _HealthRow(
            isDark: isDark,
            icon: Icons.auto_awesome_rounded,
            iconColor: HGColors.blue,
            label: 'HRI engine',
            rightLabel: '${health.trainedCities} / ${health.totalCities}',
            pillLabel:
                '${(health.modelCoveragePct * 100).toStringAsFixed(0)}%',
            pillColor: health.modelCoveragePct > 0.8
                ? HGColors.safe
                : HGColors.watch,
            pct: health.modelCoveragePct,
            barColor: HGColors.blue,
          ),
          _divider(isDark),
          _HealthRow(
            isDark: isDark,
            icon: Icons.show_chart_rounded,
            iconColor: HGColors.cyan,
            label: 'Data ingest',
            rightLabel: 'Live',
            pillLabel: 'WeatherAPI',
            pillColor: HGColors.monitor,
            pct: 0.92,
            barColor: HGColors.cyan,
          ),
          _divider(isDark),
          _HealthRow(
            isDark: isDark,
            icon: Icons.analytics_rounded,
            iconColor: HGColors.violet,
            label: 'Drift monitor',
            rightLabel: '$driftCityCount cities',
            pillLabel: driftLabel,
            pillColor: driftColor,
            pct: driftPct,
            barColor: driftColor,
          ),
        ],
      ),
    );
  }

  Widget _divider(bool isDark) => Divider(
      height: 20,
      color: isDark ? HGColors.lineDark : HGColors.lineLight);
}

class _HealthRow extends StatelessWidget {
  final bool isDark;
  final IconData icon;
  final Color iconColor;
  final String label;
  final String rightLabel;
  final String pillLabel;
  final Color pillColor;
  final double pct;
  final Color barColor;

  const _HealthRow({
    required this.isDark,
    required this.icon,
    required this.iconColor,
    required this.label,
    required this.rightLabel,
    required this.pillLabel,
    required this.pillColor,
    required this.pct,
    required this.barColor,
  });

  @override
  Widget build(BuildContext context) {
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    return Column(
      children: [
        Row(
          children: [
            Icon(icon, size: 18, color: iconColor),
            const SizedBox(width: 8),
            Expanded(
                child: Text(label,
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: textColor))),
            Text(rightLabel,
                style:
                    TextStyle(fontSize: 12, color: mutedColor)),
            const SizedBox(width: 6),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: pillColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(pillLabel,
                  style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: pillColor)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        LayoutBuilder(builder: (_, constraints) {
          return Stack(
            children: [
              Container(
                height: 4,
                width: constraints.maxWidth,
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFE2E8F0),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Container(
                height: 4,
                width: constraints.maxWidth * pct.clamp(0.0, 1.0),
                decoration: BoxDecoration(
                  color: barColor,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ],
          );
        }),
      ],
    );
  }
}

// ─── Per-city model state ──────────────────────────────────────────────────────

class _ModelStateCard extends StatelessWidget {
  final List<CityOverviewModel> cities;
  final bool isDark;
  const _ModelStateCard({required this.cities, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final show = cities.take(4).toList();
    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Container(
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Column(
        children: List.generate(show.length, (i) {
          final c         = show[i];
          final isModel   = !c.isHeuristic;
          final srcLabel  = isModel ? 'Model' : 'Heuristic';
          final srcColor  = isModel ? HGColors.safe : HGColors.watch;
          final stability =
              c.isHeuristic ? 'Degraded · MC fallback' : 'Stable · MC active';

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(c.name,
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: textColor)),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: srcColor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(srcLabel,
                          style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                              color: srcColor)),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(stability,
                            style: TextStyle(
                                fontSize: 10, color: mutedColor)),
                        Text('HRI ${c.hriScore}',
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: HGColors.forScenario(c.levelKey))),
                      ],
                    ),
                  ],
                ),
              ),
              if (i < show.length - 1)
                Divider(
                    height: 1,
                    color: isDark
                        ? HGColors.lineDark
                        : HGColors.lineLight),
            ],
          );
        }),
      ),
    );
  }
}

// ─── Live event feed ──────────────────────────────────────────────────────────

class _LiveEventFeedCard extends StatelessWidget {
  final List<CityOverviewModel> cities;
  final bool isDark;
  const _LiveEventFeedCard({required this.cities, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final sorted = [...cities]..sort((a, b) => b.hriScore.compareTo(a.hriScore));
    final top5   = sorted.take(5).toList();
    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    if (top5.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Text('No active events. Background ML monitoring.',
            style: TextStyle(fontSize: 13, color: mutedColor)),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Column(
        children: List.generate(top5.length, (i) {
          final c         = top5[i];
          final color     = HGColors.forScenario(c.levelKey);
          final riskLabel = _riskLabel(c.levelKey);

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 11),
                child: Row(
                  children: [
                    // Pulsing dot
                    _PulsingDot(color: color),
                    const SizedBox(width: 10),
                    Text(riskLabel,
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: color)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(c.name,
                          style: TextStyle(
                              fontSize: 13, color: textColor)),
                    ),
                    Text('HRI ${c.hriScore}',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: color)),
                    const SizedBox(width: 6),
                    Text(c.isHeuristic ? 'Heuristic' : 'ML',
                        style: TextStyle(
                            fontSize: 10, color: mutedColor)),
                  ],
                ),
              ),
              if (i < top5.length - 1)
                Divider(
                    height: 1,
                    color: isDark
                        ? HGColors.lineDark
                        : HGColors.lineLight),
            ],
          );
        }),
      ),
    );
  }

  static String _riskLabel(String levelKey) => switch (levelKey) {
    'severe'  => 'Severe',
    'warning' => 'Warning',
    'watch'   => 'Watch',
    'monitor' => 'Monitor',
    _         => 'Safe',
  };
}

class _PulsingDot extends StatefulWidget {
  final Color color;
  const _PulsingDot({required this.color});

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.5, end: 1.0).animate(
        CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color.withValues(alpha: _anim.value),
          boxShadow: [
            BoxShadow(
                color: widget.color.withValues(alpha: _anim.value * 0.5),
                blurRadius: 6,
                spreadRadius: 1),
          ],
        ),
      ),
    );
  }
}

// ─── Operations grid ──────────────────────────────────────────────────────────

class _OperationsGrid extends StatelessWidget {
  final BuildContext context;
  final bool isDark;
  final String city;
  const _OperationsGrid(
      {required this.context,
      required this.isDark,
      required this.city});

  @override
  Widget build(BuildContext buildContext) {
    final cardColor = isDark ? HGColors.cardDark : HGColors.cardLight;
    final items = [
      _QuickAction(
        icon: Icons.notifications_active_rounded,
        label: 'Manual Prediction',
        color: HGColors.severe,
        onTap: () => buildContext.push('/admin/predict'),
      ),
      _QuickAction(
        icon: Icons.auto_awesome_rounded,
        label: 'HRI models',
        color: HGColors.blue,
        onTap: () => buildContext.go('/admin/hri'),
      ),
      _QuickAction(
        icon: Icons.people_alt_rounded,
        label: 'Dispatch',
        color: HGColors.violet,
        onTap: () => ScaffoldMessenger.of(buildContext).showSnackBar(
          const SnackBar(content: Text('Dispatch — coming soon')),
        ),
      ),
      _QuickAction(
        icon: Icons.bar_chart_rounded,
        label: 'Reports',
        color: HGColors.cyan,
        onTap: () => ScaffoldMessenger.of(buildContext).showSnackBar(
          const SnackBar(content: Text('Reports — coming soon')),
        ),
      ),
    ];

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 2.4,
      children: items.map((item) {
        return GestureDetector(
          onTap: item.onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                  color: isDark ? HGColors.lineDark : HGColors.lineLight),
            ),
            child: Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: item.color.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(item.icon, size: 18, color: item.color),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(item.label,
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: isDark
                              ? HGColors.textDark
                              : HGColors.textLight)),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _QuickAction {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _QuickAction(
      {required this.icon,
      required this.label,
      required this.color,
      required this.onTap});
}

// ─── National HRI grid ────────────────────────────────────────────────────────

class _NationalHriCard extends StatelessWidget {
  final List<CityOverviewModel> cities;
  final bool isDark;
  const _NationalHriCard({required this.cities, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final sorted = [...cities]..sort((a, b) => b.hriScore.compareTo(a.hriScore));
    final top6   = sorted.take(6).toList();

    final severeCount  = cities.where((c) => c.levelKey == 'severe').length;
    final warningCount = cities.where((c) => c.levelKey == 'warning').length;
    final safeCount    = cities
        .where((c) => c.levelKey == 'safe' || c.levelKey == 'monitor')
        .length;

    final activeCount = cities
        .where((c) => c.hriScore >= 60)
        .length;
    final statusTitle = activeCount > 0
        ? '$activeCount active'
        : 'Background monitoring';

    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header sub-card
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Pakistan flood intelligence · live',
                            style: TextStyle(
                                fontSize: 10,
                                color: Color(0xFF94A3B8),
                                letterSpacing: 0.3)),
                        const SizedBox(height: 4),
                        Text(statusTitle,
                            style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                                color: Colors.white)),
                        const SizedBox(height: 4),
                        Text(
                            '$severeCount high-risk · $safeCount stable · ${cities.length} cities monitored',
                            style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF94A3B8))),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Column(
                    children: [
                      _CountChip(
                          count: severeCount,
                          label: 'Severe',
                          color: HGColors.severe),
                      const SizedBox(height: 4),
                      _CountChip(
                          count: warningCount,
                          label: 'Warning',
                          color: HGColors.watch),
                      const SizedBox(height: 4),
                      _CountChip(
                          count: safeCount,
                          label: 'Stable',
                          color: HGColors.cyan),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 16),
              // City grid rows
              ...top6.map((c) {
                final color = HGColors.forScenario(c.levelKey);
                final pct   = c.hriScore / 100.0;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 80,
                        child: Text(c.name,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFFCBD5E1))),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 36,
                        child: Text('${c.hriScore}',
                            textAlign: TextAlign.right,
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                fontFamily: 'monospace',
                                color: color)),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(2),
                          child: Stack(
                            children: [
                              Container(
                                  height: 4,
                                  color: const Color(0xFF334155)),
                              FractionallySizedBox(
                                widthFactor: pct.clamp(0.0, 1.0),
                                child: Container(
                                    height: 4, color: color),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 52,
                        child: Text(c.riskBand,
                            textAlign: TextAlign.right,
                            style: TextStyle(
                                fontSize: 10, color: color)),
                      ),
                    ],
                  ),
                );
              }),
            ],
          ),
        ),
      ),
    );
  }
}

class _CountChip extends StatelessWidget {
  final int count;
  final String label;
  final Color color;
  const _CountChip(
      {required this.count, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('$count',
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: color)),
          const SizedBox(width: 3),
          Text(label,
              style: TextStyle(fontSize: 10, color: color)),
        ],
      ),
    );
  }
}
