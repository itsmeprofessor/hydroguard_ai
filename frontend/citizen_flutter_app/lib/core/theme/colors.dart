import 'package:flutter/material.dart';

class HGColors {
  HGColors._();

  // Severity ladder
  static const Color safe     = Color(0xFF22C55E);
  static const Color monitor  = Color(0xFF06B6D4);
  static const Color watch    = Color(0xFFEAB308);
  static const Color warning  = Color(0xFFF97316);
  static const Color severe   = Color(0xFFEF4444);
  static const Color evac     = Color(0xFFB91C1C);

  // Severity soft backgrounds (light mode)
  static const Color safeSoft     = Color(0xFFDCFCE7);
  static const Color monitorSoft  = Color(0xFFCFFAFE);
  static const Color watchSoft    = Color(0xFFFEF3C7);
  static const Color warningSoft  = Color(0xFFFFEDD5);
  static const Color severeSoft   = Color(0xFFFEE2E2);
  static const Color evacSoft     = Color(0xFFFEC9C9);

  // Severity soft backgrounds (dark mode)
  static const Color safeSoftDark     = Color(0xFF0E2918);
  static const Color monitorSoftDark  = Color(0xFF06262C);
  static const Color watchSoftDark    = Color(0xFF2A2008);
  static const Color warningSoftDark  = Color(0xFF2A1808);
  static const Color severeSoftDark   = Color(0xFF2A0F10);

  // Brand accents
  static const Color blue       = Color(0xFF2563EB);
  static const Color blueSoft   = Color(0xFFDBEAFE);
  static const Color cyan       = Color(0xFF0891B2);
  static const Color violet     = Color(0xFF7C3AED);
  static const Color violetSoft = Color(0xFFEDE9FE);

  // Surfaces — light
  static const Color bgLight   = Color(0xFFF4F6FB);
  static const Color bg2Light  = Color(0xFFECEFF5);
  static const Color cardLight = Color(0xFFFFFFFF);

  // Surfaces — dark
  static const Color bgDark    = Color(0xFF07090E);
  static const Color bg2Dark   = Color(0xFF0B0F17);
  static const Color cardDark  = Color(0xFF131823);

  // Text — light
  static const Color textLight  = Color(0xFF0B1220);
  static const Color text2Light = Color(0xFF2E3645);
  static const Color mutedLight = Color(0xFF5B6573);
  static const Color dimLight   = Color(0xFF8B95A5);

  // Text — dark
  static const Color textDark   = Color(0xFFF6F8FB);
  static const Color mutedDark  = Color(0xFFA0AAB8);
  static const Color dimDark    = Color(0xFF6E7886);

  // Dividers
  static const Color lineLight = Color(0x120F172A); // rgba(15,23,42,0.07)
  static const Color lineDark  = Color(0x12FFFFFF); // rgba(255,255,255,0.07)

  // Scenario → color map
  static Color forScenario(String scenario) => switch (scenario) {
    'safe'    => safe,
    'monitor' => monitor,
    'watch'   => watch,
    'warning' => warning,
    'severe'  => severe,
    'evac'    => evac,
    _         => monitor,
  };

  static Color softForScenario(String scenario, {bool dark = false}) {
    if (dark) {
      return switch (scenario) {
        'safe'    => safeSoftDark,
        'monitor' => monitorSoftDark,
        'watch'   => watchSoftDark,
        'warning' => warningSoftDark,
        'severe'  => severeSoftDark,
        _         => monitorSoftDark,
      };
    }
    return switch (scenario) {
      'safe'    => safeSoft,
      'monitor' => monitorSoft,
      'watch'   => watchSoft,
      'warning' => warningSoft,
      'severe'  => severeSoft,
      'evac'    => evacSoft,
      _         => monitorSoft,
    };
  }
}
