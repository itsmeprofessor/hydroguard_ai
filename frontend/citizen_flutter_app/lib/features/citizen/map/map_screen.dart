import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';
import '../../../core/theme/colors.dart';
import '../../../shared/providers/city_provider.dart';

const _cityCoords = {
  'islamabad':  LatLng(33.6844, 73.0479),
  'rawalpindi': LatLng(33.5651, 73.0169),
  'lahore':     LatLng(31.5204, 74.3587),
  'karachi':    LatLng(24.8607, 67.0011),
  'peshawar':   LatLng(34.0151, 71.5249),
  'quetta':     LatLng(30.1798, 66.9750),
  'gilgit':     LatLng(35.9022, 74.3085),
};

class CitizenMapScreen extends ConsumerWidget {
  const CitizenMapScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final slug = ref.watch(currentCitySlugProvider);
    final riskAsync = ref.watch(cityRiskProvider(slug));
    final cityCoord = _cityCoords[slug];
    final center = cityCoord ?? const LatLng(33.6844, 73.0479);

    final levelKey = riskAsync.valueOrNull?.levelKey ?? 'safe';

    // Shelter POIs at offsets from city center
    final shelterLocs = [
      LatLng(center.latitude + 0.01, center.longitude + 0.01),
      LatLng(center.latitude - 0.01, center.longitude + 0.015),
      LatLng(center.latitude + 0.008, center.longitude - 0.012),
    ];

    return Scaffold(
      body: Stack(
        children: [
          // ── Map ──────────────────────────────────────────────────────
          FlutterMap(
            options: MapOptions(
              initialCenter: center,
              initialZoom: 12,
            ),
            children: [
              TileLayer(
                urlTemplate:
                    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName:
                    'com.hydroguard.citizen_flutter_app',
              ),
              MarkerLayer(
                markers: [
                  // City marker
                  Marker(
                    point: center,
                    width: 60,
                    height: 60,
                    child: _CityMarker(levelKey: levelKey),
                  ),
                  // Shelter POIs
                  ...shelterLocs.map((loc) => Marker(
                        point: loc,
                        width: 32,
                        height: 32,
                        child: Container(
                          decoration: BoxDecoration(
                            color: HGColors.safe,
                            shape: BoxShape.circle,
                            border: Border.all(
                                color: Colors.white, width: 2),
                          ),
                          child: const Icon(Icons.local_hospital,
                              color: Colors.white, size: 14),
                        ),
                      )),
                ],
              ),
            ],
          ),

          // ── Safe area top ─────────────────────────────────────────────
          const Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SizedBox(height: 50),
          ),

          // ── Demo disclaimer pill ──────────────────────────────────────
          Positioned(
            top: 60,
            left: 0,
            right: 0,
            child: Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.55),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const Text(
                      'Tap any pin to see safety point details.',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 11,
                          fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
              ),
            ),
          ),

          // ── Live status pill (top-left) ───────────────────────────────
          Positioned(
            top: 100,
            left: 16,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.85),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                        color: Colors.white.withValues(alpha: 0.6)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: HGColors.forScenario(levelKey),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        riskAsync.valueOrNull?.city ??
                            slug.replaceAll('_', ' '),
                        style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: HGColors.textLight),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        riskAsync.valueOrNull?.level ?? 'Safe',
                        style: TextStyle(
                            fontSize: 12,
                            color: HGColors.forScenario(levelKey)),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // ── Layer switcher (top-right) ────────────────────────────────
          Positioned(
            top: 100,
            right: 16,
            child: _LayerSwitcher(),
          ),

          // ── Report button (right, floating) ───────────────────────────
          Positioned(
            right: 16,
            bottom: 320,
            child: FloatingActionButton.small(
              heroTag: 'report_btn',
              backgroundColor: HGColors.warning,
              onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content: Text('Report submitted — coming soon'))),
              child: const Icon(Icons.flag_outlined, color: Colors.white),
            ),
          ),

          // ── Bottom sheet ───────────────────────────────────────────────
          DraggableScrollableSheet(
            initialChildSize: 0.30,
            minChildSize: 0.25,
            maxChildSize: 0.55,
            builder: (ctx, ctrl) => _BottomSheet(controller: ctrl),
          ),
        ],
      ),
    );
  }
}

// ─── City marker (pulsing) ────────────────────────────────────────────────────

class _CityMarker extends StatefulWidget {
  final String levelKey;
  const _CityMarker({required this.levelKey});

  @override
  State<_CityMarker> createState() => _CityMarkerState();
}

