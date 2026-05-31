import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../repositories/city_repository.dart';
import '../../shared/providers/auth_provider.dart';

class SignupScreen extends ConsumerStatefulWidget {
  const SignupScreen({super.key});
  @override
  ConsumerState<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends ConsumerState<SignupScreen> {
  final _nameCtrl     = TextEditingController();
  final _usernameCtrl = TextEditingController();
  final _emailCtrl    = TextEditingController();
  final _phoneCtrl    = TextEditingController();
  final _pwCtrl       = TextEditingController();
  final _pw2Ctrl      = TextEditingController();

  int     _step          = 1;
  bool    _showPw        = false;
  bool    _showPw2       = false;
  bool    _agreed        = false;
  bool    _loading       = false;
  String? _error;
  String? _selectedCity;

  List<String> _cities = [];
  bool _citiesLoading = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _usernameCtrl.dispose();
    _emailCtrl.dispose();
    _phoneCtrl.dispose();
    _pwCtrl.dispose();
    _pw2Ctrl.dispose();
    super.dispose();
  }

  // Password strength: 0-4
  int get _strength {
    final pw = _pwCtrl.text;
    int s = 0;
    if (pw.length >= 8) s++;
    if (pw.contains(RegExp(r'[A-Z]'))) s++;
    if (pw.contains(RegExp(r'[0-9]'))) s++;
    if (pw.contains(RegExp(r'[!@#\$&*~]'))) s++;
    return s;
  }

  Color _strengthColor(int s) {
    if (s <= 1) return HGColors.severe;
    if (s == 2) return HGColors.warning;
    if (s == 3) return HGColors.watch;
    return HGColors.safe;
  }

  String? _validate() {
    if (_nameCtrl.text.trim().isEmpty) return 'Full name is required.';
    if (_usernameCtrl.text.length < 3) return 'Username must be at least 3 characters.';
    if (!_emailCtrl.text.contains('@')) return 'Enter a valid email address.';
    if (_pwCtrl.text.length < 8) return 'Password must be at least 8 characters.';
    if (_pwCtrl.text != _pw2Ctrl.text) return 'Passwords do not match.';
    if (!_agreed) return 'Please agree to the terms and privacy policy.';
    return null;
  }

