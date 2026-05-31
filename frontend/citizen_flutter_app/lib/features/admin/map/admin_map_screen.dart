import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../models/city_overview_model.dart';
import '../../../shared/providers/prefs_provider.dart';
import '../../../shared/providers/admin_provider.dart';
import '../../../shared/widgets/risk_pill.dart';

const _cityCoords = {
  'islamabad':  LatLng(33.6844, 73.0479),
  'rawalpindi': LatLng(33.5651, 73.0169),
  'lahore':     LatLng(31.5204, 74.3587),
  'karachi':    LatLng(24.8607, 67.0011),
  'peshawar':   LatLng(34.0151, 71.5249),
  'quetta':     LatLng(30.1798, 66.9750),
  'gilgit':     LatLng(35.9022, 74.3085),
};

const _cityCodes = {
  'islamabad':  'ISL',
  'karachi':    'KAR',
  'lahore':     'LAH',
  'peshawar':   'PES',
  'quetta':     'QUE',
  'gilgit':     'GIL',
  'rawalpindi': 'RWP',
};

// Shelter POIs (representative)
const _shelters = [
  (name: 'Flood Relief Camp Alpha', pos: LatLng(33.720, 73.060)),
  (name: 'NDMA Staging Area',       pos: LatLng(33.650, 73.010)),
  (name: 'Civil Hospital Shelter',  pos: LatLng(33.695, 73.050)),
];

class AdminMapScreen extends ConsumerStatefulWidget {
  const AdminMapScreen({super.key});

  @override
  ConsumerState<AdminMapScreen> createState() => _AdminMapScreenState();
}

class _AdminMapScreenState extends ConsumerState<AdminMapScreen> {
  bool _showShelters = true;
  bool _showHri      = true;
  CityOverviewModel? _selected;

  static String _toSlug(String city) => city
      .toLowerCase()
      .replaceAll(RegExp(r'\s+'), '_')
      .replaceAll(RegExp(r'[^a-z0-9_]'), '');

  @override
  Widget build(BuildContext context) {
    final isDark        = Theme.of(context).brightness == Brightness.dark;
    final prefs         = ref.watch(prefsProvider);
    final slug          = _toSlug(prefs.city);
    final overviewAsync = ref.watch(adminOverviewProvider);
    final cities        = overviewAsync.valueOrNull ?? [];

    final center = _cityCoords[slug] ?? const LatLng(30.3753, 69.3451);

    return Scaffold(
      backgroundColor: isDark ? HGColors.bgDark : HGColors.bgLight,
      body: SafeArea(
        child: Stack(
          children: [
            // Map
            FlutterMap(
              options: MapOptions(
                initialCenter: center,
                initialZoom: 6.5,
                onTap: (_, __) => setState(() => _selected = null),
              ),
              children: [
                TileLayer(
                  urlTemplate:
                      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.hydroguard.ai',
                ),
                // City markers
                if (_showHri)
                  MarkerLayer(
                    markers: cities.map((c) {
                      final pos = _cityCoords[c.slug];
                      if (pos == null) return null;
                      final color =
                          HGColors.forScenario(c.levelKey);
                      final code = _cityCodes[c.slug] ??
                          c.slug.substring(0, 3).toUpperCase();
                      return Marker(
                        point: pos,
                        width: 56,
                        height: 56,
                        child: GestureDetector(
                          onTap: () =>
                              setState(() => _selected = c),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 5, vertical: 2),
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.65),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  code,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 9,
                                      fontWeight: FontWeight.w700),
                                ),
                              ),
                              const SizedBox(height: 2),
                              Expanded(
                                child: _CityMarker(
                                    color: color, hri: c.hriScore),
                              ),
                            ],
                          ),
                        ),
                      );
                    }).whereType<Marker>().toList(),
                  ),
                // Fallback: coords-only markers for cities with no overview data
                if (_showHri && cities.isEmpty)
                  MarkerLayer(
                    markers: _cityCoords.entries.map((e) {
                      final code = _cityCodes[e.key] ??
                          e.key.substring(0, 3).toUpperCase();
                      return Marker(
                        point: e.value,
                        width: 56,
                        height: 56,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 5, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.65),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                code,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 9,
                                    fontWeight: FontWeight.w700),
                              ),
                            ),
                            const SizedBox(height: 2),
                            const Expanded(
                              child: _CityMarker(
                                  color: HGColors.monitor, hri: 0),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ),
                // Shelter markers
                if (_showShelters)
                  MarkerLayer(
                    markers: _shelters.map((s) {
                      return Marker(
                        point: s.pos,
                        width: 36,
                        height: 36,
                        child: GestureDetector(
                          onTap: () =>
                              ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content:
                                    Text('Shelter: ${s.name}')),
                          ),
                          child: Container(
                            decoration: const BoxDecoration(
                              color: Colors.white,
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                    color: Colors.black26,
                                    blurRadius: 4,
                                    offset: Offset(0, 2)),
                              ],
                            ),
                            child: const Icon(Icons.local_hospital_rounded,
                                size: 18, color: Colors.red),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
              ],
            ),

