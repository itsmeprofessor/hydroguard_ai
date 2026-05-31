import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/colors.dart';
import '../../shared/providers/auth_provider.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});
  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _pwCtrl    = TextEditingController();
  bool _showPw  = false;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _pwCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_emailCtrl.text.isEmpty || _pwCtrl.text.isEmpty) return;
    setState(() { _loading = true; _error = null; });
    try {
      await ref.read(authProvider.notifier).login(
          _emailCtrl.text.trim(), _pwCtrl.text);
      // Router redirect handles navigation
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // Dark background
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF0B1220), Color(0xFF0B1220)],
              ),
            ),
          ),
          Positioned(
            top: -100,
            left: -80,
            child: Container(
              width: 400,
              height: 400,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: HGColors.blue.withValues(alpha: 0.18),
              ),
            ),
          ),
          Positioned(
            bottom: -100,
            right: -80,
            child: Container(
              width: 400,
              height: 400,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: HGColors.monitor.withValues(alpha: 0.15),
              ),
            ),
          ),
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const SizedBox(height: 48),
                  // Brand icon
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      color: HGColors.blue.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                      border: Border.all(
                          color: HGColors.blue.withValues(alpha: 0.4)),
                    ),
                    child: const Icon(Icons.water_drop_rounded,
                        color: Colors.white, size: 28),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'HydroGuard',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -0.5),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Welcome back',
                    style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.6),
                        fontSize: 14),
                  ),
                  const SizedBox(height: 40),

                  // Sign-in card
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(24),
                    ),
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Sign in',
                          style: TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0B1220)),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Continue receiving flood alerts for your city.',
                          style: TextStyle(
                              fontSize: 13, color: HGColors.mutedLight),
                        ),
                        const SizedBox(height: 20),

                        if (_error != null) ...[
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: HGColors.severeSoft,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              _error!,
                              style: const TextStyle(
                                  fontSize: 13, color: HGColors.severe),
                            ),
                          ),
                          const SizedBox(height: 12),
                        ],

                        _field('Email', _emailCtrl, Icons.mail_outline,
                            keyboardType: TextInputType.emailAddress),
                        const SizedBox(height: 12),
                        _pwField(),
                        const SizedBox(height: 10),

                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            GestureDetector(
                              onTap: () => context.push('/forgot-password'),
                              child: const Text(
                                'Forgot password?',
                                style: TextStyle(
                                    color: HGColors.blue,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 13),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 20),

                        SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: _loading ? null : _submit,
                            style: FilledButton.styleFrom(
                              backgroundColor: HGColors.blue,
                              padding:
                                  const EdgeInsets.symmetric(vertical: 16),
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(14)),
                            ),
                            child: _loading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white),
                                  )
                                : const Text(
                                    'Sign in',
                                    style: TextStyle(
                                        fontSize: 15,
                                        fontWeight: FontWeight.w600),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Text(
                              'New to HydroGuard? ',
                              style: TextStyle(
                                  fontSize: 13, color: HGColors.mutedLight),
                            ),
                            GestureDetector(
                              onTap: () => context.push('/signup'),
                              child: const Text(
                                'Create account',
                                style: TextStyle(
                                    fontSize: 13,
                                    color: HGColors.blue,
                                    fontWeight: FontWeight.w700),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.shield_outlined,
                          size: 12,
                          color: Colors.white.withValues(alpha: 0.5)),
                      const SizedBox(width: 6),
                      Text(
                        'End-to-end encrypted · Free for residents of Pakistan',
                        style: TextStyle(
                            fontSize: 11,
                            color: Colors.white.withValues(alpha: 0.5)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _field(
    String label,
    TextEditingController ctrl,
    IconData icon, {
    TextInputType? keyboardType,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(0xFF2E3645)),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: ctrl,
          keyboardType: keyboardType,
          style: const TextStyle(color: Color(0xFF0B1220)), // always dark text — card is always white
          decoration: InputDecoration(
            prefixIcon: Icon(icon, size: 18, color: HGColors.mutedLight),
            hintStyle: TextStyle(color: Color(0xFF0B1220).withValues(alpha: 0.4)),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: Color(0xFFE2E8F0))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: Color(0xFFE2E8F0))),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: HGColors.blue, width: 1.5)),
            contentPadding: const EdgeInsets.symmetric(
                horizontal: 14, vertical: 14),
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
          ),
        ),
      ],
    );
  }

  Widget _pwField() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Password',
          style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: Color(0xFF2E3645)),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: _pwCtrl,
          obscureText: !_showPw,
          style: const TextStyle(color: Color(0xFF0B1220)), // always dark text — card is always white
          decoration: InputDecoration(
            hintStyle: TextStyle(color: Color(0xFF0B1220).withValues(alpha: 0.4)),
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
                borderSide:
                    const BorderSide(color: Color(0xFFE2E8F0))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: Color(0xFFE2E8F0))),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide:
                    const BorderSide(color: HGColors.blue, width: 1.5)),
            contentPadding: const EdgeInsets.symmetric(
                horizontal: 14, vertical: 14),
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
          ),
        ),
      ],
    );
  }
}
