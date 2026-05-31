import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/colors.dart';
import '../../../models/alert_item_model.dart';
import '../../../shared/providers/city_provider.dart';
import '../../../shared/providers/ws_provider.dart';
import '../../../shared/widgets/hg_app_bar.dart';
import '../../../shared/widgets/hg_skeleton.dart';
import '../../../shared/widgets/risk_pill.dart';
import '../../../shared/widgets/severity_ladder.dart';

class AlertsScreen extends ConsumerStatefulWidget {
  const AlertsScreen({super.key});

  @override
  ConsumerState<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends ConsumerState<AlertsScreen> {
  late StreamSubscription<Map<String, dynamic>> _wsSub;

  @override
  void initState() {
    super.initState();
    _wsSub = WsService.instance.anomaliesStream.listen((data) {
      final slug = ref.read(currentCitySlugProvider);
      final item = AlertItemModel.fromJson(data);
      if (item.kind != 'monitor' || data['is_alert'] == true) {
        ref.read(alertsProvider(slug).notifier).prepend(item);
      }
    });
  }

  @override
  void dispose() {
    _wsSub.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final slug = ref.watch(currentCitySlugProvider);
    final alerts = ref.watch(alertsProvider(slug));
    final riskAsync = ref.watch(cityRiskProvider(slug));
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;

    return riskAsync.when(
      loading: () => Scaffold(
        backgroundColor: bg,
        body: const Center(child: HGSkeleton()),
      ),
      error: (_, __) => Scaffold(
        backgroundColor: bg,
        appBar: HGAppBar(
          eyebrow: 'Alert log',
          title: 'Alerts',
          trailing: IconButton(
            icon: const Icon(Icons.filter_list_outlined),
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Filter — coming soon'))),
            color: isDark ? HGColors.textDark : HGColors.textLight,
          ),
        ),
        body: const Center(child: Text('Could not load risk data')),
      ),
      data: (risk) {
        final tierMap = {1: 'NORMAL', 2: 'ADVISORY', 4: 'ALERT'};
        final tierLabel = tierMap[risk.alertTier] ??
            risk.alertTierLabel;

        return Scaffold(
          backgroundColor: bg,
          appBar: HGAppBar(
            eyebrow: 'Tier ${risk.alertTier} · $tierLabel',
            title: risk.city,
            trailing: IconButton(
              icon: const Icon(Icons.filter_list_outlined),
              onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Filter — coming soon'))),
              color: isDark ? HGColors.textDark : HGColors.textLight,
            ),
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Evacuation banner
                if (risk.levelKey == 'severe') _EvacBanner(),

                // Current alert level
                _AlertLevelSection(
                    scenario: risk.levelKey,
                    tier: risk.alertTier,
                    tierLabel: tierLabel),
                const SizedBox(height: 16),

                // Alerts list header
                _AlertsListHeader(count: alerts.length),
                const SizedBox(height: 10),

                // Alert cards
                if (alerts.isEmpty)
                  _EmptyAlertsCard()
                else
                  ...alerts.asMap().entries.map((e) =>
                      _AlertCard(item: e.value, isFirst: e.key == 0)),

                // Alert history
                if (alerts.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  _AlertHistoryCard(alerts: alerts),
                ],
                const SizedBox(height: 12),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ─── Evacuation banner ────────────────────────────────────────────────────────

class _EvacBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: HGColors.severeSoft,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
              color: HGColors.severe.withValues(alpha: 0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                      color: HGColors.severe, shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
                const Text('Evacuation advisory',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: HGColors.severe)),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'High probability of severe flooding. Consider moving to higher ground.',
              style: TextStyle(
                  fontSize: 13,
                  color: Color(0xFFB91C1C)),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: () {},
                    style: ElevatedButton.styleFrom(
                        backgroundColor: HGColors.severe,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10))),
                    child: const Text('Evacuation routes'),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () {},
                  style: OutlinedButton.styleFrom(
                      foregroundColor: HGColors.severe,
                      side: const BorderSide(color: HGColors.severe),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10))),
                  child: const Text("I'm safe"),
                ),
              ],
            ),
          ],
        ),
      );
}

// ─── Alert level section ──────────────────────────────────────────────────────

class _AlertLevelSection extends StatelessWidget {
  final String scenario;
  final int tier;
  final String tierLabel;
  const _AlertLevelSection(
      {required this.scenario,
      required this.tier,
      required this.tierLabel});

  String get _tierDescription => switch (tierLabel) {
        'ALERT' =>
          'Active alert — push notification issued. Take protective action.',
        'ADVISORY' =>
          'Advisory active — elevated risk detected. Stay informed.',
        _ => 'Normal conditions — monitoring is active.',
      };

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

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
          Text('Current alert level',
              style: TextStyle(
                  fontSize: 11,
                  color: muted,
                  fontWeight: FontWeight.w500)),
          const SizedBox(height: 10),
          SeverityLadder(currentScenario: scenario),
          const SizedBox(height: 12),
          Text(_tierDescription,
              style: TextStyle(fontSize: 13, color: textColor)),
        ],
      ),
    );
  }
}

