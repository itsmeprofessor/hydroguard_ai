import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../models/city_risk_model.dart';
import '../../../models/forecast_day_model.dart';
import '../../../shared/providers/auth_provider.dart';
import '../../../shared/providers/city_provider.dart';
import '../../../shared/providers/prefs_provider.dart';
import '../../../shared/widgets/hg_error_card.dart';
import '../../../shared/widgets/hg_skeleton.dart';
import '../../../shared/widgets/severity_ladder.dart';

// ─── Constants ────────────────────────────────────────────────────────────────

const _stability = {
  'stable':     (label: 'Stable prediction',      tone: 'safe'),
  'warming_up': (label: 'Model warming up',        tone: 'watch'),
  'degraded':   (label: 'Reduced confidence mode', tone: 'warning'),
};

const _tiers = {
  1: (label: 'NORMAL',   tone: 'safe'),
  2: (label: 'ADVISORY', tone: 'watch'),
  3: (label: 'ADVISORY', tone: 'watch'),
  4: (label: 'ALERT',    tone: 'warning'),
  5: (label: 'ALERT',    tone: 'severe'),
};

IconData _wxIcon(double? prcp, double? cloud) {
  if ((prcp ?? 0) > 20) return Icons.thunderstorm_outlined;
  if ((prcp ?? 0) > 2) return Icons.grain_outlined;
  if ((cloud ?? 0) > 60) return Icons.cloud_outlined;
  return Icons.wb_sunny_outlined;
}

// ─── HomeScreen ───────────────────────────────────────────────────────────────

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  @override
  Widget build(BuildContext context) {
    final slug = ref.watch(currentCitySlugProvider);
    final riskAsync = ref.watch(cityRiskProvider(slug));
    final forecastAsync = ref.watch(forecastProvider(slug));
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;

    return Scaffold(
      backgroundColor: bg,
      body: riskAsync.when(
        loading: () => const Center(child: HGSkeleton()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: HGErrorCard(
              message: e.toString(),
              onRetry: () => ref.invalidate(cityRiskProvider(slug)),
            ),
          ),
        ),
        data: (risk) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(cityRiskProvider(slug));
            ref.invalidate(forecastProvider(slug));
          },
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 50),
                _AppBarRow(risk: risk),
                _HeroSection(risk: risk),
                const SizedBox(height: 12),
                _LiveWeatherCard(risk: risk),
                const SizedBox(height: 12),
                if (risk.alertTier >= 3 && risk.drivers.isNotEmpty)
                  _ShapDriversPanel(risk: risk),
                if (risk.alertTier >= 2)
                  _EventLifecycleBar(risk: risk),
                if (risk.levelKey == 'watch' ||
                    risk.levelKey == 'warning' ||
                    risk.levelKey == 'severe')
                  _CtaBanner(risk: risk),
                if (risk.levelKey == 'warning' || risk.levelKey == 'severe')
                  _ImSafeButton(cityName: risk.city),
                const SizedBox(height: 12),
                forecastAsync.when(
                  loading: () => const SizedBox.shrink(),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (forecast) => _NextDaysSection(forecast: forecast),
                ),
                const SizedBox(height: 12),
                _WhatToDoSection(levelKey: risk.levelKey),
                const SizedBox(height: 12),
                _FamilySafetyGrid(),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ─── App bar row ──────────────────────────────────────────────────────────────

