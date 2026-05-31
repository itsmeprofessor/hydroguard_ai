import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);
    return base.copyWith(
      brightness: Brightness.light,
      scaffoldBackgroundColor: HGColors.bgLight,
      colorScheme: ColorScheme.fromSeed(
        seedColor: HGColors.blue,
        brightness: Brightness.light,
        surface: HGColors.cardLight,
        onSurface: HGColors.textLight,
      ).copyWith(
        primary: HGColors.blue,
        secondary: HGColors.cyan,
        tertiary: HGColors.violet,
        error: HGColors.severe,
        onPrimary: Colors.white,
        onError: Colors.white,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
        bodyColor: HGColors.textLight,
        displayColor: HGColors.textLight,
      ),
      cardTheme: CardThemeData(
        color: HGColors.cardLight,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
      dividerColor: HGColors.lineLight,
      dividerTheme: const DividerThemeData(color: HGColors.lineLight, space: 1, thickness: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFF8FAFC),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: HGColors.blue, width: 1.5)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        hintStyle: const TextStyle(color: HGColors.mutedLight),
        labelStyle: const TextStyle(color: HGColors.mutedLight),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        foregroundColor: HGColors.textLight,
        iconTheme: IconThemeData(color: HGColors.textLight),
      ),
      iconTheme: const IconThemeData(color: HGColors.mutedLight),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: HGColors.cardLight,
        selectedItemColor: HGColors.blue,
        unselectedItemColor: HGColors.mutedLight,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? HGColors.blue : null),
        trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? HGColors.blueSoft : null),
      ),
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? HGColors.blue : null),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: HGColors.textLight,
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: HGColors.bgDark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: HGColors.blue,
        brightness: Brightness.dark,
        surface: HGColors.cardDark,
        onSurface: HGColors.textDark,
      ).copyWith(
        primary: HGColors.blue,
        secondary: HGColors.cyan,
        tertiary: HGColors.violet,
        error: HGColors.severe,
        onPrimary: Colors.white,
        onError: Colors.white,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
        bodyColor: HGColors.textDark,
        displayColor: HGColors.textDark,
      ),
      cardTheme: CardThemeData(
        color: HGColors.cardDark,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
      dividerColor: HGColors.lineDark,
      dividerTheme: const DividerThemeData(color: HGColors.lineDark, space: 1, thickness: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF1A2035),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF2D3748))),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF2D3748))),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: HGColors.blue, width: 1.5)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        hintStyle: const TextStyle(color: HGColors.mutedDark),
        labelStyle: const TextStyle(color: HGColors.mutedDark),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        foregroundColor: HGColors.textDark,
        iconTheme: IconThemeData(color: HGColors.textDark),
      ),
      iconTheme: const IconThemeData(color: HGColors.mutedDark),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: HGColors.cardDark,
        selectedItemColor: HGColors.blue,
        unselectedItemColor: HGColors.mutedDark,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? HGColors.blue : null),
        trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? const Color(0xFF1D3A6E) : null),
      ),
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? HGColors.blue : null),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: HGColors.cardDark,
        contentTextStyle: const TextStyle(color: HGColors.textDark),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}
