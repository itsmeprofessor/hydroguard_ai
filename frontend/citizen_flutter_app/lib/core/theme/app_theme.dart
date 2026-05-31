import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData light() => ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: HGColors.bgLight,
    colorScheme: ColorScheme.fromSeed(
      seedColor: HGColors.blue,
      brightness: Brightness.light,
    ),
    textTheme: GoogleFonts.interTextTheme(ThemeData.light().textTheme),
    cardTheme: CardThemeData(
      color: HGColors.cardLight,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    dividerColor: HGColors.lineLight,
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: HGColors.cardLight,
      selectedItemColor: HGColors.blue,
      unselectedItemColor: HGColors.mutedLight,
      type: BottomNavigationBarType.fixed,
      elevation: 0,
    ),
  );

  static ThemeData dark() => ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: HGColors.bgDark,
    colorScheme: ColorScheme.fromSeed(
      seedColor: HGColors.blue,
      brightness: Brightness.dark,
    ),
    textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
    cardTheme: CardThemeData(
      color: HGColors.cardDark,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    dividerColor: HGColors.lineDark,
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: HGColors.cardDark,
      selectedItemColor: HGColors.blue,
      unselectedItemColor: HGColors.mutedDark,
      type: BottomNavigationBarType.fixed,
      elevation: 0,
    ),
  );
}
