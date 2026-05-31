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
  (
    t: 'What is a cloudburst?',
    d: '3 min read',
    color: Color(0xFF2563EB),
    icon: Icons.thunderstorm_outlined,
    body: '''A cloudburst is an intense, sudden rainstorm that dumps more than 100mm of rain per hour. In Pakistan's hilly terrain — Islamabad, Peshawar, and Gilgit — cloudbursts can trigger flash floods within minutes.

**Signs of an approaching cloudburst:**
• Rapidly darkening sky with green or yellow tint
• Thunder before visible lightning
• Sudden drop in temperature (5-10°C in minutes)
• Distant rumbling that grows louder quickly

**What makes them dangerous:**
Storm drains and nullahs overflow within 15–20 minutes of a cloudburst. Low-lying areas and underpasses flood first. Never wait for water to "level off" before evacuating.

**HydroGuard monitors:** prcp (precipitation rate), pressure drop, humidity spike, and cloud cover — all early indicators of cloudburst formation.''',
  ),
  (
    t: 'Flash flood survival',
    d: '5 min · key points',
    color: Color(0xFFEF4444),
    icon: Icons.waves_outlined,
    body: '''Flash floods kill more people than any other flood type in Pakistan. They arrive with little warning and move with tremendous force.

**During a flash flood:**
• Do NOT try to walk through moving water — 15 cm of fast-moving water can knock you down
• Do NOT drive through flooded roads — 30 cm of water can sweep a car away
• Move to higher ground immediately — upper floors of a building or a hillside
• Stay away from rivers, nullahs, storm drains, and culverts

**If caught in a vehicle:**
1. Stay calm — don't panic
2. Open windows before water rises
3. Exit and move perpendicular to the flood flow to reach high ground
4. Never stay in a submerged vehicle

**Emergency: Call Rescue 1122 — free, 24/7 across Pakistan**

**Post-flood:** Wait for official all-clear before returning. Floodwater carries sewage, chemicals, and debris. Do not touch it without protection.''',
  ),
  (
    t: 'Build your emergency kit',
    d: 'Interactive checklist',
    color: Color(0xFF22C55E),
    icon: Icons.medical_services_outlined,
    body: '''Your emergency kit should be packed and ready to grab in 60 seconds. Store it near your front door.

**Water & Food (72-hour supply):**
• 4 litres of water per person per day (12L for a family of 3 for 3 days)
• Non-perishable food: canned goods, dry biscuits, nuts, dried fruit
• Manual can opener
• Water purification tablets

**First Aid:**
• Bandages, antiseptic, gauze
• Prescription medications (7-day supply)
• First aid manual

**Documents (in waterproof bag):**
• CNIC / B-Form copies for all family members
• Property documents
• Insurance papers
• Emergency cash (small denominations)

**Communication & Light:**
• Battery-powered or hand-crank radio
• Flashlight with extra batteries
• Fully charged power bank
• Family emergency contact list (written — phones die)

**Clothing & Shelter:**
• Warm clothing for each family member
• Emergency blanket / mylar blanket
• Rain poncho or waterproof jacket

**Special needs:**
• Infant formula, diapers
• Extra spectacles / contact lens supplies
• Hearing aid batteries''',
  ),
  (
    t: 'Driving in a flood',
    d: '2 min read',
    color: Color(0xFFF97316),
    icon: Icons.directions_car_outlined,
    body: '''More Pakistanis die in vehicles during floods than almost any other flood-related cause. Here's what to do.

**The golden rule: Turn Around, Don't Drown**
If you cannot see the road surface under floodwater, do not cross.

**Water depth guide:**
• 15 cm: Can stall most cars; motorcycles fall over
• 30 cm: Can float small cars, sweep motorcycles
• 60 cm: Sweeps away large vehicles and buses
• 90 cm+: Completely submerges most vehicles

**Before driving in a storm:**
• Check HydroGuard alerts for your route cities
• Identify alternate routes that avoid underpasses and low bridges
• Keep your fuel tank above half
• Tell someone your route and expected arrival time

**If your car stalls in rising water:**
1. Do NOT try to restart the engine (hydrolocks the engine)
2. Exit immediately — before water reaches door handles
3. Leave belongings — take only phone, keys, documents bag
4. Move uphill, away from the vehicle

**Underpasses in Islamabad, Lahore, Karachi:** These flood extremely fast. If you see any water in an underpass, find another route. Do not enter.''',
  ),
  (
    t: 'Helping vulnerable neighbors',
    d: '4 min read',
    color: Color(0xFF7C3AED),
    icon: Icons.people_outlined,
    body: '''During a flood emergency, elderly neighbors, people with disabilities, and families without transportation are most at risk. Here's how to help.

**Before the flood (when HydroGuard shows Watch or higher):**
• Knock on doors of elderly or disabled neighbors — offer to help them prepare
• Help them locate important documents and medications
• Identify neighbors who may need transport to reach higher ground
• Share the Rescue 1122 number (free call)

**During evacuation:**
• Do not wait for neighbors to ask — proactively offer help
• Assist mobility-impaired individuals up stairs or to vehicles
• Carry emergency kits for those who cannot
• Never leave a vulnerable person alone in a flooded area

**What to bring when helping:**
• Extra water and snacks
• Flashlight
• A list of your neighbors' medical needs (ask in advance)

**Community shelter protocol:**
Pakistan has designated community shelter points in most flood-prone areas. Ask your local Union Council or Rescue 1122 for the nearest shelter address. Note it down now — it may be hard to find during an emergency.

**After the flood:**
• Check on neighbors again within 24 hours
• Flood trauma is real — listen, don't minimize what they experienced
• Help clear mud and debris from entrances before they return home''',
  ),
  (
    t: 'After the flood',
    d: '6 min · full protocol',
    color: Color(0xFF06B6D4),
    icon: Icons.home_repair_service_outlined,
    body: '''Returning home after a flood is dangerous if done too early or without precautions. Follow this protocol.

**Wait for official clearance:**
• Do not re-enter your home until Rescue 1122 or NDMA has declared the area safe
• Even if water has receded, structural damage, gas leaks, and electrical hazards remain

**Before entering the building:**
• Check for cracks in walls and foundation
• Smell for gas — if you smell gas, do not enter and call the gas company
• Do not use electrical switches until an electrician has inspected the wiring

**Inside the home:**
• Wear rubber boots and gloves — floodwater is contaminated with sewage and chemicals
• Open all windows and doors to ventilate
• Do not use taps until water supply is confirmed safe
• Photograph all damage before cleaning — for insurance and NDMA compensation claims

**Cleaning:**
• Remove mud and debris immediately — it grows mold within 24-48 hours
• Disinfect all surfaces with bleach solution (1 cup bleach per 10 litres water)
• Throw away all food and water that contacted floodwater
• Dry mattresses, furniture, and carpets in sunlight for 2+ days

**Health risks:**
• Drink only boiled or bottled water for at least 2 weeks
• Wash hands frequently with soap
• Watch for fever, diarrhea, skin infections — seek medical help early
• Leptospirosis (from floodwater contact with skin) is a risk — see a doctor if you develop flu-like symptoms after flood contact

**Claim support:**
• NDMA compensation: nadma.gov.pk
• Provincial Disaster Management Authorities (PDMAs) also provide relief
• Rescue 1122 can connect you with support services''',
  ),
];

