import 'package:shared_preferences/shared_preferences.dart';

class LocalStorage {
  LocalStorage._();
  static final LocalStorage instance = LocalStorage._();

  SharedPreferences? _prefs;

  Future<void> init() async {
    _prefs ??= await SharedPreferences.getInstance();
  }

  SharedPreferences get prefs {
    assert(_prefs != null, 'LocalStorage.init() must be called before use');
    return _prefs!;
  }

  // Theme
  String get theme => prefs.getString('hg_theme') ?? 'system';
  Future<void> setTheme(String v) => prefs.setString('hg_theme', v);

  // Selected city
  String get city => prefs.getString('hg_city') ?? 'Islamabad';
  Future<void> setCity(String v) => prefs.setString('hg_city', v);

  // Language
  String get lang => prefs.getString('hg_lang') ?? 'en';
  Future<void> setLang(String v) => prefs.setString('hg_lang', v);

  // Notification toggles
  bool get notif      => prefs.getBool('hg_notif')    ?? true;
  bool get critOnly   => prefs.getBool('hg_critOnly') ?? false;
  bool get quietHours => prefs.getBool('hg_quiet')    ?? false;
  bool get smsAlert   => prefs.getBool('hg_sms')      ?? false;

  Future<void> setNotif(bool v)    => prefs.setBool('hg_notif',    v);
  Future<void> setCritOnly(bool v) => prefs.setBool('hg_critOnly', v);
  Future<void> setQuiet(bool v)    => prefs.setBool('hg_quiet',    v);
  Future<void> setSms(bool v)      => prefs.setBool('hg_sms',      v);

  // Accessibility
  bool get bigText  => prefs.getBool('hg_bigText')  ?? false;
  bool get contrast => prefs.getBool('hg_contrast') ?? false;
  Future<void> setBigText(bool v)  => prefs.setBool('hg_bigText',  v);
  Future<void> setContrast(bool v) => prefs.setBool('hg_contrast', v);

  // Local profile (JSON string)
  String? get localProfile => prefs.getString('hg_local_profile');
  Future<void> setLocalProfile(String json) => prefs.setString('hg_local_profile', json);

  // Learn checklist (JSON string of Map<String, bool>)
  String? get learnChecklist => prefs.getString('hg_learn_checklist');
  Future<void> setLearnChecklist(String json) => prefs.setString('hg_learn_checklist', json);
}
