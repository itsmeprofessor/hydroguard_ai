import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../../core/storage/local_storage.dart';
import '../../../core/theme/colors.dart';
import '../../../shared/widgets/hg_app_bar.dart';

const _checklistItems = [
  (k: 'kit',      l: 'Emergency kit packed',        s: 'Water, first aid, flashlight, batteries'),
  (k: 'plan',     l: 'Family meet-up plan agreed',  s: 'Where to meet if separated'),
  (k: 'contacts', l: 'Emergency contacts saved',    s: 'Rescue 1122, family, neighbors'),
  (k: 'route',    l: 'Evacuation route memorized',  s: 'To nearest shelter or higher ground'),
  (k: 'docs',     l: 'Documents in waterproof bag', s: 'ID cards, deeds, photos'),
  (k: 'water',    l: '3 days of drinking water',    s: '4 L per person per day'),
  (k: 'radio',    l: 'Battery-powered radio',       s: 'When networks fail, this works'),
];

const _guides = [
  (t: 'What is a cloudburst?',     d: '3 min read',    color: Color(0xFF2563EB)),
  (t: 'Flash flood survival',      d: '5 min · video', color: Color(0xFFEF4444)),
  (t: 'Build your kit',            d: 'Interactive',   color: Color(0xFF22C55E)),
  (t: 'Driving in a flood',        d: '2 min read',    color: Color(0xFFF97316)),
  (t: 'Helping elderly neighbors', d: '4 min read',    color: Color(0xFF7C3AED)),
  (t: 'After the flood',           d: '6 min · video', color: Color(0xFF06B6D4)),
];

class LearnScreen extends StatefulWidget {
  const LearnScreen({super.key});

  @override
  State<LearnScreen> createState() => _LearnScreenState();
}

class _LearnScreenState extends State<LearnScreen> {
  Map<String, bool> _checks = {
    for (final item in _checklistItems) item.k: false,
  };

  @override
  void initState() {
    super.initState();
    _loadChecklist();
  }

  void _loadChecklist() {
    final raw = LocalStorage.instance.learnChecklist;
    if (raw != null) {
      try {
        final decoded = jsonDecode(raw) as Map<String, dynamic>;
        setState(() {
          _checks = {
            for (final item in _checklistItems)
              item.k: decoded[item.k] as bool? ?? false,
          };
        });
      } catch (_) {}
    }
  }

  Future<void> _toggleCheck(String key) async {
    setState(() {
      _checks = {..._checks, key: !(_checks[key] ?? false)};
    });
    await LocalStorage.instance
        .setLearnChecklist(jsonEncode(_checks));
  }

  int get _completedCount =>
      _checks.values.where((v) => v).length;

  double get _pct =>
      _checklistItems.isEmpty
          ? 0
          : _completedCount / _checklistItems.length;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.bgDark : HGColors.bgLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;

    return Scaffold(
      backgroundColor: bg,
      appBar: HGAppBar(
        eyebrow: 'Learn & Prepare',
        title: 'Be ready',
        trailing: IconButton(
          icon: const Icon(Icons.search),
          onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Search — coming soon'))),
          color: isDark ? HGColors.textDark : HGColors.textLight,
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Prep score hero ─────────────────────────────────────────
            _PrepScoreCard(pct: _pct, completed: _completedCount),
            const SizedBox(height: 16),

            // ── Readiness checklist ─────────────────────────────────────
            Text('Readiness checklist',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: textColor)),
            const SizedBox(height: 10),
            ..._checklistItems.map(
              (item) => _ChecklistRow(
                item: item,
                checked: _checks[item.k] ?? false,
                onToggle: () => _toggleCheck(item.k),
              ),
            ),
            const SizedBox(height: 16),

            // ── Guides ──────────────────────────────────────────────────
            Text('Guides & explainers',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: textColor)),
            const SizedBox(height: 10),
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: 1.4,
              children: _guides
                  .map((g) => _GuideCard(guide: g))
                  .toList(),
            ),
            const SizedBox(height: 16),

            // ── Quiz CTA ────────────────────────────────────────────────
            _QuizCard(),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }
}

// ─── Prep score card ──────────────────────────────────────────────────────────

class _PrepScoreCard extends StatelessWidget {
  final double pct;
  final int completed;
  const _PrepScoreCard({required this.pct, required this.completed});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF7C3AED), Color(0xFF2563EB)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          children: [
            // Circular progress ring
            SizedBox(
              width: 80,
              height: 80,
              child: CustomPaint(
                painter: _RingPainter(pct: pct),
                child: Center(
                  child: Text(
                    '${(pct * 100).round()}%',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w800),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Your prep score',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(
                    "You've completed $completed of ${_checklistItems.length} steps.",
                    style: const TextStyle(
                        color: Colors.white70, fontSize: 13),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
}

class _RingPainter extends CustomPainter {
  final double pct;
  const _RingPainter({required this.pct});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 6;

    // Background track
    final trackPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.2)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(center, radius, trackPaint);

    // Filled arc
    final fillPaint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      2 * math.pi * pct,
      false,
      fillPaint,
    );
  }

  @override
  bool shouldRepaint(_RingPainter old) => old.pct != pct;
}

// ─── Checklist row ────────────────────────────────────────────────────────────

class _ChecklistRow extends StatelessWidget {
  final ({String k, String l, String s}) item;
  final bool checked;
  final VoidCallback onToggle;
  const _ChecklistRow(
      {required this.item,
      required this.checked,
      required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return GestureDetector(
      onTap: onToggle,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: checked
                  ? HGColors.safe.withValues(alpha: 0.4)
                  : (isDark ? HGColors.lineDark : HGColors.lineLight)),
        ),
        child: Row(
          children: [
            // Checkbox
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: checked ? HGColors.safe : Colors.transparent,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: checked ? HGColors.safe : muted,
                  width: 2,
                ),
              ),
              child: checked
                  ? const Icon(Icons.check,
                      color: Colors.white, size: 16)
                  : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.l,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: textColor,
                      decoration: checked
                          ? TextDecoration.lineThrough
                          : null,
                      decorationColor: muted,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(item.s,
                      style: TextStyle(fontSize: 11, color: muted)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Guide card ───────────────────────────────────────────────────────────────

class _GuideCard extends StatelessWidget {
  final ({String t, String d, Color color}) guide;
  const _GuideCard({required this.guide});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return GestureDetector(
      onTap: () => ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Opening ${guide.t} — coming soon'))),
      child: Container(
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Gradient header
            Container(
              height: 40,
              decoration: BoxDecoration(
                color: guide.color,
                borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(14)),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(guide.t,
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: textColor),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ),
                    Text(guide.d,
                        style: TextStyle(fontSize: 10, color: muted)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Quiz CTA card ────────────────────────────────────────────────────────────

class _QuizCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF7C3AED), Color(0xFF2563EB)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.quiz_outlined,
                  color: Colors.white, size: 24),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('Test what you know',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w700)),
                  SizedBox(height: 2),
                  Text('5-question quiz · earn the Ready badge',
                      style: TextStyle(
                          color: Colors.white70, fontSize: 12)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            ElevatedButton(
              onPressed: () => ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('Quiz coming soon'))),
              style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: const Color(0xFF7C3AED),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10))),
              child: const Text('Start',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ],
        ),
      );
}