class _AppBarRow extends ConsumerWidget {
  final CityRiskModel risk;
  const _AppBarRow({required this.risk});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final uname = auth.user?.username ?? 'U';
    final initials =
        uname.substring(0, math.min(2, uname.length)).toUpperCase();
    final badge = risk.alertTier >= 2
        ? (risk.alertTier >= 4 ? '!' : '${risk.alertTier - 1}')
        : null;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          GestureDetector(
            onTap: () => context.push('/citizen/profile'),
            child: Container(
              width: 38,
              height: 38,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: [Color(0xFF6366F1), Color(0xFF06B6D4)],
                ),
              ),
              child: Center(
                child: Text(initials,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 13)),
              ),
            ),
          ),
          Expanded(
            child: Column(
              children: [
                Text('Good day ·',
                    style: TextStyle(fontSize: 11, color: muted)),
                GestureDetector(
                  onTap: () => _showCityPicker(context, ref),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(risk.city,
                          style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: textColor)),
                      const SizedBox(width: 4),
                      Icon(Icons.keyboard_arrow_down_rounded,
                          size: 18, color: muted),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Stack(
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_outlined),
                onPressed: () => context.go('/citizen/alerts'),
                color: isDark ? HGColors.textDark : HGColors.textLight,
              ),
              if (badge != null)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    padding: const EdgeInsets.all(3),
                    decoration: BoxDecoration(
                      color: HGColors.forScenario(
                          risk.alertTier >= 4 ? 'severe' : 'watch'),
                      shape: BoxShape.circle,
                    ),
                    child: Text(badge,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w700)),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─── City picker ──────────────────────────────────────────────────────────────

void _showCityPicker(BuildContext context, WidgetRef ref) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) {
      final isDark = Theme.of(ctx).brightness == Brightness.dark;
      final citiesAsync = ref.watch(citiesListProvider);
      final currentCity = ref.read(prefsProvider).city;
      return Container(
        height: MediaQuery.of(ctx).size.height * 0.6,
        decoration: BoxDecoration(
          color: isDark ? HGColors.cardDark : HGColors.cardLight,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              width: 36,
              height: 4,
              margin: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(
                color: isDark ? HGColors.lineDark : HGColors.lineLight,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Row(
                children: [
                  Text(
                    'Select City',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: isDark ? HGColors.textDark : HGColors.textLight,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(ctx),
                    color: isDark ? HGColors.mutedDark : HGColors.mutedLight,
                  ),
                ],
              ),
            ),
            Expanded(
              child: citiesAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (_, __) =>
                    const Center(child: Text('Could not load cities')),
                data: (cities) => ListView.builder(
                  itemCount: cities.length,
                  itemBuilder: (_, i) {
                    final name = cities[i]['name'] as String? ?? '';
                    final isSelected = name == currentCity;
                    return ListTile(
                      title: Text(
                        name,
                        style: TextStyle(
                          fontWeight: isSelected
                              ? FontWeight.w600
                              : FontWeight.w400,
                          color: isSelected
                              ? HGColors.blue
                              : (isDark
                                  ? HGColors.textDark
                                  : HGColors.textLight),
                        ),
                      ),
                      trailing: isSelected
                          ? const Icon(Icons.check_rounded,
                              color: HGColors.blue)
                          : null,
                      onTap: () {
                        ref.read(prefsProvider.notifier).setCity(name);
                        Navigator.pop(ctx);
                      },
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
}

// ─── Hero section ─────────────────────────────────────────────────────────────

class _HeroSection extends StatelessWidget {
  final CityRiskModel risk;
  const _HeroSection({required this.risk});

  String get _headline => switch (risk.levelKey) {
        'severe' => 'Cloudburst alert',
        'warning' => 'Warning issued',
        'watch' => 'Heads up',
        _ => 'All clear',
      };

  String _paragraph(String city, int hri) => switch (risk.levelKey) {
        'severe' =>
          'High probability of severe flooding in $city. HRI $hri/100 — act now.',
        'warning' =>
          'Elevated flash-flood risk in $city. HRI $hri/100 — avoid low-lying areas.',
        'watch' =>
          'Heavy rain expected in $city. HRI $hri/100 — monitor conditions.',
        _ =>
          '$city is in the clear. HRI $hri/100 — HydroGuard ML is watching.',
      };

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final tier = _tiers[risk.alertTier] ?? _tiers[1]!;
    final stab = _stability[risk.stability] ?? _stability['stable']!;
    final hri = risk.hriScore;
    final city = risk.city;

    final aiBody = risk.eventProbability > 0
        ? 'Calibrated flood probability ${(risk.eventProbability * 100).round()}% '
            '(${risk.inferenceMode == 'mc_dropout' ? 'MC Dropout' : 'deterministic'}). '
            'HRI $hri/100.${risk.degradedReason != null ? ' Note: ${risk.degradedReason}.' : ''}'
        : 'ML ensemble monitoring. HRI $hri/100 · '
            '${risk.modelVersion.isNotEmpty ? risk.modelVersion : 'v3.3'}.';

    final gradColors = isDark
        ? switch (risk.levelKey) {
            'severe'  => [const Color(0xFF3A1818), const Color(0xFF1A0808), HGColors.bgDark],
            'warning' => [const Color(0xFF2A1808), HGColors.bgDark],
            'watch'   => [const Color(0xFF2A2008), HGColors.bgDark],
            'monitor' => [const Color(0xFF0A2C33), HGColors.bgDark],
            _         => [const Color(0xFF0B2A3F), HGColors.bgDark],
          }
        : switch (risk.levelKey) {
            'severe'  => [const Color(0xFFFEE2E2), const Color(0xFFFECACA), const Color(0xFFF4F6FB)],
            'warning' => [const Color(0xFFFFEDD5), const Color(0xFFF4F6FB)],
            'watch'   => [const Color(0xFFFEF3C7), const Color(0xFFF4F6FB)],
            'monitor' => [const Color(0xFFCFFAFE), const Color(0xFFF4F6FB)],
            _         => [const Color(0xFFE0F2FE), const Color(0xFFF4F6FB)],
          };
    final stops = risk.levelKey == 'severe' ? [0.0, 0.4, 1.0] : [0.0, 1.0];

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: gradColors,
          stops: stops,
        ),
      ),
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Level label row
          Row(
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: HGColors.forScenario(risk.levelKey),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '${risk.level} level',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: HGColors.forScenario(risk.levelKey),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),

          // Chips row
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              _ScenarioChip(label: tier.label, tone: tier.tone),
              _ScenarioChip(label: stab.label, tone: stab.tone),
              if (risk.isHeuristic)
                _ScenarioChip(label: 'Heuristic estimate', tone: 'monitor'),
            ],
          ),
          const SizedBox(height: 14),

          // Headline
          Text(
            _headline,
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w800,
              color: isDark ? HGColors.textDark : HGColors.textLight,
            ),
          ),
          const SizedBox(height: 6),

          // Paragraph
          Text(
            _paragraph(city, hri),
            style: TextStyle(
                fontSize: 15,
                color: isDark ? HGColors.mutedDark : HGColors.mutedLight),
          ),
          const SizedBox(height: 16),

          // Severity ladder
          SeverityLadder(currentScenario: risk.levelKey),
          const SizedBox(height: 16),

          // Metrics row
          Row(
            children: [
              _MetricCol(
                label: 'Rainfall',
                value: risk.prcp != null
                    ? risk.prcp!.toStringAsFixed(1)
                    : '—',
                unit: 'mm/h',
              ),
              const _ColDivider(),
              _MetricCol(
                label: 'Temperature',
                value: risk.tavg != null
                    ? '${risk.tavg!.toStringAsFixed(0)}°'
                    : '—',
                unit: risk.humidity != null
                    ? '${risk.humidity!.toStringAsFixed(0)}% hum'
                    : '',
              ),
              const _ColDivider(),
              _MetricCol(
                label: 'HRI',
                value: '$hri',
                unit: '/100 · ±${(risk.uncertainty * 100).toStringAsFixed(0)}%',
              ),
            ],
          ),
          const SizedBox(height: 16),

          // AI confidence card
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: isDark
                  ? HGColors.cardDark.withValues(alpha: 0.9)
                  : Colors.white.withValues(alpha: 0.85),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                  color: isDark
                      ? HGColors.lineDark
                      : const Color(0x1A000000)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Text('✨', style: TextStyle(fontSize: 14)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'HydroGuard ML · model stability',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: isDark
                                ? HGColors.textDark
                                : HGColors.textLight),
                      ),
                    ),
                    Text(
                      '${risk.confidencePct}%',
                      style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: HGColors.blue),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(aiBody,
                    style: TextStyle(
                        fontSize: 11,
                        color: isDark
                            ? HGColors.mutedDark
                            : HGColors.mutedLight)),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: risk.confidencePct / 100,
                    backgroundColor: isDark
                        ? HGColors.blueSoftDark
                        : HGColors.blueSoft,
                    valueColor:
                        const AlwaysStoppedAnimation<Color>(HGColors.blue),
                    minHeight: 5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '${risk.confidencePct}% confidence · HRI ${risk.hriScore}/100 · v3.3',
                  style: TextStyle(
                    fontSize: 11,
                    color: isDark ? HGColors.mutedDark : HGColors.mutedLight,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ScenarioChip extends StatelessWidget {
  final String label;
  final String tone;
  const _ScenarioChip({required this.label, required this.tone});

  @override
  Widget build(BuildContext context) {
    final color = HGColors.forScenario(tone);
    final soft = HGColors.softForScenario(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: soft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }
}

class _MetricCol extends StatelessWidget {
  final String label;
  final String value;
  final String unit;
  const _MetricCol(
      {required this.label, required this.value, required this.unit});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final dim = isDark ? HGColors.dimDark : HGColors.dimLight;
    return Expanded(
      child: Column(
        children: [
          Text(label, style: TextStyle(fontSize: 10, color: dim)),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: textColor)),
          Text(unit, style: TextStyle(fontSize: 10, color: dim)),
        ],
      ),
    );
  }
}

