import 'package:flutter/material.dart';
import '../../core/theme/colors.dart';

class RiskPill extends StatelessWidget {
  final String scenario; // 'safe' | 'monitor' | 'watch' | 'warning' | 'severe'
  final String label;
  final double fontSize;

  const RiskPill({
    super.key,
    required this.scenario,
    required this.label,
    this.fontSize = 11,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final color  = HGColors.forScenario(scenario);
    final soft   = HGColors.softForScenario(scenario, dark: isDark);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
          color: soft, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration:
                BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
