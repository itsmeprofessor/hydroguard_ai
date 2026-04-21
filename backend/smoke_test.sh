#!/usr/bin/env bash
# HydroGuard-AI — backend smoke test
# ──────────────────────────────────────────────────────────────────────────────
# Verifies every endpoint the Flutter app and HTML dashboard depend on.
# Runs in < 5 s against a local FastAPI instance.
#
# Usage:
#   ./smoke_test.sh                     # default http://127.0.0.1:8000
#   ./smoke_test.sh http://192.168.1.100:8000
#   API_URL=https://hydroguard-api.onrender.com ./smoke_test.sh
#
# Exit code 0 on all-green, 1 if any endpoint failed.
# ──────────────────────────────────────────────────────────────────────────────

set -u

API="${1:-${API_URL:-http://127.0.0.1:8000}}"
FAILED=0

# ANSI colors (disable when not a tty)
if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_FAIL=$'\033[31m'; C_DIM=$'\033[2m'; C_END=$'\033[0m'
else
  C_OK=""; C_FAIL=""; C_DIM=""; C_END=""
fi

check() {
  local label="$1" method="$2" path="$3" body="${4:-}"
  local start end ms code out

  start=$(date +%s%3N)
  if [ "$method" = "GET" ]; then
    out=$(curl -s -o /tmp/sm_body -w "%{http_code}" "$API$path" 2>/dev/null)
  else
    out=$(curl -s -o /tmp/sm_body -w "%{http_code}" \
      -X "$method" -H "Content-Type: application/json" \
      -d "$body" "$API$path" 2>/dev/null)
  fi
  code="$out"
  end=$(date +%s%3N); ms=$((end - start))

  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    printf "  ${C_OK}✓${C_END} %-34s ${C_DIM}[%s]${C_END}  %4d ms  HTTP %s\n" \
      "$label" "$method $path" "$ms" "$code"
  else
    printf "  ${C_FAIL}✗${C_END} %-34s ${C_DIM}[%s]${C_END}  %4d ms  HTTP %s\n" \
      "$label" "$method $path" "$ms" "$code"
    # Print first 120 chars of body for debugging
    head -c 180 /tmp/sm_body 2>/dev/null | sed 's/^/      /'
    echo ""
    FAILED=1
  fi
}

echo ""
echo "  HydroGuard-AI · backend smoke test"
echo "  target: $API"
echo "  ────────────────────────────────────────────────────────────────"

# Core endpoints used by both clients
check "health"                GET  "/health"
check "model info"            GET  "/model/info"
check "anomalies (list)"      GET  "/anomalies?limit=5"
check "anomalies (stats)"     GET  "/anomalies/statistics"

# HTML dashboard aliases (added by analytics_aliases.py)
check "database statistics"   GET  "/database/statistics"
check "analytics aggregate"   GET  "/analytics"

# Prediction pipeline (uses a minimal valid payload matching
# WeatherData.toAnomalyApiFormat() output — required fields only)
check "predict"               POST "/predict" '{
  "city":"Islamabad","region":"Punjab","date":"2026-04-20",
  "month":4,"day":20,"dayofweek":0,"is_weekend":0,
  "season":"Spring","latitude":33.6844,"longitude":73.0479,
  "tmin":18.0,"tmax":28.0,"tavg":23.0,"temp_range":10.0,
  "prcp":2.5,"wspd":12.0,"humidity":65,"pressure":1013.0,
  "dew_point":16.0,"cloud_cover":40
}'

echo "  ────────────────────────────────────────────────────────────────"
if [ $FAILED -eq 0 ]; then
  printf "  ${C_OK}PASS${C_END} · all endpoints reachable\n\n"
  exit 0
else
  printf "  ${C_FAIL}FAIL${C_END} · one or more endpoints failed\n\n"
  printf "  hints:\n"
  printf "    · is uvicorn running?  (uvicorn app.main:app --reload)\n"
  printf "    · is the backend patched? (analytics_aliases.py + CORS)\n"
  printf "    · is the /predict payload valid? (check backend logs)\n\n"
  exit 1
fi
