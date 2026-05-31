import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/colors.dart';
import '../../../models/forecast_day_model.dart';
import '../../../models/city_overview_model.dart';
import '../../../shared/providers/city_provider.dart';
import '../../../shared/widgets/hg_app_bar.dart';
import '../../../shared/widgets/hg_error_card.dart';
import '../../../shared/widgets/hg_skeleton.dart';
import '../../../shared/widgets/risk_pill.dart';

IconData _wxIcon(double? prcp, double? cloud) {
  if ((prcp ?? 0) > 20) return Icons.thunderstorm_outlined;
  if ((prcp ?? 0) > 2) return Icons.grain_outlined;
  if ((cloud ?? 0) > 60) return Icons.cloud_outlined;
  return Icons.wb_sunny_outlined;
}

String _conditionLabel(String levelKey, int? chanceRain, int? eventProb) {
  if (levelKey == 'severe') return 'High flood risk';
  if (levelKey == 'warning') return 'Heavy rain';
  if (levelKey == 'watch') return 'Light rain';
  if ((chanceRain ?? 0) > 40) return 'Mostly cloudy';
  return 'Clear';
}

class ForecastScreen extends ConsumerWidget {
  const ForecastScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final slug = ref.watch(currentCitySlugProvider);
    final forecastAsync = ref.watch(forecastProvider(slug));
    final overviewAsync = ref.watch(overviewProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;

    return Scaffold(
      backgroundColor: bg,
      appBar: HGAppBar(
        eyebrow: 'Forecast',
        title: slug.replaceAll('_', ' ').split(' ')
            .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
            .join(' '),
        trailing: IconButton(
          icon: const Icon(Icons.share_outlined),
          onPressed: () => ScaffoldMessenger.of(context)
              .showSnackBar(const SnackBar(content: Text('Sharing — coming soon'))),
          color: isDark ? HGColors.textDark : HGColors.textLight,
        ),
      ),
      body: forecastAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: HGErrorCard(
              message: e.toString(),
              onRetry: () => ref.invalidate(forecastProvider(slug)),
            ),
          ),
        ),
        data: (forecast) => SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _PrecipHeroCard(forecast: forecast),
              const SizedBox(height: 16),
              _DailyOutlookSection(forecast: forecast),
              const SizedBox(height: 16),
              overviewAsync.when(
                loading: () => const HGSkeleton(),
                error: (_, __) => const SizedBox.shrink(),
                data: (overview) =>
                    _CityCompareSection(overview: overview, currentSlug: slug),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );
  }
}

// ─── Precipitation hero card ──────────────────────────────────────────────────

class _PrecipHeroCard extends StatelessWidget {
  final List<ForecastDayModel> forecast;
  const _PrecipHeroCard({required this.forecast});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    final days = forecast.take(7).toList();
    final maxPrecp =
        days.fold(0.0, (m, d) => (d.prcp ?? 0) > m ? (d.prcp ?? 0) : m);
    final today = days.isNotEmpty ? days.first : null;

    final barGroups = <BarChartGroupData>[];
    for (var i = 0; i < days.length; i++) {
      final d = days[i];
      final val = d.prcp ?? 0;
      barGroups.add(BarChartGroupData(
        x: i,
        barRods: [
          BarChartRodData(
            toY: val,
            color: i == 0
                ? HGColors.forScenario(d.levelKey)
                : HGColors.blue.withValues(alpha: 0.7),
            width: 20,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(5)),
          ),
        ],
      ));
    }

    return Container(
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
                  Text('7-day rainfall outlook',
                      style: TextStyle(
                          fontSize: 11,
                          color: muted,
                          fontWeight: FontWeight.w500)),
                  Text(
                    today?.prcp != null
                        ? 'Today: ${today!.prcp!.toStringAsFixed(1)} mm'
                        : 'Rainfall forecast',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: textColor),
                  ),
                ],
              ),
              const Spacer(),
              if (today != null)
                RiskPill(
                    scenario: today.levelKey,
                    label: today.riskBand),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 140,
            child: BarChart(
              BarChartData(
                maxY: maxPrecp < 1 ? 10 : maxPrecp * 1.3,
                barGroups: barGroups,
                gridData: FlGridData(
                  drawHorizontalLine: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) => FlLine(
                    color: (isDark ? HGColors.lineDark : HGColors.lineLight)
                        .withValues(alpha: 0.5),
                    strokeWidth: 1,
                  ),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  leftTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (val, meta) {
                        final i = val.toInt();
                        if (i < 0 || i >= days.length) {
                          return const SizedBox.shrink();
                        }
                        final label =
                            i == 0 ? 'Today' : days[i].dayName;
                        return Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(label,
                              style: TextStyle(
                                  fontSize: 9,
                                  fontWeight: FontWeight.w500,
                                  color: muted)),
                        );
                      },
                      reservedSize: 22,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _LegendDot(
                  color: HGColors.forScenario(
                      today?.levelKey ?? 'safe'),
                  label: 'Today'),
              const SizedBox(width: 12),
              _LegendDot(
                  color: HGColors.blue.withValues(alpha: 0.7),
                  label: 'Other days'),
            ],
          ),
        ],
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    return Row(
      children: [
        Container(
            width: 10,
            height: 10,
            decoration:
                BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 5),
        Text(label, style: TextStyle(fontSize: 11, color: muted)),
      ],
    );
  }
}

