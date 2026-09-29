#!/usr/bin/env bash
# Step 22 — mobile-responsive smoke test (real backend + real frontend).
# Usage: bash scripts/smoke_step22.sh   (from repo root; requires Chrome, Python, Node)
# Produces docs/step22_*.png screenshots and docs/step22_probe_*.html probe dumps.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
[ -x "$CHROME" ] || CHROME="/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"

cleanup() { kill -9 "$VITEPID" "$UVPID" 2>/dev/null; sleep 1; }
trap cleanup EXIT

# ---- start servers as independent subshells (a plain `cd x && cmd &` would
# ---- background the whole list and skip the next cd — do not "simplify" this) ----
( cd frontend && exec npx vite --port 5173 --strictPort >/tmp/vite.log 2>&1 ) &
VITEPID=$!
( cd backend && exec python -m uvicorn app.main:create_app --factory --port 8000 --log-level warning >/tmp/uv.log 2>&1 ) &
UVPID=$!
sleep 8
echo "backend: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/locations/tree)"
echo "vite:    $(curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/)"

# Encoded app URLs for the probe page's ?url= parameter
ENC_DASH=$(python -c "import urllib.parse;print(urllib.parse.quote('http://localhost:5173/?tab=dashboard&loc=2',safe=''))")
ENC_MAP=$(python -c "import urllib.parse;print(urllib.parse.quote('http://localhost:5173/',safe=''))")
ENC_MR=$(python -c "import urllib.parse;print(urllib.parse.quote('http://localhost:5173/?tab=dashboard&loc=2&lang=mr',safe=''))")

# Expected testids per mode (dashboard runs also check advisory + history presence).
# NB: react-leaflet v4 drops data-* props, so "leaflet-map" never appears in the DOM;
# the map is verified via req=leaflet (.leaflet-container) instead.
DASH_EXPECT="dash-summary,dash-probability,dash-uncertainty,dash-data-quality,history-panel,advisory-panel,advisory-disclaimer,lang-select,crop-select"
MAP_EXPECT="location-select,tab-map,tab-dashboard"

probe() { # $1=width $2=height $3=encoded-app-url $4=label $5=expected-testids $6=extra-req(leaflet|none)
  local REQ="${6:-none}"
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size="$1,$2" --virtual-time-budget=25000 \
    --screenshot="$(cygpath -w "$ROOT/docs/step22_$4.png")" \
    "http://localhost:5173/step22-probe.html?w=$1&h=$2&url=$3&expect=$5&req=$REQ" >/tmp/chrome.log 2>&1
  "$CHROME" --headless=new --disable-gpu --no-sandbox --window-size="$1,$2" \
    --virtual-time-budget=25000 --dump-dom \
    "http://localhost:5173/step22-probe.html?w=$1&h=$2&url=$3&expect=$5&req=$REQ" \
    >"$ROOT/docs/step22_probe_$4.html" 2>/dev/null
  echo "--- probe $4 ---"
  sed -n '/PROBE_START/,/PROBE_END/p' "$ROOT/docs/step22_probe_$4.html"
  # NB: the dump contains the probe's own script source, so grep for the *title element*,
  # not the bare string (which appears inside the source too).
  grep -q "<title>PROBE_OK" "$ROOT/docs/step22_probe_$4.html" || FAIL=1
}

FAIL=0
probe 375  812 "$ENC_DASH" mobile_375_dash "$DASH_EXPECT"
probe 390  844 "$ENC_DASH" mobile_390_dash "$DASH_EXPECT"
probe 768 1024 "$ENC_DASH" tablet_768_dash "$DASH_EXPECT"
probe 1440 900 "$ENC_DASH" desktop_1440_dash "$DASH_EXPECT"
probe 375  812 "$ENC_MAP"  mobile_375_map  "$MAP_EXPECT" leaflet
probe 375  812 "$ENC_MR"   mobile_375_mr   "$DASH_EXPECT"

echo "SMOKE_FAIL=$FAIL"
ls -la "$ROOT/docs"/step22_*.png 2>/dev/null
echo "SMOKE_DONE"
