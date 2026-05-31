import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'prefs_provider.dart';

final themeModeProvider = Provider<ThemeMode>((ref) {
  final theme = ref.watch(prefsProvider).theme;
  return switch (theme) {
    'dark'  => ThemeMode.dark,
    'light' => ThemeMode.light,
    _       => ThemeMode.system,
  };
});