// ─── Daily outlook section ────────────────────────────────────────────────────

class _DailyOutlookSection extends StatelessWidget {
  final List<ForecastDayModel> forecast;
  const _DailyOutlookSection({required this.forecast});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('7-day outlook',
            style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: textColor)),
        const SizedBox(height: 10),
        ...forecast
            .take(7)
            .toList()
            .asMap()
            .entries
            .map((e) =>
                _ForecastDayRow(day: e.value, isToday: e.key == 0)),
      ],
    );
  }
}

class _ForecastDayRow extends StatelessWidget {
  final ForecastDayModel day;
  final bool isToday;
  const _ForecastDayRow({required this.day, required this.isToday});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final color = HGColors.forScenario(day.levelKey);
    final condition =
        _conditionLabel(day.levelKey, day.chanceRain, day.eventProb);
    final probText = day.eventProb != null
        ? '${day.eventProb}% flood probability'
        : day.chanceRain != null
            ? '${day.chanceRain}% chance of rain'
            : '';

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
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(isToday ? 'Today' : day.dayName,
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: isToday ? HGColors.blue : textColor)),
              Text(day.dateStr,
                  style: TextStyle(fontSize: 11, color: muted)),
            ],
          ),
          const SizedBox(width: 12),
          Icon(_wxIcon(day.prcp, null), size: 26, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(condition,
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: textColor)),
                if (probText.isNotEmpty)
                  Text(probText,
                      style: TextStyle(fontSize: 11, color: muted)),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                day.prcp != null
                    ? '${day.prcp!.toStringAsFixed(1)} mm'
                    : '—',
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: color),
              ),
              if (day.maxTemp != null)
                Text(
                  '${day.maxTemp!.toStringAsFixed(0)}° / ${day.minTemp?.toStringAsFixed(0) ?? '—'}°',
                  style: TextStyle(fontSize: 11, color: muted),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─── City compare section ─────────────────────────────────────────────────────

class _CityCompareSection extends StatelessWidget {
  final List<CityOverviewModel> overview;
  final String currentSlug;
  const _CityCompareSection(
      {required this.overview, required this.currentSlug});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    final sorted = [...overview]..sort((a, b) {
        if (a.slug == currentSlug) return -1;
        if (b.slug == currentSlug) return 1;
        return b.hriScore.compareTo(a.hriScore);
      });

    return Container(
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
          Text('Compare with other cities',
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: textColor)),
          const SizedBox(height: 12),
          ...sorted.map((city) {
            final isCurrent = city.slug == currentSlug;
            final barFrac = city.hriScore / 100.0;
            final color = HGColors.forScenario(city.levelKey);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  SizedBox(
                    width: 100,
                    child: Text(
                      isCurrent ? '${city.name} (you)' : city.name,
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: isCurrent
                              ? FontWeight.w700
                              : FontWeight.w400,
                          color: isCurrent ? HGColors.blue : textColor),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: barFrac,
                        minHeight: 8,
                        backgroundColor: isDark
                            ? const Color(0xFF1E2535)
                            : const Color(0xFFECEFF5),
                        valueColor: AlwaysStoppedAnimation<Color>(color),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('${city.hriScore}',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: color)),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}