class _ColDivider extends StatelessWidget {
  const _ColDivider();
  @override
  Widget build(BuildContext context) =>
      Container(width: 1, height: 40, color: const Color(0x1A000000));
}

// ─── Live weather card ────────────────────────────────────────────────────────

class _LiveWeatherCard extends StatelessWidget {
  final CityRiskModel risk;
  const _LiveWeatherCard({required this.risk});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Live weather',
                        style: TextStyle(
                            fontSize: 11,
                            color: muted,
                            fontWeight: FontWeight.w500)),
                    Text(risk.city,
                        style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: textColor)),
                  ],
                ),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: risk.isHeuristic
                        ? HGColors.watchSoft
                        : HGColors.blueSoft,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    risk.isHeuristic
                        ? 'Heuristic estimate'
                        : 'ML model active',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: risk.isHeuristic ? HGColors.watch : HGColors.blue,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Icon(
                  _wxIcon(risk.prcp, risk.cloudCover),
                  size: 48,
                  color: HGColors.forScenario(risk.levelKey),
                ),
                const SizedBox(width: 16),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      risk.tavg != null
                          ? '${risk.tavg!.toStringAsFixed(0)}°C'
                          : '—',
                      style: TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.w800,
                          color: textColor),
                    ),
                    Text(
                      risk.humidity != null
                          ? 'Humidity ${risk.humidity!.toStringAsFixed(0)}%'
                          : 'Weather data',
                      style: TextStyle(fontSize: 12, color: muted),
                    ),
                  ],
                ),
                const Spacer(),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      risk.prcp != null
                          ? '${risk.prcp!.toStringAsFixed(1)} mm'
                          : '—',
                      style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: HGColors.forScenario(risk.levelKey)),
                    ),
                    Text('rain / h',
                        style: TextStyle(fontSize: 11, color: muted)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                _WeatherStat(
                    label: 'Humidity',
                    value: risk.humidity != null
                        ? '${risk.humidity!.toStringAsFixed(0)}%'
                        : '—'),
                _WeatherStat(
                    label: 'Wind',
                    value: risk.wspd != null
                        ? '${risk.wspd!.toStringAsFixed(0)} km/h'
                        : '—'),
                _WeatherStat(
                    label: 'Pressure',
                    value: risk.pressure != null
                        ? '${risk.pressure!.toStringAsFixed(0)} hPa'
                        : '—'),
                _WeatherStat(
                    label: 'Cloud cover',
                    value: risk.cloudCover != null
                        ? '${risk.cloudCover!.toStringAsFixed(0)}%'
                        : '—'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _WeatherStat extends StatelessWidget {
  final String label;
  final String value;
  const _WeatherStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    return Expanded(
      child: Column(
        children: [
          Text(label, style: TextStyle(fontSize: 10, color: muted)),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: textColor)),
        ],
      ),
    );
  }
}