// ─── Alerts list header ───────────────────────────────────────────────────────

class _AlertsListHeader extends StatelessWidget {
  final int count;
  const _AlertsListHeader({required this.count});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Row(
      children: [
        Text('$count ${count == 1 ? 'alert' : 'alerts'} in log',
            style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: textColor)),
        const Spacer(),
        GestureDetector(
          onTap: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Filter — coming soon'))),
          child: Text('Filter →',
              style: TextStyle(fontSize: 13, color: muted)),
        ),
      ],
    );
  }
}

// ─── Empty alerts card ────────────────────────────────────────────────────────

class _EmptyAlertsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          Icon(Icons.notifications_none_outlined, size: 40, color: muted),
          const SizedBox(height: 12),
          Text('No alerts recorded',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: muted)),
          const SizedBox(height: 4),
          Text('Alerts will appear here as conditions change.',
              style: TextStyle(fontSize: 12, color: muted),
              textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

// ─── Alert card ───────────────────────────────────────────────────────────────

class _AlertCard extends StatelessWidget {
  final AlertItemModel item;
  final bool isFirst;
  const _AlertCard({required this.item, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final color = HGColors.forScenario(item.kind);
    final showDrivers = isFirst &&
        (item.kind == 'warning' || item.kind == 'severe') &&
        item.drivers.isNotEmpty;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Left stripe
          Container(
            width: 4,
            height: null,
            decoration: BoxDecoration(
              color: color,
              borderRadius: const BorderRadius.horizontal(
                  left: Radius.circular(14)),
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Title + time
                  Row(
                    children: [
                      Expanded(
                        child: Text(item.title,
                            style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: textColor)),
                      ),
                      Text(item.relativeTime,
                          style:
                              TextStyle(fontSize: 11, color: muted)),
                    ],
                  ),
                  const SizedBox(height: 6),

                  // Risk pill + source
                  Row(
                    children: [
                      RiskPill(
                          scenario: item.kind,
                          label: item.tierLabel),
                      const SizedBox(width: 8),
                      Text(item.source,
                          style: TextStyle(
                              fontSize: 11, color: muted)),
                    ],
                  ),
                  const SizedBox(height: 6),

                  // Description
                  Text(item.description,
                      style:
                          TextStyle(fontSize: 12, color: muted)),

                  // Inline SHAP drivers (first alert card only)
                  if (showDrivers) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: HGColors.softForScenario(item.kind,
                            dark: isDark),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Top contributing factors',
                              style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: color)),
                          const SizedBox(height: 6),
                          ...item.drivers.take(3).map((d) => Padding(
                                padding:
                                    const EdgeInsets.only(bottom: 4),
                                child: Row(
                                  children: [
                                    Icon(
                                      d.direction == 'up'
                                          ? Icons.arrow_upward_rounded
                                          : Icons.arrow_downward_rounded,
                                      size: 12,
                                      color: d.direction == 'up'
                                          ? color
                                          : HGColors.safe,
                                    ),
                                    const SizedBox(width: 4),
                                    Expanded(
                                      child: Text(d.plain,
                                          style: TextStyle(
                                              fontSize: 11,
                                              color: textColor)),
                                    ),
                                  ],
                                ),
                              )),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 10),

                  // Action buttons
                  Row(
                    children: [
                      OutlinedButton(
                        onPressed: () =>
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text(
                                        'View on map — coming soon'))),
                        style: OutlinedButton.styleFrom(
                            foregroundColor: color,
                            side: BorderSide(
                                color: color.withValues(alpha: 0.4)),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 6),
                            shape: RoundedRectangleBorder(
                                borderRadius:
                                    BorderRadius.circular(8))),
                        child: const Text('View on map',
                            style: TextStyle(fontSize: 12)),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton(
                        onPressed: () =>
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text(
                                        'Sharing — coming soon'))),
                        style: OutlinedButton.styleFrom(
                            foregroundColor: muted,
                            side: BorderSide(
                                color: muted.withValues(alpha: 0.3)),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 6),
                            shape: RoundedRectangleBorder(
                                borderRadius:
                                    BorderRadius.circular(8))),
                        child: const Text('Share',
                            style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Alert history card ───────────────────────────────────────────────────────

class _AlertHistoryCard extends StatelessWidget {
  final List<AlertItemModel> alerts;
  const _AlertHistoryCard({required this.alerts});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    final last7 = alerts.take(7).map((a) => a.hriScore.toDouble()).toList();
    final maxH =
        last7.isEmpty ? 10.0 : last7.reduce((a, b) => a > b ? a : b);

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
              Text('Alert history',
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: textColor)),
              const Spacer(),
              Text('Last ${alerts.length} events',
                  style: TextStyle(fontSize: 12, color: muted)),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 50,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: last7.map((h) {
                final frac = maxH > 0 ? h / maxH : 0.0;
                final kind = h >= 50 ? 'severe' : h >= 25 ? 'warning' : 'safe';
                return Expanded(
                  child: Container(
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    height: (frac * 50).clamp(4, 50),
                    decoration: BoxDecoration(
                      color: HGColors.forScenario(kind),
                      borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(3)),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}