            // App bar overlay
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 8),
                color: isDark
                    ? HGColors.cardDark.withValues(alpha: 0.95)
                    : HGColors.cardLight.withValues(alpha: 0.95),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(
                          Icons.arrow_back_ios_new_rounded,
                          size: 20),
                      onPressed: () =>
                          context.go('/admin/dashboard'),
                      color: isDark
                          ? HGColors.mutedDark
                          : HGColors.mutedLight,
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Risk Map',
                              style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                  color: isDark
                                      ? HGColors.textDark
                                      : HGColors.textLight)),
                          Text(prefs.city,
                              style: TextStyle(
                                  fontSize: 11,
                                  color: isDark
                                      ? HGColors.mutedDark
                                      : HGColors.mutedLight)),
                        ],
                      ),
                    ),
                    // Layer switcher
                    Row(
                      children: [
                        _LayerChip(
                          label: 'HRI',
                          active: _showHri,
                          onTap: () => setState(
                              () => _showHri = !_showHri),
                        ),
                        const SizedBox(width: 6),
                        _LayerChip(
                          label: 'Shelters',
                          active: _showShelters,
                          onTap: () => setState(
                              () => _showShelters = !_showShelters),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            // Admin badge (top-right corner)
            const Positioned(
              top: 72,
              right: 12,
              child: _AdminBadge(),
            ),

            // Risk level legend (bottom-left)
            Positioned(
              bottom: 200,
              left: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(
                        color: Colors.black.withValues(alpha: 0.12),
                        blurRadius: 8),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('Risk level',
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF0B1220))),
                    const SizedBox(height: 6),
                    ...[
                      ('Safe',    const Color(0xFF22C55E)),
                      ('Watch',   const Color(0xFFEAB308)),
                      ('Warning', const Color(0xFFF97316)),
                      ('Severe',  const Color(0xFFEF4444)),
                    ].map((e) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                              width: 10,
                              height: 10,
                              decoration: BoxDecoration(
                                  color: e.$2,
                                  shape: BoxShape.circle)),
                          const SizedBox(width: 6),
                          Text(e.$1,
                              style: const TextStyle(
                                  fontSize: 11,
                                  color: Color(0xFF0B1220))),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ),

            // Selected city bottom sheet inline
            if (_selected != null)
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: _CityBottomSheet(
                  city: _selected!,
                  isDark: isDark,
                  onClose: () => setState(() => _selected = null),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ─── Widgets ──────────────────────────────────────────────────────────────────

class _CityMarker extends StatelessWidget {
  final Color color;
  final int hri;
  const _CityMarker({required this.color, required this.hri});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
              color: color.withValues(alpha: 0.5),
              blurRadius: 8,
              spreadRadius: 2),
        ],
      ),
      child: Center(
        child: Text('$hri',
            style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w800)),
      ),
    );
  }
}

class _AdminBadge extends StatelessWidget {
  const _AdminBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [HGColors.violet, HGColors.blue],
        ),
        borderRadius: BorderRadius.circular(999),
        boxShadow: const [
          BoxShadow(color: Colors.black26, blurRadius: 6,
              offset: Offset(0, 2)),
        ],
      ),
      child: const Text('Admin',
          style: TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.w700)),
    );
  }
}

class _LayerChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;
  const _LayerChip(
      {required this.label,
      required this.active,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: active
              ? HGColors.blue
              : (isDark
                  ? const Color(0xFF1E293B)
                  : const Color(0xFFE2E8F0)),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(label,
            style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: active
                    ? Colors.white
                    : (isDark
                        ? HGColors.mutedDark
                        : HGColors.mutedLight))),
      ),
    );
  }
}

class _CityBottomSheet extends StatelessWidget {
  final CityOverviewModel city;
  final bool isDark;
  final VoidCallback onClose;

  const _CityBottomSheet({
    required this.city,
    required this.isDark,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final color      = HGColors.forScenario(city.levelKey);
    final cardColor  = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor  = isDark ? HGColors.textDark : HGColors.textLight;
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Container(
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius:
            const BorderRadius.vertical(top: Radius.circular(20)),
        boxShadow: const [
          BoxShadow(
              color: Colors.black26,
              blurRadius: 16,
              offset: Offset(0, -4)),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(city.name,
                        style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: textColor)),
                    const SizedBox(height: 4),
                    Text(
                        city.isHeuristic
                            ? 'Heuristic mode · no trained model'
                            : '${city.alertTierLabel} · ML active',
                        style: TextStyle(
                            fontSize: 12, color: mutedColor)),
                  ],
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text('${city.hriScore}',
                      style: TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.w900,
                          fontFamily: 'monospace',
                          color: color)),
                  Text('/100',
                      style:
                          TextStyle(fontSize: 12, color: mutedColor)),
                ],
              ),
              const SizedBox(width: 10),
              IconButton(
                onPressed: onClose,
                icon: const Icon(Icons.close_rounded),
                color: mutedColor,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              RiskPill(scenario: city.levelKey, label: city.riskBand),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                    city.isHeuristic ? 'Heuristic' : 'ML model',
                    style: TextStyle(
                        fontSize: 10, color: mutedColor)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
