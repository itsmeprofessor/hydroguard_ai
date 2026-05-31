import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/colors.dart';
import '../../../models/alert_item_model.dart';
import '../../../models/driver_model.dart';
import '../../../shared/providers/prefs_provider.dart';
import '../../../shared/providers/city_provider.dart';
import '../../../shared/providers/ws_provider.dart';
import '../../../shared/widgets/severity_ladder.dart';

class AdminAlertsScreen extends ConsumerStatefulWidget {
  const AdminAlertsScreen({super.key});

  @override
  ConsumerState<AdminAlertsScreen> createState() =>
      _AdminAlertsScreenState();
}

class _AdminAlertsScreenState extends ConsumerState<AdminAlertsScreen> {
  late String _slug;

  @override
  void initState() {
    super.initState();
    final city = ref.read(prefsProvider).city;
    _slug = _toSlug(city);
    _subscribeWs();
  }

  void _subscribeWs() {
    WsService.instance.anomaliesStream.listen((data) {
      if (!mounted) return;
      final item = AlertItemModel.fromJson(data);
      ref.read(alertsProvider(_slug).notifier).prepend(item);
    });
  }

  static String _toSlug(String city) => city
      .toLowerCase()
      .replaceAll(RegExp(r'\s+'), '_')
      .replaceAll(RegExp(r'[^a-z0-9_]'), '');

  @override
  Widget build(BuildContext context) {
    final isDark     = Theme.of(context).brightness == Brightness.dark;
    final prefs      = ref.watch(prefsProvider);
    _slug = _toSlug(prefs.city);
    final alerts     = ref.watch(alertsProvider(_slug));

    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Scaffold(
      backgroundColor: isDark ? HGColors.bgDark : HGColors.bgLight,
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
                  Text('Admin Alerts',
                      style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: textColor)),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: HGColors.violet.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const Text('ADMIN',
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: HGColors.violet)),
                  ),
                  const Spacer(),
                  Text(prefs.city,
                      style: TextStyle(fontSize: 13, color: mutedColor)),
                ],
              ),
            ),
            Expanded(
              child: alerts.isEmpty
                  ? _buildEmpty(isDark, mutedColor)
                  : RefreshIndicator(
                      onRefresh: () async {
                        ref.invalidate(alertsProvider(_slug));
                      },
                      child: ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding:
                            const EdgeInsets.fromLTRB(16, 12, 16, 24),
                        children: [
                          // Severity ladder from first alert
                          _SeverityCard(
                            alert: alerts.first,
                            isDark: isDark,
                            cardColor: cardColor,
                            textColor: textColor,
                            mutedColor: mutedColor,
                          ),
                          const SizedBox(height: 16),
                          // Feed header
                          Text('Alert feed',
                              style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: mutedColor,
                                  letterSpacing: 0.5)),
                          const SizedBox(height: 10),
                          // Alert cards
                          ...alerts.map((a) => Padding(
                                padding:
                                    const EdgeInsets.only(bottom: 10),
                                child: _AlertCard(
                                  alert: a,
                                  isDark: isDark,
                                  cardColor: cardColor,
                                  textColor: textColor,
                                  mutedColor: mutedColor,
                                  showShap: a == alerts.first,
                                ),
                              )),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty(bool isDark, Color mutedColor) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.notifications_none_rounded,
              size: 56,
              color: isDark ? HGColors.mutedDark : HGColors.mutedLight),
          const SizedBox(height: 12),
          Text('No alerts for this city yet',
              style: TextStyle(fontSize: 15, color: mutedColor)),
          const SizedBox(height: 6),
          Text('Background ML is monitoring conditions',
              style: TextStyle(fontSize: 12, color: mutedColor)),
        ],
      ),
    );
  }
}

// ─── Severity card ─────────────────────────────────────────────────────────────

class _SeverityCard extends StatelessWidget {
  final AlertItemModel alert;
  final bool isDark;
  final Color cardColor;
  final Color textColor;
  final Color mutedColor;