// ─── SHAP drivers panel ───────────────────────────────────────────────────────

class _ShapDriversPanel extends StatelessWidget {
  final CityRiskModel risk;
  const _ShapDriversPanel({required this.risk});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    final maxW = risk.drivers.isNotEmpty
        ? risk.drivers.map((d) => d.weight).reduce(math.max)
        : 1.0;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('✨', style: TextStyle(fontSize: 14)),
                const SizedBox(width: 6),
                Text('Why this alert?',
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: textColor)),
                const Spacer(),
                Text('Top drivers · ML',
                    style: TextStyle(fontSize: 11, color: muted)),
              ],
            ),
            const SizedBox(height: 12),
            ...risk.drivers.map((d) {
              final frac = maxW > 0 ? d.weight / maxW : 0.0;
              final upColor = HGColors.forScenario(risk.levelKey);
              const downColor = HGColors.safe;
              final arrowColor =
                  d.direction == 'up' ? upColor : downColor;
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          d.direction == 'up'
                              ? Icons.arrow_upward_rounded
                              : Icons.arrow_downward_rounded,
                          size: 14,
                          color: arrowColor,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(d.plain,
                              style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: textColor)),
                        ),
                        Text(d.tech,
                            style: TextStyle(fontSize: 11, color: muted)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: frac,
                        backgroundColor: isDark
                            ? const Color(0xFF1E2535)
                            : HGColors.bg2Light,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(arrowColor),
                        minHeight: 5,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

// ─── Event lifecycle bar ──────────────────────────────────────────────────────

class _EventLifecycleBar extends StatelessWidget {
  final CityRiskModel risk;
  const _EventLifecycleBar({required this.risk});

  static const _stages = [
    'monitoring', 'formation', 'escalation',
    'active', 'peak', 'stabilizing', 'recovery',
  ];
  static const _labels = [
    'Monitoring', 'Formation', 'Escalation',
    'Active', 'Peak risk', 'Stabilizing', 'Recovery',
  ];

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final curIdx = _stages.indexOf(risk.lifecycleStage);
    final stageColor = HGColors.forScenario(risk.levelKey);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('🕐', style: TextStyle(fontSize: 14)),
                const SizedBox(width: 6),
                Text('Event lifecycle',
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: textColor)),
              ],
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: List.generate(_stages.length, (i) {
                  // ignore: unused_local_variable
                  final isPast = i < curIdx;
                  final isCur = i == curIdx;
                  final isFuture = i > curIdx;
                  final dotColor = isFuture
                      ? muted.withValues(alpha: 0.3)
                      : stageColor;
                  return Padding(
                    padding: const EdgeInsets.only(right: 12),
                    child: Column(
                      children: [
                        Container(
                          width: isCur ? 16 : 10,
                          height: isCur ? 16 : 10,
                          decoration: BoxDecoration(
                            color: isFuture
                                ? Colors.transparent
                                : dotColor,
                            shape: BoxShape.circle,
                            border: Border.all(
                                color: dotColor, width: 2),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _labels[i],
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: isCur
                                ? FontWeight.w700
                                : FontWeight.w400,
                            color: isFuture ? muted : dotColor,
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── CTA banner ───────────────────────────────────────────────────────────────

class _CtaBanner extends StatelessWidget {
  final CityRiskModel risk;
  const _CtaBanner({required this.risk});

  @override
  Widget build(BuildContext context) {
    final ctas = {
      'watch': (
        tone: 'warning',
        title: 'Heavy rain advisory',
        body: 'Valid until 8 PM today',
        primary: 'Safety steps',
        secondary: 'Share',
      ),
      'warning': (
        tone: 'warning',
        title: 'Flash flood warning',
        body: 'Elevated risk — avoid low-lying areas',
        primary: 'View safety steps',
        secondary: 'Share alert',
      ),
      'severe': (
        tone: 'severe',
        title: 'EVACUATION ADVISED',
        body: 'High probability of severe flooding — consider evacuation',
        primary: 'Open evacuation route',
        secondary: "Mark I'm safe",
      ),
    };
    final cta = ctas[risk.levelKey];
    if (cta == null) return const SizedBox.shrink();

    final color = HGColors.forScenario(cta.tone);
    final soft = HGColors.softForScenario(cta.tone);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: soft,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration:
                      BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
                Text(cta.title,
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: color)),
              ],
            ),
            const SizedBox(height: 6),
            Text(cta.body,
                style: TextStyle(
                    fontSize: 13,
                    color: color.withValues(alpha: 0.8))),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: () => ScaffoldMessenger.of(context)
                        .showSnackBar(
                            SnackBar(content: Text(cta.primary))),
                    style: ElevatedButton.styleFrom(
                        backgroundColor: color,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10))),
                    child: Text(cta.primary,
                        style: const TextStyle(fontSize: 13)),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () => ScaffoldMessenger.of(context)
                      .showSnackBar(
                          SnackBar(content: Text(cta.secondary))),
                  style: OutlinedButton.styleFrom(
                      foregroundColor: color,
                      side: BorderSide(color: color),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10))),
                  child: Text(cta.secondary,
                      style: const TextStyle(fontSize: 13)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ─── I'm safe button ──────────────────────────────────────────────────────────

class _ImSafeButton extends StatelessWidget {
  final String cityName;
  const _ImSafeButton({required this.cityName});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        child: SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            icon: const Icon(Icons.shield_outlined),
            label: const Text("I'm safe — let my circle know"),
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Status shared — coming soon')),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: HGColors.safe,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14)),
            ),
          ),
        ),
      );
}

