import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/storage/local_storage.dart';

class AppPrefs {
  final String theme;
  final String city;
  final String lang;
  final bool notif;
  final bool critOnly;
  final bool quiet;
  final bool sms;
  final bool bigText;
  final bool contrast;

  const AppPrefs({
    this.theme    = 'system',
    this.city     = 'Islamabad',
    this.lang     = 'en',
    this.notif    = true,
    this.critOnly = false,
    this.quiet    = false,
    this.sms      = false,
    this.bigText  = false,
    this.contrast = false,
  });

  AppPrefs copyWith({
    String? theme,
    String? city,
    String? lang,
    bool? notif,
    bool? critOnly,
    bool? quiet,
    bool? sms,
    bool? bigText,
    bool? contrast,
  }) => AppPrefs(
    theme:    theme    ?? this.theme,
    city:     city     ?? this.city,
    lang:     lang     ?? this.lang,
    notif:    notif    ?? this.notif,
    critOnly: critOnly ?? this.critOnly,
    quiet:    quiet    ?? this.quiet,
    sms:      sms      ?? this.sms,
    bigText:  bigText  ?? this.bigText,
    contrast: contrast ?? this.contrast,
  );
}

class PrefsNotifier extends StateNotifier<AppPrefs> {
  PrefsNotifier() : super(const AppPrefs()) {
    _load();
  }

  void _load() {
    final s = LocalStorage.instance;
    state = AppPrefs(
      theme:    s.theme,
      city:     s.city,
      lang:     s.lang,
      notif:    s.notif,
      critOnly: s.critOnly,
      quiet:    s.quietHours,
      sms:      s.smsAlert,
      bigText:  s.bigText,
      contrast: s.contrast,
    );
  }

  Future<void> setTheme(String v)   async { await LocalStorage.instance.setTheme(v);    state = state.copyWith(theme: v); }
  Future<void> setCity(String v)    async { await LocalStorage.instance.setCity(v);     state = state.copyWith(city: v); }
  Future<void> setLang(String v)    async { await LocalStorage.instance.setLang(v);     state = state.copyWith(lang: v); }
  Future<void> setNotif(bool v)     async { await LocalStorage.instance.setNotif(v);    state = state.copyWith(notif: v); }
  Future<void> setCritOnly(bool v)  async { await LocalStorage.instance.setCritOnly(v); state = state.copyWith(critOnly: v); }
  Future<void> setQuiet(bool v)     async { await LocalStorage.instance.setQuiet(v);    state = state.copyWith(quiet: v); }
  Future<void> setSms(bool v)       async { await LocalStorage.instance.setSms(v);      state = state.copyWith(sms: v); }
  Future<void> setBigText(bool v)   async { await LocalStorage.instance.setBigText(v);  state = state.copyWith(bigText: v); }
  Future<void> setContrast(bool v)  async { await LocalStorage.instance.setContrast(v); state = state.copyWith(contrast: v); }
}

final prefsProvider =
    StateNotifierProvider<PrefsNotifier, AppPrefs>((_) => PrefsNotifier());
