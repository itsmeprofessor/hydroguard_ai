import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class HGTextStyles {
  HGTextStyles._();

  static TextStyle get sans => GoogleFonts.inter();
  static TextStyle get mono => GoogleFonts.jetBrainsMono();

  static TextStyle heroScore({required Color color}) =>
      GoogleFonts.inter(fontSize: 52, fontWeight: FontWeight.w700, letterSpacing: -2.0, color: color);

  static TextStyle headline({required Color color}) =>
      GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.5, color: color);

  static TextStyle title({required Color color}) =>
      GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: -0.2, color: color);

  static TextStyle body({required Color color}) =>
      GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w400, height: 1.5, color: color);

  static TextStyle caption({required Color color}) =>
      GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w400, color: color);

  static TextStyle eyebrow({required Color color}) =>
      GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.0, color: color);

  static TextStyle monoLarge({required Color color}) =>
      GoogleFonts.jetBrainsMono(fontSize: 28, fontWeight: FontWeight.w600, letterSpacing: -0.5, color: color);

  static TextStyle monoSmall({required Color color}) =>
      GoogleFonts.jetBrainsMono(fontSize: 12, fontWeight: FontWeight.w500, color: color);
}
