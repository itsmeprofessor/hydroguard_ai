import 'package:flutter/material.dart';
import '../../core/theme/colors.dart';

class HGErrorCard extends StatelessWidget {
  final String? message;
  final VoidCallback? onRetry;
  final String label;

  const HGErrorCard({
    super.key,
    this.message,
    this.onRetry,
    this.label = 'Could not load data',
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: isDark ? HGColors.cardDark : HGColors.cardLight,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('⚠️', style: TextStyle(fontSize: 32)),
          const SizedBox(height: 8),
          Text(
            label,
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: isDark ? HGColors.textDark : HGColors.textLight,
            ),
          ),
          if (message != null) ...[
            const SizedBox(height: 6),
            Text(
              message!,
              style: const TextStyle(fontSize: 12, color: HGColors.mutedLight),
              textAlign: TextAlign.center,
            ),
          ],
          if (onRetry != null) ...[
            const SizedBox(height: 16),
            TextButton(
              onPressed: onRetry,
              style: TextButton.styleFrom(
                backgroundColor: HGColors.blueSoft,
                foregroundColor: HGColors.blue,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('Retry'),
            ),
          ],
        ],
      ),
    );
  }
}