  Future<void> _continue() async {
    final err = _validate();
    if (err != null) { setState(() => _error = err); return; }
    setState(() { _loading = true; _error = null; });
    try {
      await ref.read(authProvider.notifier).register(
          _emailCtrl.text.trim(), _usernameCtrl.text.trim(), _pwCtrl.text);
      // Load cities for step 2
      setState(() { _step = 2; _loading = false; _citiesLoading = true; });
      try {
        final raw = await CityRepository().getCities();
        setState(() {
          _cities = raw.map((m) => m['name'] as String? ?? '').where((n) => n.isNotEmpty).toList();
          _citiesLoading = false;
        });
      } catch (_) {
        setState(() {
          _cities = ['Islamabad', 'Lahore', 'Karachi', 'Rawalpindi', 'Peshawar', 'Quetta'];
          _citiesLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Container(color: const Color(0xFF0B1220)),
          Positioned(
            top: -80, left: -60,
            child: Container(
              width: 320, height: 320,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: HGColors.blue.withValues(alpha: 0.15),
              ),
            ),
          ),
          Positioned(
            bottom: -80, right: -60,
            child: Container(
              width: 320, height: 320,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: HGColors.violet.withValues(alpha: 0.12),
              ),
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                // Top bar
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.arrow_back, color: Colors.white),
                        onPressed: _step == 2
                            ? () => setState(() => _step = 1)
                            : () => context.pop(),
                      ),
                      const Spacer(),
                      Text(
                        'Step $_step/2',
                        style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.7), fontSize: 13),
                      ),
                      const SizedBox(width: 8),
                      // Step dots
                      Row(
                        children: List.generate(2, (i) => Container(
                          width: i + 1 == _step ? 16 : 8,
                          height: 8,
                          margin: const EdgeInsets.only(right: 4),
                          decoration: BoxDecoration(
                            color: i + 1 == _step
                                ? HGColors.blue
                                : Colors.white.withValues(alpha: 0.3),
                            borderRadius: BorderRadius.circular(4),
                          ),
                        )),
                      ),
                    ],
                  ),
                ),
                // Body
                Expanded(
                  child: _step == 1 ? _buildStep1() : _buildStep2(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStep1() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
        ),
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Create account',
                style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0B1220))),
            const SizedBox(height: 4),
            const Text('Join HydroGuard to get personalised flood alerts.',
                style: TextStyle(fontSize: 13, color: HGColors.mutedLight)),
            const SizedBox(height: 20),

            if (_error != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                    color: HGColors.severeSoft,
                    borderRadius: BorderRadius.circular(10)),
                child: Text(_error!,
                    style: const TextStyle(fontSize: 13, color: HGColors.severe)),
              ),
              const SizedBox(height: 12),
            ],

            _field('Full name', _nameCtrl, Icons.person_outline),
            const SizedBox(height: 12),
            _field('Username', _usernameCtrl, Icons.alternate_email,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[a-zA-Z0-9_\-]'))]),
            const SizedBox(height: 12),
            _field('Email', _emailCtrl, Icons.mail_outline,
                keyboardType: TextInputType.emailAddress),
            const SizedBox(height: 12),
            _field('Phone (optional)', _phoneCtrl, Icons.phone_outlined,
                keyboardType: TextInputType.phone),
            const SizedBox(height: 12),
            _pwFieldWithStrength(),
            const SizedBox(height: 12),
            _confirmPwField(),
            const SizedBox(height: 16),

            // Terms checkbox
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Checkbox(
                  value: _agreed,
                  activeColor: HGColors.blue,
                  onChanged: (v) => setState(() => _agreed = v ?? false),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text.rich(
                      TextSpan(children: [
                        const TextSpan(
                            text: 'I agree to the ',
                            style: TextStyle(fontSize: 13, color: HGColors.mutedLight)),
                        TextSpan(
                            text: 'Terms of Service',
                            style: const TextStyle(
                                fontSize: 13,
                                color: HGColors.blue,
                                fontWeight: FontWeight.w600)),
                        const TextSpan(
                            text: ' and ',
                            style: TextStyle(fontSize: 13, color: HGColors.mutedLight)),
                        TextSpan(
                            text: 'Privacy Policy',
                            style: const TextStyle(
                                fontSize: 13,
                                color: HGColors.blue,
                                fontWeight: FontWeight.w600)),
                      ]),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _loading ? null : _continue,
                style: FilledButton.styleFrom(
                  backgroundColor: HGColors.blue,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                child: _loading
                    ? const SizedBox(
                        width: 20, height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Text('Continue',
                        style: TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text('Already have an account? ',
                    style: TextStyle(fontSize: 13, color: HGColors.mutedLight)),
                GestureDetector(
                  onTap: () => context.pop(),
                  child: const Text('Sign in',
                      style: TextStyle(
                          fontSize: 13,
                          color: HGColors.blue,
                          fontWeight: FontWeight.w700)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStep2() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
        ),
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Your city',
                style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0B1220))),
            const SizedBox(height: 4),
            const Text('Select your primary city to receive localised alerts.',
                style: TextStyle(fontSize: 13, color: HGColors.mutedLight)),
            const SizedBox(height: 20),

            if (_citiesLoading)
              const Center(child: CircularProgressIndicator())
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _cities.map((city) {
                  final selected = _selectedCity == city;
                  return GestureDetector(
                    onTap: () => setState(() => _selectedCity = city),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: selected ? HGColors.blueSoft : const Color(0xFFF8FAFC),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: selected ? HGColors.blue : const Color(0xFFE2E8F0),
                          width: selected ? 1.5 : 1,
                        ),
                      ),
                      child: Text(
                        city,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: selected ? HGColors.blue : const Color(0xFF2E3645),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),

            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => context.go('/citizen/home'),
                style: FilledButton.styleFrom(
                  backgroundColor: HGColors.blue,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                child: const Text('Get started',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: TextButton(
                onPressed: () => context.go('/citizen/home'),
                child: const Text('Skip for now',
                    style: TextStyle(color: HGColors.mutedLight, fontSize: 13)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field(
    String label,
    TextEditingController ctrl,
    IconData icon, {
    TextInputType? keyboardType,
    List<TextInputFormatter>? inputFormatters,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(0xFF2E3645))),
        const SizedBox(height: 6),
        TextField(
          controller: ctrl,
          keyboardType: keyboardType,
          inputFormatters: inputFormatters,
          decoration: InputDecoration(
            prefixIcon: Icon(icon, size: 18, color: HGColors.mutedLight),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: HGColors.blue, width: 1.5)),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
          ),
        ),
      ],
    );
  }

  Widget _pwFieldWithStrength() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Password',
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(0xFF2E3645))),
        const SizedBox(height: 6),
        TextField(
          controller: _pwCtrl,
          obscureText: !_showPw,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.lock_outline,
                size: 18, color: HGColors.mutedLight),
            suffixIcon: IconButton(
              icon: Icon(
                _showPw
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                size: 18,
                color: HGColors.mutedLight,
              ),
              onPressed: () => setState(() => _showPw = !_showPw),
            ),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: HGColors.blue, width: 1.5)),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
          ),
        ),
        const SizedBox(height: 8),
        // Strength meter
        Row(
          children: List.generate(4, (i) => Expanded(
            child: Container(
              height: 4,
              margin: const EdgeInsets.only(right: 4),
              decoration: BoxDecoration(
                color: i < _strength
                    ? _strengthColor(_strength)
                    : const Color(0xFFE2E8F0),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          )),
        ),
      ],
    );
  }

  Widget _confirmPwField() {
    final mismatch = _pw2Ctrl.text.isNotEmpty && _pwCtrl.text != _pw2Ctrl.text;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Confirm password',
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(0xFF2E3645))),
        const SizedBox(height: 6),
        TextField(
          controller: _pw2Ctrl,
          obscureText: !_showPw2,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.lock_outline,
                size: 18, color: HGColors.mutedLight),
            suffixIcon: IconButton(
              icon: Icon(
                _showPw2
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                size: 18,
                color: HGColors.mutedLight,
              ),
              onPressed: () => setState(() => _showPw2 = !_showPw2),
            ),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(
                    color: mismatch
                        ? HGColors.severe
                        : const Color(0xFFE2E8F0))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(
                    color: mismatch
                        ? HGColors.severe
                        : const Color(0xFFE2E8F0))),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(
                    color: mismatch ? HGColors.severe : HGColors.blue,
                    width: 1.5)),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
          ),
        ),
        if (mismatch) ...[
          const SizedBox(height: 4),
          const Text('Passwords do not match',
              style: TextStyle(fontSize: 11, color: HGColors.severe)),
        ],
      ],
    );
  }
}