// ─── Next days section ────────────────────────────────────────────────────────

class _NextDaysSection extends StatelessWidget {
  final List<ForecastDayModel> forecast;
  const _NextDaysSection({required this.forecast});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final days = forecast.take(5).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Next days',
                  style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: textColor)),
              const Spacer(),
              GestureDetector(
                onTap: () => context.go('/citizen/forecast'),
                child: const Text('Forecast →',
                    style: TextStyle(fontSize: 13, color: HGColors.blue)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: days.isEmpty
                  ? [Text('No forecast data', style: TextStyle(color: muted))]
                  : days
                      .asMap()
                      .entries
                      .map((e) => _ForecastMiniCard(
                          day: e.value, isToday: e.key == 0))
                      .toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _ForecastMiniCard extends StatelessWidget {
  final ForecastDayModel day;
  final bool isToday;
  const _ForecastMiniCard({required this.day, required this.isToday});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final color = HGColors.forScenario(day.levelKey);

    return Container(
      width: 70,
      margin: const EdgeInsets.only(right: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Column(
        children: [
          Text(isToday ? 'Today' : day.dayName,
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: isToday ? HGColors.blue : textColor)),
          const SizedBox(height: 6),
          Icon(_wxIcon(day.prcp, null), size: 22, color: color),
          const SizedBox(height: 6),
          Text(
            day.prcp != null
                ? '${day.prcp!.toStringAsFixed(0)}mm'
                : '—',
            style:
                TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: muted),
          ),
        ],
      ),
    );
  }
}

