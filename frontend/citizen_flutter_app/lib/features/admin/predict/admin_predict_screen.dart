import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme/colors.dart';
import '../../../repositories/admin_repository.dart';
import '../../../shared/providers/city_provider.dart';

class AdminPredictScreen extends ConsumerStatefulWidget {
  const AdminPredictScreen({super.key});
  @override
  ConsumerState<AdminPredictScreen> createState() => _AdminPredictScreenState();
}

class _AdminPredictScreenState extends ConsumerState<AdminPredictScreen> {
  final _formKey = GlobalKey<FormState>();
  final _repo    = AdminRepository();

  String? _selectedSlug;
  String? _selectedName;
  bool    _loading = false;
  String? _error;
  Map<String, dynamic>? _result;

  // Controllers for each weather parameter
  final _prcp     = TextEditingController(text: '0.0');
  final _humidity = TextEditingController(text: '60.0');
  final _pressure = TextEditingController(text: '1010.0');
  final _cloud    = TextEditingController(text: '30.0');
  final _tmax     = TextEditingController(text: '35.0');
  final _tmin     = TextEditingController(text: '20.0');
  final _tavg     = TextEditingController(text: '27.0');
  final _wspd     = TextEditingController(text: '10.0');

  @override
  void dispose() {
    for (final c in [_prcp, _humidity, _pressure, _cloud, _tmax, _tmin, _tavg, _wspd]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _runPrediction() async {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedSlug == null) {
      setState(() => _error = 'Please select a city.');
      return;
    }
    setState(() {
      _loading = true;
      _error   = null;
      _result  = null;
    });
    try {
      final params = {
        'city':        _selectedName ?? _selectedSlug,
        'prcp':        double.tryParse(_prcp.text)      ?? 0.0,
        'humidity':    double.tryParse(_humidity.text)  ?? 60.0,
        'pressure':    double.tryParse(_pressure.text)  ?? 1010.0,
        'cloud_cover': double.tryParse(_cloud.text)     ?? 30.0,
        'tmax':        double.tryParse(_tmax.text)      ?? 35.0,
        'tmin':        double.tryParse(_tmin.text)      ?? 20.0,
        'tavg':        double.tryParse(_tavg.text)      ?? 27.0,
        'wspd':        double.tryParse(_wspd.text)      ?? 10.0,
      };
      final data = await _repo.predictCity(_selectedSlug!, params);
      setState(() => _result = data);
    } catch (e) {
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _reset() => setState(() {
    _result = null;
    _error  = null;
  });

  @override
  Widget build(BuildContext context) {
    final isDark      = Theme.of(context).brightness == Brightness.dark;
    final bg          = isDark ? HGColors.bgDark    : HGColors.bgLight;
    final card        = isDark ? HGColors.cardDark  : HGColors.cardLight;
    final textColor   = isDark ? HGColors.textDark  : HGColors.textLight;
    final mutedColor  = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final lineColor   = isDark ? HGColors.lineDark  : HGColors.lineLight;
    final citiesAsync = ref.watch(citiesListProvider);

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: Icon(Icons.arrow_back_rounded, color: textColor),
          onPressed: () => context.pop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Manual Prediction',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: textColor)),
            Text('Enter parameters · Run ML inference',
                style: TextStyle(fontSize: 11, color: mutedColor)),
          ],
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // City selector
              _SectionLabel('City', isDark: isDark),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                decoration: BoxDecoration(
                  color: card,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: lineColor),
                ),
                child: citiesAsync.when(
                  loading: () => const SizedBox(
                      height: 48,
                      child: Center(child: CircularProgressIndicator())),
                  error: (_, __) => const Text('Failed to load cities',
                      style: TextStyle(color: HGColors.severe)),
                  data: (cities) => DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value:         _selectedSlug,
                      isExpanded:    true,
                      hint:          Text('Select a city',
                          style: TextStyle(color: mutedColor)),
                      dropdownColor: card,
                      style: TextStyle(color: textColor, fontSize: 14),
                      items: cities.map((c) {
                        final slug = (c['slug'] as String? ?? '');
                        final name = (c['name'] as String? ?? slug);
                        return DropdownMenuItem(
                            value: slug,
                            child: Text(name,
                                style: TextStyle(color: textColor)));
                      }).toList(),
                      onChanged: (v) {
                        final city = cities.firstWhere(
                            (c) => c['slug'] == v,
                            orElse: () => {});
                        setState(() {
                          _selectedSlug = v;
                          _selectedName = city['name'] as String?;
                          _result       = null;
                        });
                      },
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Weather parameters
              _SectionLabel('Weather Parameters', isDark: isDark),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: card,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: lineColor),
                ),
                child: Column(
                  children: [
                    Row(children: [
                      Expanded(child: _ParamField(
                        ctrl: _prcp, label: 'Precipitation', unit: 'mm',
                        icon: Icons.water_drop_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                      const SizedBox(width: 12),
                      Expanded(child: _ParamField(
                        ctrl: _humidity, label: 'Humidity', unit: '%',
                        icon: Icons.water_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                    ]),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: _ParamField(
                        ctrl: _pressure, label: 'Pressure', unit: 'hPa',
                        icon: Icons.speed_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                      const SizedBox(width: 12),
                      Expanded(child: _ParamField(
                        ctrl: _cloud, label: 'Cloud Cover', unit: '%',
                        icon: Icons.cloud_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                    ]),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: _ParamField(
                        ctrl: _tmax, label: 'Max Temp', unit: '°C',
                        icon: Icons.thermostat_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                      const SizedBox(width: 12),
                      Expanded(child: _ParamField(
                        ctrl: _tmin, label: 'Min Temp', unit: '°C',
                        icon: Icons.thermostat_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                    ]),
                    const SizedBox(height: 12),
                    Row(children: [
                      Expanded(child: _ParamField(
                        ctrl: _tavg, label: 'Avg Temp', unit: '°C',
                        icon: Icons.device_thermostat_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                      const SizedBox(width: 12),
                      Expanded(child: _ParamField(
                        ctrl: _wspd, label: 'Wind Speed', unit: 'km/h',
                        icon: Icons.air_outlined,
                        isDark: isDark, textColor: textColor,
                        mutedColor: mutedColor, lineColor: lineColor,
                      )),
                    ]),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Run button
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _loading ? null : _runPrediction,
                  style: FilledButton.styleFrom(
                    backgroundColor: HGColors.blue,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.psychology_outlined,
                          color: Colors.white),
                  label: Text(
                    _loading ? 'Running ML inference…' : 'Run Prediction',
                    style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: Colors.white),
                  ),
                ),
              ),

              // Error
              if (_error != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: HGColors.severeSoft,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: HGColors.severe.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          color: HGColors.severe, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(_error!,
                              style: const TextStyle(
                                  color: HGColors.severe, fontSize: 13))),
                    ],
                  ),
                ),
              ],

              // Result
              if (_result != null) ...[
                const SizedBox(height: 20),
                _ResultCard(
                  result:     _result!,
                  isDark:     isDark,
                  card:       card,
                  textColor:  textColor,
                  mutedColor: mutedColor,
                  lineColor:  lineColor,
                ),
                const SizedBox(height: 12),
                TextButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh_rounded, size: 16),
                  label: const Text('Clear result'),
                ),
              ],
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

// Section label
class _SectionLabel extends StatelessWidget {
  final String text;
  final bool isDark;
  const _SectionLabel(this.text, {required this.isDark});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text,
            style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
                color:
                    isDark ? HGColors.mutedDark : HGColors.mutedLight)),
      );
}

