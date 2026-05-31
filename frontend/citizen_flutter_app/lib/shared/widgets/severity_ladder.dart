import 'package:flutter/material.dart';
import '../../core/theme/colors.dart';

class SeverityLadder extends StatelessWidget {
  final String currentScenario;
  final bool showLabels;

  const SeverityLadder({
    super.key,
    required this.currentScenario,
    this.showLabels = true,
  });

  static const _steps  = ['safe', 'monitor', 'watch', 'warning', 'severe', 'evac'];
  static const _labels = ['Safe', 'Monitor', 'Watch', 'Warning', 'Severe', 'Evac'];

  @override
  Widget build(BuildContext context) {
    final curIdx = _steps.indexOf(currentScenario);
    return Column(
      children: [
        Row(
          children: List.generate(_steps.length, (i) {
            final active = i <= curIdx;
            final color  = active
                ? HGColors.forScenario(_steps[i])
                : const Color(0x20000000);
            return Expanded(
              child: Container(
                height: 6,
                margin: const EdgeInsets.symmetric(horizontal: 1.5),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            );
          }),
        ),
        if (showLabels) ...[
          const SizedBox(height: 6),
          Row(
            children: List.generate(
              _steps.length,
              (i) => Expanded(
                child: Text(
                  _labels[i],
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    color: i <= curIdx
                        ? HGColors.forScenario(_steps[i])
                        : Colors.grey,
                    letterSpacing: 0.3,
                  ),
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}