// ─── What to do section ───────────────────────────────────────────────────────

class _WhatToDoSection extends StatelessWidget {
  final String levelKey;
  const _WhatToDoSection({required this.levelKey});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    final advice = <String, List<({IconData ic, String kind, String t, String b})>>{
      'safe': [
        (
          ic: Icons.info_outline,
          kind: 'safe',
          t: 'Background monitoring active',
          b: "HydroGuard ML is continuously inferring your city's risk in real time."
        ),
        (
          ic: Icons.shield_outlined,
          kind: 'safe',
          t: 'No flood risk detected',
          b: 'All clear across monitored weather parameters.'
        ),
      ],
      'monitor': [
        (
          ic: Icons.info_outline,
          kind: 'safe',
          t: 'Background monitoring active',
          b: "HydroGuard ML is continuously inferring your city's risk in real time."
        ),
        (
          ic: Icons.shield_outlined,
          kind: 'safe',
          t: 'Conditions are normal',
          b: 'All weather parameters are within normal range.'
        ),
      ],
      'watch': [
        (
          ic: Icons.water_outlined,
          kind: 'warning',
          t: 'Avoid low-lying streets and underpasses',
          b: 'Storm drains and culverts flood first.'
        ),
        (
          ic: Icons.directions_car_outlined,
          kind: 'warning',
          t: 'Drive carefully',
          b: 'Roads will be slippery. Reduce speed.'
        ),
        (
          ic: Icons.phone_outlined,
          kind: 'safe',
          t: 'Save Rescue 1122 to favorites',
          b: 'Tap to add the emergency hotline.'
        ),
      ],
      'warning': [
        (
          ic: Icons.stairs_outlined,
          kind: 'warning',
          t: 'Move belongings off the ground floor',
          b: 'Especially documents, electronics, and family photos.'
        ),
        (
          ic: Icons.family_restroom_outlined,
          kind: 'warning',
          t: 'Pick up children early',
          b: 'Schools may close. Roads will worsen.'
        ),
        (
          ic: Icons.directions_car_outlined,
          kind: 'severe',
          t: 'Do not drive through standing water',
          b: '30 cm of moving water can sweep a car.'
        ),
      ],
      'severe': [
        (
          ic: Icons.terrain_outlined,
          kind: 'severe',
          t: 'Move to higher ground now',
          b: 'Head to the nearest designated shelter immediately.'
        ),
        (
          ic: Icons.family_restroom_outlined,
          kind: 'severe',
          t: 'Check on family and elderly neighbors',
          b: 'Call now — phone networks may degrade.'
        ),
        (
          ic: Icons.phone_outlined,
          kind: 'severe',
          t: 'Call Rescue 1122',
          b: 'Free hotline · open 24/7 across Pakistan.'
        ),
      ],
    };