// Parameter input field
class _ParamField extends StatelessWidget {
  final TextEditingController ctrl;
  final String label, unit;
  final IconData icon;
  final bool isDark;
  final Color textColor, mutedColor, lineColor;

  const _ParamField({
    required this.ctrl,
    required this.label,
    required this.unit,
    required this.icon,
    required this.isDark,
    required this.textColor,
    required this.mutedColor,
    required this.lineColor,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$label ($unit)',
            style: TextStyle(
                fontSize: 11,
                color: mutedColor,
                fontWeight: FontWeight.w500)),
        const SizedBox(height: 4),
        TextFormField(
          controller: ctrl,
          keyboardType: const TextInputType.numberWithOptions(
              decimal: true, signed: true),
          style: TextStyle(fontSize: 14, color: textColor),
          decoration: InputDecoration(
            prefixIcon: Icon(icon, size: 16, color: mutedColor),
            contentPadding: const EdgeInsets.symmetric(
                horizontal: 12, vertical: 10),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: lineColor)),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: lineColor)),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(
                    color: HGColors.blue, width: 1.5)),
            filled:    true,
            fillColor: isDark
                ? const Color(0xFF1A2035)
                : const Color(0xFFF8FAFC),
          ),
          validator: (v) {
            if (v == null || v.isEmpty) return 'Required';
            if (double.tryParse(v) == null) return 'Number only';
            return null;
          },
        ),
      ],
    );
  }
}