class _CityMarkerState extends State<_CityMarker>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(seconds: 2))
      ..repeat();
    _pulse = Tween<double>(begin: 0.6, end: 1.0).animate(
        CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = HGColors.forScenario(widget.levelKey);
    return AnimatedBuilder(
      animation: _pulse,
      builder: (_, __) => Stack(
        alignment: Alignment.center,
        children: [
          // Pulse ring
          Container(
            width: 60 * _pulse.value,
            height: 60 * _pulse.value,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color
                  .withValues(alpha: (1 - _pulse.value) * 0.4),
            ),
          ),
          // Core
          Container(
            width: 24,
            height: 24,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              border:
                  Border.all(color: Colors.white, width: 3),
              boxShadow: [
                BoxShadow(
                    color: color.withValues(alpha: 0.4),
                    blurRadius: 8,
                    spreadRadius: 2),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Layer switcher ───────────────────────────────────────────────────────────

class _LayerSwitcher extends StatefulWidget {
  @override
  State<_LayerSwitcher> createState() => _LayerSwitcherState();
}

class _LayerSwitcherState extends State<_LayerSwitcher> {
  final _layers = ['Radar', 'Sensors', 'Shelters', 'Routes'];
  int _active = 2;

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.9),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white.withValues(alpha: 0.6)),
          boxShadow: [
            BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 8),
          ],
        ),
        child: Column(
          children: _layers.asMap().entries.map((e) {
            final isActive = e.key == _active;
            return GestureDetector(
              onTap: () => setState(() => _active = e.key),
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: isActive
                      ? HGColors.blue.withValues(alpha: 0.1)
                      : Colors.transparent,
                  borderRadius: e.key == 0
                      ? const BorderRadius.vertical(
                          top: Radius.circular(12))
                      : e.key == _layers.length - 1
                          ? const BorderRadius.vertical(
                              bottom: Radius.circular(12))
                          : BorderRadius.zero,
                ),
                child: Text(
                  e.value,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: isActive
                        ? HGColors.blue
                        : HGColors.mutedLight,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      );
}

// ─── Bottom sheet ─────────────────────────────────────────────────────────────

class _BottomSheet extends StatelessWidget {
  final ScrollController controller;
  const _BottomSheet({required this.controller});

  @override
  Widget build(BuildContext context) {
    const pois = [
      (
        ic: Icons.shield_outlined,
        color: HGColors.safe,
        name: 'Nearest evacuation shelter',
        desc: 'Capacity 600 · Open · Example location',
        action: 'Get directions',
      ),
      (
        ic: Icons.local_hospital_outlined,
        color: HGColors.blue,
        name: 'Closest emergency hospital',
        desc: '24/7 trauma + flood response',
        action: 'Get directions',
      ),
      (
        ic: Icons.phone_outlined,
        color: HGColors.violet,
        name: 'Rescue 1122 station',
        desc: 'Boats · medics · 24/7',
        action: 'Call',
      ),
    ];

    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).brightness == Brightness.dark
            ? HGColors.cardDark
            : HGColors.cardLight,
        borderRadius:
            const BorderRadius.vertical(top: Radius.circular(20)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.12),
              blurRadius: 16,
              offset: const Offset(0, -4)),
        ],
      ),
      child: ListView(
        controller: controller,
        padding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        children: [
          // Grab handle
          Center(
            child: Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(
                color: Colors.grey.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),

          // Header
          Row(
            children: [
              const Text(
                'Safety points',
                style: TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: HGColors.watchSoft,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text('Demo',
                    style: TextStyle(
                        fontSize: 10,
                        color: HGColors.watch,
                        fontWeight: FontWeight.w600)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Example locations — actual GIS integration required',
            style: TextStyle(fontSize: 11, color: HGColors.mutedLight),
          ),
          const SizedBox(height: 12),

          // POI rows
          ...pois.map(
            (poi) => Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Theme.of(context).brightness == Brightness.dark
                    ? const Color(0xFF1A2030)
                    : HGColors.bgLight,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: poi.color.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                    ),
                    child:
                        Icon(poi.ic, color: poi.color, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(poi.name,
                            style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600)),
                        Text(poi.desc,
                            style: const TextStyle(
                                fontSize: 11,
                                color: HGColors.mutedLight)),
                      ],
                    ),
                  ),
                  GestureDetector(
                    onTap: () => ScaffoldMessenger.of(context)
                        .showSnackBar(SnackBar(
                            content: Text(
                                '${poi.action} — coming soon'))),
                    child: Text(poi.action,
                        style: const TextStyle(
                            fontSize: 12,
                            color: HGColors.blue,
                            fontWeight: FontWeight.w600)),
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