    final items = advice[levelKey] ?? advice['safe']!;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('What to do',
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: textColor)),
          const SizedBox(height: 10),
          ...items.map((item) => _AdviceCard(item: item)),
        ],
      ),
    );
  }
}

class _AdviceCard extends StatelessWidget {
  final ({IconData ic, String kind, String t, String b}) item;
  const _AdviceCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final color = HGColors.forScenario(item.kind);
    final soft = HGColors.softForScenario(item.kind, dark: isDark);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: soft, shape: BoxShape.circle),
            child: Icon(item.ic, size: 20, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.t,
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: textColor)),
                const SizedBox(height: 2),
                Text(item.b,
                    style: TextStyle(fontSize: 12, color: muted)),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: muted, size: 18),
        ],
      ),
    );
  }
}

// ─── Family safety grid ───────────────────────────────────────────────────────

class _FamilySafetyGrid extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    final actions = [
      (
        ic: Icons.check_circle_outline,
        color: HGColors.blue,
        label: 'Notify family',
        msg: 'Notify family — coming soon'
      ),
      (
        ic: Icons.backpack_outlined,
        color: HGColors.safe,
        label: 'Emergency kit',
        msg: 'Emergency kit checklist — coming soon'
      ),
      (
        ic: Icons.phone_in_talk_outlined,
        color: HGColors.violet,
        label: 'Call 1122',
        msg: 'Calling Rescue 1122 — dial 1122'
      ),
      (
        ic: Icons.flag_outlined,
        color: HGColors.warning,
        label: 'Report issue',
        msg: 'Report submitted — coming soon'
      ),
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Family safety',
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: textColor)),
          const SizedBox(height: 10),
          GridView.count(
            crossAxisCount: 4,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            children: actions
                .map((a) => _SafetyActionButton(action: a))
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _SafetyActionButton extends StatelessWidget {
  final ({IconData ic, Color color, String label, String msg}) action;
  const _SafetyActionButton({required this.action});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    return GestureDetector(
      onTap: () => ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(action.msg))),
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(action.ic, color: action.color, size: 24),
            const SizedBox(height: 6),
            Text(action.label,
                style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: textColor),
                textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