// Result card
class _ResultCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final bool isDark;
  final Color card, textColor, mutedColor, lineColor;

  const _ResultCard({
    required this.result,
    required this.isDark,
    required this.card,
    required this.textColor,
    required this.mutedColor,
    required this.lineColor,
  });

  @override
  Widget build(BuildContext context) {
    final riskBand  = result['risk_band']       as String? ?? 'Low';
    final hriScore  = (result['hri_score']      as num?)?.toInt() ?? 0;
    final tierLabel = result['alert_tier_label'] as String? ?? 'NORMAL';
    final eventProb =
        ((result['event_probability'] as num?)?.toDouble() ?? 0.0) * 100;
    final drivers   = (result['drivers'] as List?) ?? [];
    final inferMode = result['inference_mode']      as String? ?? 'unknown';
    final stability = result['prediction_stability'] as String? ?? 'stable';
    final city      = result['city']               as String? ?? '';

    final scenarioColor = switch (riskBand) {
      'Severe'   => HGColors.severe,
      'High'     => HGColors.warning,
      'Moderate' => HGColors.watch,
      _          => HGColors.safe,
    };

    final tierColor = switch (tierLabel) {
      'ALERT'    => HGColors.severe,
      'ADVISORY' => HGColors.watch,
      _          => HGColors.safe,
    };

    return Container(
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: scenarioColor.withValues(alpha: 0.4), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: scenarioColor
                  .withValues(alpha: isDark ? 0.15 : 0.08),
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(14)),
            ),
            child: Row(
              children: [
                Icon(Icons.psychology_rounded,
                    color: scenarioColor, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Prediction Result — $city',
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: textColor)),
                      Text(
                          inferMode == 'mc_dropout'
                              ? 'MC Dropout active'
                              : 'Deterministic mode',
                          style: TextStyle(
                              fontSize: 11, color: mutedColor)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: tierColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                        color: tierColor.withValues(alpha: 0.4)),
                  ),
                  child: Text(tierLabel,
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: tierColor)),
                ),
              ],
            ),
          ),

          // Main metrics
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // HRI + Risk band + Flood prob
                Row(children: [
                  Expanded(child: _MetricBox(
                    label: 'HRI Score', value: '$hriScore', unit: '/ 100',
                    color: scenarioColor, isDark: isDark,
                    textColor: textColor, mutedColor: mutedColor,
                    lineColor: lineColor,
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: _MetricBox(
                    label: 'Risk Band', value: riskBand, unit: '',
                    color: scenarioColor, isDark: isDark,
                    textColor: textColor, mutedColor: mutedColor,
                    lineColor: lineColor,
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: _MetricBox(
                    label: 'Flood Prob.',
                    value: '${eventProb.toStringAsFixed(1)}%',
                    unit: '',
                    color: HGColors.blue, isDark: isDark,
                    textColor: textColor, mutedColor: mutedColor,
                    lineColor: lineColor,
                  )),
                ]),

                // Stability + mode
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF1A2035)
                        : const Color(0xFFF1F5FB),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.auto_graph_outlined,
                          size: 14, color: HGColors.blue),
                      const SizedBox(width: 6),
                      Text('Stability: ',
                          style:
                              TextStyle(fontSize: 12, color: mutedColor)),
                      Text(stability,
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: textColor)),
                      const SizedBox(width: 12),
                      const Icon(Icons.memory_outlined,
                          size: 14, color: HGColors.violet),
                      const SizedBox(width: 6),
                      Text('Mode: ',
                          style:
                              TextStyle(fontSize: 12, color: mutedColor)),
                      Expanded(
                        child: Text(
                          inferMode == 'mc_dropout'
                              ? 'MC Dropout'
                              : 'Deterministic',
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: textColor),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),

                // SHAP Drivers
                if (drivers.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Text('Top Drivers (SHAP)',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: mutedColor)),
                  const SizedBox(height: 8),
                  ...drivers.take(4).map((d) {
                    final shap  =
                        (d['shap'] as num?)?.toDouble() ?? 0.0;
                    final weight = shap.abs();
                    final isUp   = shap >= 0;
                    final rawName = d['display_name'] as String? ??
                        (d['feature'] as String? ?? 'unknown');
                    final feature = rawName
                        .replaceAll('_', ' ')
                        .split(' ')
                        .map((w) => w.isEmpty
                            ? w
                            : '${w[0].toUpperCase()}${w.substring(1)}')
                        .join(' ');
                    final maxW = drivers.fold(0.0, (m, x) {
                      final w2 = ((x['shap'] as num?)
                                  ?.toDouble()
                                  .abs() ??
                              0.0);
                      return w2 > m ? w2 : m;
                    });
                    final barFrac = maxW > 0 ? weight / maxW : 0.0;
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Row(children: [
                        Icon(
                          isUp
                              ? Icons.arrow_upward_rounded
                              : Icons.arrow_downward_rounded,
                          size: 14,
                          color: isUp ? HGColors.severe : HGColors.safe,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(feature,
                                  style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: textColor)),
                              const SizedBox(height: 3),
                              ClipRRect(
                                borderRadius: BorderRadius.circular(2),
                                child: LinearProgressIndicator(
                                  value:           barFrac,
                                  backgroundColor: isDark
                                      ? const Color(0xFF2D3748)
                                      : const Color(0xFFE2E8F0),
                                  valueColor: AlwaysStoppedAnimation(
                                      isUp
                                          ? HGColors.severe
                                          : HGColors.safe),
                                  minHeight: 4,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(shap.toStringAsFixed(3),
                            style: TextStyle(
                                fontSize: 11,
                                fontFamily: 'monospace',
                                color: mutedColor)),
                      ]),
                    );
                  }),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricBox extends StatelessWidget {
  final String label, value, unit;
  final Color color, textColor, mutedColor, lineColor;
  final bool isDark;

  const _MetricBox({
    required this.label,
    required this.value,
    required this.unit,
    required this.color,
    required this.isDark,
    required this.textColor,
    required this.mutedColor,
    required this.lineColor,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color:  color.withValues(alpha: isDark ? 0.12 : 0.07),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 10,
                    color: mutedColor,
                    fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(value,
                    style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: color,
                        fontFamily: 'monospace')),
                if (unit.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(left: 3, bottom: 2),
                    child: Text(unit,
                        style:
                            TextStyle(fontSize: 11, color: mutedColor)),
                  ),
              ],
            ),
          ],
        ),
      );
}