// ── Quiz data ─────────────────────────────────────────────────────────────────

class _QuizQuestion {
  final String question;
  final List<String> options;
  final int correctIndex;
  final String explanation;
  const _QuizQuestion({
    required this.question,
    required this.options,
    required this.correctIndex,
    required this.explanation,
  });
}

class _QuizTier {
  final String name;
  final String subtitle;
  final String badge;
  final Color color;
  final List<_QuizQuestion> questions;
  const _QuizTier({
    required this.name,
    required this.subtitle,
    required this.badge,
    required this.color,
    required this.questions,
  });
}

const _quizTiers = [
  _QuizTier(
    name: 'Flood Aware',
    subtitle: 'Beginner · Basic flood safety',
    badge: '🌊 Flood Aware',
    color: Color(0xFF2563EB),
    questions: [
      _QuizQuestion(
        question: 'What is the emergency rescue number in Pakistan?',
        options: ['1122', '115', '911', '1000'],
        correctIndex: 0,
        explanation: "Rescue 1122 is Pakistan's free, 24/7 emergency rescue service available across all major cities.",
      ),
      _QuizQuestion(
        question: 'How much moving water can knock a person off their feet?',
        options: ['60 cm', '30 cm', '15 cm', '90 cm'],
        correctIndex: 2,
        explanation: 'Just 15 cm (6 inches) of fast-moving floodwater is enough to knock an adult off their feet.',
      ),
      _QuizQuestion(
        question: 'What does HRI stand for in HydroGuard?',
        options: ['Humidity Risk Index', 'Hazard Risk Indicator', 'HydroGuard Risk Index', 'Hydrological Rainfall Index'],
        correctIndex: 2,
        explanation: 'HRI (HydroGuard Risk Index) is a 0–100 score combining ML flood probability with weather severity and regional vulnerability.',
      ),
      _QuizQuestion(
        question: 'When should you evacuate your home during a flash flood warning?',
        options: ['When water enters the ground floor', 'Immediately when authorities order evacuation', 'When water reaches knee height', 'After turning off all utilities'],
        correctIndex: 1,
        explanation: 'Evacuate IMMEDIATELY when authorities order it — do not wait for visible flooding. Flash floods can overwhelm structures in minutes.',
      ),
      _QuizQuestion(
        question: 'What should you do if your car stalls in rising floodwater?',
        options: ['Try to restart the engine repeatedly', 'Stay in the car and wait for help', 'Exit immediately and move to higher ground', 'Call someone before exiting'],
        correctIndex: 2,
        explanation: 'Exit the vehicle immediately. Water rises fast — waiting even 2-3 minutes can trap you inside. Leave belongings behind.',
      ),
    ],
  ),
  _QuizTier(
    name: 'Community Guardian',
    subtitle: 'Intermediate · Risk levels & neighbors',
    badge: '🛡️ Community Guardian',
    color: Color(0xFFF97316),
    questions: [
      _QuizQuestion(
        question: 'An HRI score of 55 in HydroGuard indicates:',
        options: ['Safe — no action needed', 'Elevated risk — monitor conditions', 'Immediate evacuation required', 'System is offline'],
        correctIndex: 1,
        explanation: 'HRI 50-75 indicates elevated (High) risk. Monitor HydroGuard updates, prepare your kit, and be ready to evacuate quickly.',
      ),
      _QuizQuestion(
        question: 'What does "ADVISORY" alert tier mean in HydroGuard?',
        options: ['Everything is fine', 'Stay informed and be prepared', 'Evacuate now', 'Roads are already flooded'],
        correctIndex: 1,
        explanation: 'ADVISORY means the ML model has detected elevated flood probability. Stay informed, prepare your kit, and monitor for updates.',
      ),
      _QuizQuestion(
        question: 'Which of these is the BEST way to help an elderly neighbor during a flood warning?',
        options: ['Wait for them to ask for help', 'Call them once to check in', 'Proactively knock on their door and offer to help them prepare', 'Post on social media about the flood risk'],
        correctIndex: 2,
        explanation: 'Proactive outreach is critical. Elderly residents may not have smartphones, may not be monitoring alerts, or may need physical assistance to evacuate.',
      ),
      _QuizQuestion(
        question: 'How many litres of water per person should you store for a 3-day emergency?',
        options: ['4 litres', '8 litres', '12 litres', '2 litres'],
        correctIndex: 2,
        explanation: '4 litres per person per day × 3 days = 12 litres. This covers drinking and basic sanitation needs.',
      ),
      _QuizQuestion(
        question: 'When is it safe to re-enter your home after a flood?',
        options: ['As soon as water recedes', 'After 24 hours', 'Only after official clearance from Rescue 1122 or NDMA', 'When neighbors start returning'],
        correctIndex: 2,
        explanation: 'Wait for official clearance. Receded water leaves behind structural damage, gas leaks, electrical hazards, and contamination invisible to the eye.',
      ),
    ],
  ),
  _QuizTier(
    name: 'Crisis Ready',
    subtitle: 'Advanced · Full emergency protocol',
    badge: '⚡ Crisis Ready',
    color: Color(0xFFEF4444),
    questions: [
      _QuizQuestion(
        question: 'What household chemical can safely disinfect flood-damaged surfaces?',
        options: ['Vinegar', 'Bleach (1 cup per 10L water)', 'Hydrogen peroxide', 'Ammonia'],
        correctIndex: 1,
        explanation: 'Bleach (sodium hypochlorite) at 1 cup per 10 litres of water is the WHO-recommended solution for disinfecting flood-contaminated surfaces.',
      ),
      _QuizQuestion(
        question: 'What is leptospirosis and how is it related to floods?',
        options: ['A waterborne disease spread via contaminated floodwater contact with skin', 'Flood-related electricity shock injury', 'Structural collapse injury type', 'A type of water pump malfunction'],
        correctIndex: 0,
        explanation: 'Leptospirosis is a bacterial infection spread when floodwater (contaminated with animal urine) contacts broken skin. Symptoms appear 2-30 days later. Wear rubber boots and gloves in floodwater.',
      ),
      _QuizQuestion(
        question: 'Which NDMA resource provides flood compensation claims in Pakistan?',
        options: ['pmdu.gov.pk', 'nadma.gov.pk', '1122.gov.pk', 'pdma.gov.pk'],
        correctIndex: 1,
        explanation: 'NDMA (National Disaster Management Authority) at nadma.gov.pk handles national-level compensation. Provincial PDMAs handle province-level relief.',
      ),
      _QuizQuestion(
        question: 'A cloudburst is defined as rainfall exceeding:',
        options: ['20mm per hour', '50mm per hour', '100mm per hour', '200mm per hour'],
        correctIndex: 2,
        explanation: 'A cloudburst is technically defined as rainfall exceeding 100mm (approximately 4 inches) per hour — an intensity that overwhelms most urban drainage systems within minutes.',
      ),
      _QuizQuestion(
        question: 'If you smell gas after returning home post-flood, you should:',
        options: ['Open windows to ventilate, then inspect', 'Turn on lights to see better', 'Leave immediately without using any switches or flames, call the gas company from outside', 'Use a lighter to check for gas leaks'],
        correctIndex: 2,
        explanation: 'Gas leaks are extremely dangerous. Any spark — including light switches — can cause an explosion. Leave immediately, do not use any electrical switches, and call the gas company from a safe distance outside.',
      ),
    ],
  ),
];

