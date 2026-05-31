import 'package:flutter/material.dart';
import '../../core/theme/colors.dart';

class HGAppBar extends StatelessWidget implements PreferredSizeWidget {
  final Widget? leading;
  final String eyebrow;
  final String title;
  final Widget? trailing;

  const HGAppBar({
    super.key,
    this.leading,
    required this.eyebrow,
    required this.title,
    this.trailing,
  });

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight + 8);

  @override
  Widget build(BuildContext context) {
    final isDark    = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Row(
          children: [
            if (leading != null) leading! else const SizedBox(width: 38),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    eyebrow,
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: isDark
                            ? HGColors.mutedDark
                            : HGColors.mutedLight),
                  ),
                  Text(
                    title,
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: textColor),
                  ),
                ],
              ),
            ),
            if (trailing != null) trailing! else const SizedBox(width: 38),
          ],
        ),
      ),
    );
  }
}
