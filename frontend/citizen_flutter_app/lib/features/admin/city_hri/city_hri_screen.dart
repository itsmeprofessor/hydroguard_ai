import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../models/city_overview_model.dart';
import '../../../shared/providers/admin_provider.dart';
import '../../../shared/widgets/hg_skeleton.dart';
import '../../../shared/widgets/hg_error_card.dart';
import '../../../shared/widgets/risk_pill.dart';

// Band helpers
String _bandOf(CityOverviewModel c) {
  if (c.isHeuristic && c.hriScore == 0) return 'offline';
  final h = c.hriScore;
  if (h >= 86) return 'severe';
  if (h >= 60) return 'warning';
  if (h >= 35) return 'watch';
  if (h >= 15) return 'monitor';
  return 'ok';
}

const _bandColors = {
  'ok':      Color(0xFF22C55E),
  'monitor': Color(0xFF06B6D4),
  'watch':   Color(0xFFEAB308),
  'warning': Color(0xFFF97316),
  'severe':  Color(0xFFEF4444),
  'offline': Color(0xFF8B95A5),
};

const _bandLabels = {
  'ok':      'Low risk',
  'monitor': 'Monitor',
  'watch':   'Watch',
  'warning': 'Warning',
  'severe':  'Critical',
  'offline': 'Heuristic',
};

class CityHriScreen extends ConsumerWidget {
  const CityHriScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark        = Theme.of(context).brightness == Brightness.dark;
    final overviewAsync = ref.watch(adminOverviewProvider);

    return Scaffold(
      backgroundColor: isDark ? HGColors.bgDark : HGColors.bgLight,
      body: SafeArea(
        child: Column(
          children: [
            _buildAppBar(context, isDark, overviewAsync),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async => ref.invalidate(adminOverviewProvider),
                child: overviewAsync.when(
                  data: (cities) => _buildBody(context, isDark, cities),
                  loading: () => ListView(
                    padding: const EdgeInsets.all(16),
                    children: const [
                      HGSkeleton(height: 60, borderRadius: 12),
                      SizedBox(height: 16),
                      HGSkeleton(height: 400, borderRadius: 16),
                    ],
                  ),
                  error: (e, _) => ListView(
                    padding: const EdgeInsets.all(16),
                    children: [HGErrorCard(message: 'Failed to load: $e')],
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
    bool isDark,
    AsyncValue<List<CityOverviewModel>> overviewAsync,
  ) {
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final liveLabel  = overviewAsync.whenOrNull(
          data: (cities) {
            final trained = cities.where((c) => !c.isHeuristic).length;
            return '$trained/${cities.length} live';
          },
        ) ??
        '— live';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
      color: isDark ? HGColors.cardDark : HGColors.cardLight,
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
            onPressed: () => context.go('/admin/dashboard'),
            color: isDark ? HGColors.mutedDark : HGColors.mutedLight,
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('City HRI',
                    style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: textColor)),
                Text(liveLabel,
                    style: TextStyle(fontSize: 11, color: mutedColor)),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.filter_list_rounded, size: 22),
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Filter — coming soon')),
            ),
            color: isDark ? HGColors.mutedDark : HGColors.mutedLight,
          ),
        ],
      ),
    );
  }

  Widget _buildBody(
      BuildContext context, bool isDark, List<CityOverviewModel> cities) {
    final sorted = [...cities]..sort((a, b) => b.hriScore.compareTo(a.hriScore));
    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    // Count by band
    final Map<String, int> bandCounts = {};
    for (final c in cities) {
      final band = _bandOf(c);
      bandCounts[band] = (bandCounts[band] ?? 0) + 1;
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        // Band distribution bar
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: cardColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: isDark ? HGColors.lineDark : HGColors.lineLight),
          ),
          child: Column(
            children: [
              // Segmented bar
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: SizedBox(
                  height: 8,
                  child: Row(
                    children: _buildBandSegments(cities, bandCounts),
                  ),
                ),
              ),
              const SizedBox(height: 10),
              // Legend
              Wrap(
                spacing: 10,
                runSpacing: 6,
                children: _bandColors.entries
                    .where((e) => (bandCounts[e.key] ?? 0) > 0)
                    .map((e) {
                  final count = bandCounts[e.key] ?? 0;
                  return Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                              shape: BoxShape.circle, color: e.value)),
                      const SizedBox(width: 4),
                      Text('$count ${_bandLabels[e.key] ?? e.key}',
                          style:
                              TextStyle(fontSize: 11, color: mutedColor)),
                    ],
                  );
                }).toList(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // Section header
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('All monitored cities',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: mutedColor,
                    letterSpacing: 0.5)),
            const Text('Filter →',
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: HGColors.blue)),
          ],
        ),
        const SizedBox(height: 10),
        // City list
        Container(
          decoration: BoxDecoration(
            color: cardColor,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: isDark ? HGColors.lineDark : HGColors.lineLight),
          ),
          child: Column(
            children: List.generate(sorted.length, (i) {
              final c    = sorted[i];
              final band = _bandOf(c);
              final col  = _bandColors[band] ?? HGColors.monitor;
              final lbl  = _bandLabels[band] ?? band;

              return Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    child: Row(
                      children: [
                        _PulsingDot(color: col),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    c.slug
                                        .substring(
                                            0, c.slug.length.clamp(0, 3))
                                        .toUpperCase(),
                                    style: TextStyle(
                                        fontSize: 10,
                                        fontFamily: 'monospace',
                                        color: mutedColor,
                                        letterSpacing: 0.5),
                                  ),
                                  const SizedBox(width: 6),
                                  Text(c.name,
                                      style: TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w600,
                                          color: isDark
                                              ? HGColors.textDark
                                              : HGColors.textLight)),
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                c.isHeuristic
                                    ? 'Heuristic mode — no trained model'
                                    : '${c.alertTierLabel} · ML update live',
                                style: TextStyle(
                                    fontSize: 10, color: mutedColor),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.baseline,
                              textBaseline: TextBaseline.alphabetic,
                              children: [
                                Text('${c.hriScore}',
                                    style: TextStyle(
                                        fontSize: 22,
                                        fontWeight: FontWeight.w800,
                                        fontFamily: 'monospace',
                                        color: col)),
                                Text('/100',
                                    style: TextStyle(
                                        fontSize: 10,
                                        color: mutedColor)),
                              ],
                            ),
                            RiskPill(scenario: band, label: lbl),
                          ],
                        ),
                      ],
                    ),
                  ),
                  if (i < sorted.length - 1)
                    Divider(
                        height: 1,
                        color: isDark
                            ? HGColors.lineDark
                            : HGColors.lineLight),
                ],
              );
            }),
          ),
        ),
      ],
    );
  }

  List<Widget> _buildBandSegments(
      List<CityOverviewModel> cities, Map<String, int> counts) {
    final total = cities.length;
    if (total == 0) {
      return [Expanded(child: Container(color: const Color(0xFFE2E8F0)))];
    }
    return _bandColors.entries
        .where((e) => (counts[e.key] ?? 0) > 0)
        .map((e) {
      final pct = (counts[e.key] ?? 0) / total;
      return Flexible(
        flex: (pct * 100).round(),
        child: Container(color: e.value),
      );
    }).toList();
  }
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
        vsync: this, duration: const Duration(milliseconds: 1400))
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
        width: 9,
        height: 9,
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
