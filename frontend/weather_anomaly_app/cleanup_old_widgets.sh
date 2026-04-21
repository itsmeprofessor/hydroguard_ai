#!/usr/bin/env bash
# HydroGuard-AI — post-patch cleanup
# ──────────────────────────────────────────────────────────────────────────────
# After dropping in the new files, these are safe to delete. They are no longer
# imported by anything in the new codebase.
#
# Run from: frontend/weather_anomaly_app/
#
# What goes away:
#   · lib/widgets/hri_gauge.dart         — replaced by core/theme + RiskMeter
#   · lib/widgets/metric_card.dart       — replaced by widgets/dashboard/metric_card.dart
#   · lib/utils/app_theme.dart           — replaced by core/theme/design_system.dart
#                                          (the new screens do NOT import it;
#                                          only legacy widgets did)
#
# Before deleting app_theme.dart, make sure nothing in your own code outside
# lib/screens/ or lib/widgets/ still imports it — e.g. custom widgets you
# added that weren't in the bundle I analyzed.
# ──────────────────────────────────────────────────────────────────────────────

set -e

ROOT="$(pwd)"
if [ ! -f "$ROOT/pubspec.yaml" ]; then
  echo "ERROR: run this from frontend/weather_anomaly_app/ (no pubspec.yaml here)"
  exit 1
fi

echo "Scanning for stale imports before deletion…"
STALE=$(grep -rln --include='*.dart' \
    -e "import '../widgets/hri_gauge.dart'" \
    -e "import '../widgets/metric_card.dart'" \
    -e "import '../utils/app_theme.dart'" \
    lib/ 2>/dev/null | grep -vE "lib/widgets/(hri_gauge|metric_card)\.dart|lib/utils/app_theme\.dart" || true)

if [ -n "$STALE" ]; then
  echo ""
  echo "WARNING — these files still reference the old widgets/theme:"
  echo "$STALE" | sed 's/^/  · /'
  echo ""
  echo "Fix their imports first, then rerun this script."
  exit 1
fi

echo "No stale references. Deleting old files:"
for f in lib/widgets/hri_gauge.dart \
         lib/widgets/metric_card.dart \
         lib/utils/app_theme.dart; do
  if [ -f "$f" ]; then
    rm "$f"
    echo "  - $f"
  fi
done

echo ""
echo "Done. Run: flutter clean && flutter pub get && flutter analyze"