// ─────────────────────────────────────────────────────────────────────────────

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
    final mutedColor = isDark ? HGColors.mutedDark : HGColors.mutedLight;

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
                  .map((g) => _GuideCard(
                        guide: g,
                        onTap: () => showModalBottomSheet(
                          context: context,
                          isScrollControlled: true,
                          backgroundColor: Colors.transparent,
                          builder: (_) =>
                              _GuideDetailSheet(guide: g, isDark: isDark),
                        ),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 16),

            // ── Quiz section ──
            const SizedBox(height: 8),
            Text('Flood Safety Quiz',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: textColor)),
            const SizedBox(height: 4),
            Text('Test your knowledge — 3 difficulty levels',
                style: TextStyle(fontSize: 12, color: mutedColor)),
            const SizedBox(height: 12),
            ..._quizTiers.map((tier) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: InkWell(
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => _QuizScreen(tier: tier)),
                    ),
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: isDark ? HGColors.cardDark : HGColors.cardLight,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: tier.color.withValues(alpha: 0.3)),
                      ),
                      child: Row(children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: tier.color.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(Icons.quiz_outlined,
                              color: tier.color, size: 22),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                            child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(tier.name,
                                style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w700,
                                    color: textColor)),
                            Text(tier.subtitle,
                                style: TextStyle(
                                    fontSize: 12, color: mutedColor)),
                          ],
                        )),
                        Icon(Icons.arrow_forward_ios_rounded,
                            size: 14,
                            color: isDark
                                ? HGColors.mutedDark
                                : HGColors.mutedLight),
                      ]),
                    ),
                  ),
                )),
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
  final ({String t, String d, Color color, IconData icon, String body}) guide;
  final VoidCallback onTap;
  const _GuideCard({required this.guide, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = isDark ? HGColors.cardDark : HGColors.cardLight;
    final textColor = isDark ? HGColors.textDark : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return GestureDetector(
      onTap: onTap,
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
            // Colour header with icon
            Container(
              height: 40,
              decoration: BoxDecoration(
                color: guide.color,
                borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(14)),
              ),
              child: Center(
                child: Icon(guide.icon, color: Colors.white, size: 20),
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

// ─── Guide detail bottom sheet ────────────────────────────────────────────────

class _GuideDetailSheet extends StatelessWidget {
  final ({String t, String d, Color color, IconData icon, String body}) guide;
  final bool isDark;
  const _GuideDetailSheet({required this.guide, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final bg    = isDark ? HGColors.cardDark  : HGColors.cardLight;
    final text  = isDark ? HGColors.textDark  : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;

    return Container(
      height: MediaQuery.of(context).size.height * 0.85,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          // Drag handle
          Container(
            width: 36,
            height: 4,
            margin: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: isDark ? HGColors.lineDark : HGColors.lineLight,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          // Header
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
            child: Row(children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: guide.color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(guide.icon, color: guide.color, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                  child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(guide.t,
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: text)),
                  Text(guide.d,
                      style: TextStyle(fontSize: 12, color: muted)),
                ],
              )),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
                color: muted,
              ),
            ]),
          ),
          Divider(
              height: 1,
              color: isDark ? HGColors.lineDark : HGColors.lineLight),
          // Scrollable body
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Text(
                guide.body,
                style: TextStyle(fontSize: 14, color: text, height: 1.65),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Quiz screen ──────────────────────────────────────────────────────────────

class _QuizScreen extends StatefulWidget {
  final _QuizTier tier;
  const _QuizScreen({required this.tier});
  @override
  State<_QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<_QuizScreen> {
  int _current = 0;
  int? _selected;
  bool _answered = false;
  int _score = 0;
  bool _finished = false;

  void _answer(int idx) {
    if (_answered) return;
    final correct = idx == widget.tier.questions[_current].correctIndex;
    setState(() {
      _selected = idx;
      _answered = true;
      if (correct) _score++;
    });
  }

  void _next() {
    if (_current + 1 < widget.tier.questions.length) {
      setState(() {
        _current++;
        _selected = null;
        _answered = false;
      });
    } else {
      setState(() => _finished = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg   = isDark ? HGColors.bgDark   : HGColors.bgLight;
    final card = isDark ? HGColors.cardDark  : HGColors.cardLight;
    final text = isDark ? HGColors.textDark  : HGColors.textLight;
    final muted = isDark ? HGColors.mutedDark : HGColors.mutedLight;
    final total = widget.tier.questions.length;

    // ── Results screen ──
    if (_finished) {
      final pct = (_score / total * 100).round();
      return Scaffold(
        backgroundColor: bg,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          leading: IconButton(
            icon: Icon(Icons.close, color: text),
            onPressed: () => Navigator.pop(context),
          ),
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: widget.tier.color.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.emoji_events_rounded,
                    color: widget.tier.color, size: 40),
              ),
              const SizedBox(height: 20),
              Text(widget.tier.badge,
                  style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      color: widget.tier.color)),
              const SizedBox(height: 8),
              Text('$_score / $total correct  ·  $pct%',
                  style: TextStyle(fontSize: 16, color: text)),
              const SizedBox(height: 6),
              Text(
                pct >= 80
                    ? "Excellent! You're well prepared."
                    : pct >= 60
                        ? 'Good effort — review the guide content.'
                        : 'Keep learning — your safety depends on it.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: muted),
              ),
              const SizedBox(height: 32),
              FilledButton(
                onPressed: () => Navigator.pop(context),
                style: FilledButton.styleFrom(
                  backgroundColor: widget.tier.color,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 32, vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('Done',
                    style: TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600)),
              ),
            ]),
          ),
        ),
      );
    }

    // ── Question screen ──
    final q = widget.tier.questions[_current];
    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: Icon(Icons.close, color: text),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          '${widget.tier.name} · ${_current + 1}/$total',
          style: TextStyle(
              fontSize: 14,
              color: muted,
              fontWeight: FontWeight.w500),
        ),
        centerTitle: false,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Progress bar
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (_current + 1) / total,
              backgroundColor:
                  isDark ? HGColors.lineDark : HGColors.lineLight,
              valueColor:
                  AlwaysStoppedAnimation(widget.tier.color),
              minHeight: 6,
            ),
          ),
          const SizedBox(height: 24),
          Text(q.question,
              style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: text,
                  height: 1.4)),
          const SizedBox(height: 20),
          ...List.generate(q.options.length, (i) {
            Color optBorder =
                isDark ? HGColors.lineDark : HGColors.lineLight;
            Color optText = text;
            if (_answered) {
              if (i == q.correctIndex) {
                optBorder = HGColors.safe;
                optText = HGColors.safe;
              } else if (i == _selected) {
                optBorder = HGColors.severe;
                optText = HGColors.severe;
              }
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: InkWell(
                onTap: () => _answer(i),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: card,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: optBorder,
                      width: _answered &&
                              (i == q.correctIndex ||
                                  i == _selected)
                          ? 2
                          : 1,
                    ),
                  ),
                  child: Row(children: [
                    Expanded(
                        child: Text(q.options[i],
                            style: TextStyle(
                                fontSize: 14, color: optText))),
                    if (_answered && i == q.correctIndex)
                      const Icon(Icons.check_circle_rounded,
                          color: HGColors.safe, size: 20),
                    if (_answered &&
                        i == _selected &&
                        i != q.correctIndex)
                      const Icon(Icons.cancel_rounded,
                          color: HGColors.severe, size: 20),
                  ]),
                ),
              ),
            );
          }),
          if (_answered) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: HGColors.blueSoft
                    .withValues(alpha: isDark ? 0.15 : 1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline_rounded,
                        color: HGColors.blue, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(q.explanation,
                            style: TextStyle(
                                fontSize: 13,
                                color: isDark
                                    ? HGColors.textDark
                                    : HGColors.textLight,
                                height: 1.5))),
                  ]),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _next,
                style: FilledButton.styleFrom(
                  backgroundColor: widget.tier.color,
                  padding:
                      const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
                child: Text(
                  _current + 1 < total
                      ? 'Next Question'
                      : 'See Results',
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ],
        ]),
      ),
    );
  }
}
