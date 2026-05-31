import 'package:flutter/material.dart';

class HGSkeleton extends StatefulWidget {
  final double height;
  final double? width;
  final double borderRadius;

  const HGSkeleton({
    super.key,
    this.height = 16,
    this.width,
    this.borderRadius = 8,
  });

  @override
  State<HGSkeleton> createState() => _HGSkeletonState();
}

class _HGSkeletonState extends State<HGSkeleton>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.4, end: 1.0)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Opacity(
        opacity: _anim.value,
        child: Container(
          height: widget.height,
          width: widget.width ?? double.infinity,
          decoration: BoxDecoration(
            color: isDark
                ? const Color(0x12FFFFFF)
                : const Color(0x120F172A),
            borderRadius: BorderRadius.circular(widget.borderRadius),
          ),
        ),
      ),
    );
  }
}