  const _SeverityCard({
    required this.alert,
    required this.isDark,
    required this.cardColor,
    required this.textColor,
    required this.mutedColor,
  });

  @override
  Widget build(BuildContext context) {
    final color = HGColors.forScenario(alert.kind);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? HGColors.lineDark : HGColors.lineLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.shield_rounded, size: 16, color: color),
              const SizedBox(width: 6),
              Text('Current severity level',
                  style:
                      TextStyle(fontSize: 12, color: mutedColor)),
            ],
          ),
          const SizedBox(height: 12),
          SeverityLadder(currentScenario: alert.kind),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('HRI ${alert.hriScore}/100',
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: color)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(alert.tierLabel,
                    style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: color)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─── Alert card ────────────────────────────────────────────────────────────────

class _AlertCard extends StatefulWidget {
  final AlertItemModel alert;
  final bool isDark;
  final Color cardColor;
  final Color textColor;
  final Color mutedColor;
  final bool showShap;

  const _AlertCard({
    required this.alert,
    required this.isDark,
    required this.cardColor,
    required this.textColor,
    required this.mutedColor,
    this.showShap = false,
  });

  @override
  State<_AlertCard> createState() => _AlertCardState();
}

class _AlertCardState extends State<_AlertCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final color = HGColors.forScenario(widget.alert.kind);
    return Container(
      decoration: BoxDecoration(
        color: widget.cardColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: widget.isDark
                ? HGColors.lineDark
                : HGColors.lineLight),
      ),
      child: Column(
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 4,
                    height: 44,
                    decoration: BoxDecoration(
                        color: color,
                        borderRadius: BorderRadius.circular(2)),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.alert.title,
                            style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: widget.textColor)),
                        const SizedBox(height: 4),
                        Text(widget.alert.description,
                            style: TextStyle(
                                fontSize: 12,
                                color: widget.mutedColor)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(widget.alert.relativeTime,
                          style: TextStyle(
                              fontSize: 11,
                              color: widget.mutedColor)),
                      const SizedBox(height: 4),
                      Icon(
                        _expanded
                            ? Icons.expand_less_rounded
                            : Icons.expand_more_rounded,
                        size: 18,
                        color: widget.mutedColor,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          if (_expanded && widget.alert.drivers.isNotEmpty) ...[
            Divider(
                height: 1,
                color: widget.isDark
                    ? HGColors.lineDark
                    : HGColors.lineLight),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('SHAP drivers',
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: widget.mutedColor,
                          letterSpacing: 0.4)),
                  const SizedBox(height: 8),
                  ...widget.alert.drivers
                      .map((d) => _DriverRow(
                            driver: d,
                            isDark: widget.isDark,
                            mutedColor: widget.mutedColor,
                          )),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _DriverRow extends StatelessWidget {
  final DriverModel driver;
  final bool isDark;
  final Color mutedColor;
  const _DriverRow(
      {required this.driver,
      required this.isDark,
      required this.mutedColor});

  @override
  Widget build(BuildContext context) {
    final isUp  = driver.direction == 'up';
    final color = isUp ? HGColors.severe : HGColors.safe;
    final maxW  = driver.weight.clamp(0.0, 1.0);

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Icon(
            isUp
                ? Icons.arrow_upward_rounded
                : Icons.arrow_downward_rounded,
            size: 13,
            color: color,
          ),
          const SizedBox(width: 6),
          Expanded(
            flex: 3,
            child: Text(driver.plain,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 12,
                    color: isDark
                        ? HGColors.textDark
                        : HGColors.textLight)),
          ),
          const SizedBox(width: 6),
          Expanded(
            flex: 2,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(2),
              child: Stack(
                children: [
                  Container(
                      height: 4,
                      color: isDark
                          ? const Color(0xFF1E293B)
                          : const Color(0xFFE2E8F0)),
                  FractionallySizedBox(
                    widthFactor: maxW,
                    child: Container(height: 4, color: color),
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
