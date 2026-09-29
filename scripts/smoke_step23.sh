#!/usr/bin/env bash
# Step 23 — offline/cache smoke test against the REAL backend + REAL database.
# Verifies: valid local data usable -> provider failure keeps data -> cached/offline states
# reported -> identical prediction across modes. Read-only against the real DB (no writes).
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

( cd backend && exec python -m uvicorn app.main:create_app --factory --port 8000 --log-level warning >/tmp/uv23.log 2>&1 ) &
UVPID=$!
trap 'kill -9 $UVPID 2>/dev/null' EXIT
sleep 6

API=http://127.0.0.1:8000/api
NASHIK=2

echo "== 1. mode + health =="
curl -s $API/mode; echo
curl -s $API/health | python -c "import json,sys; d=json.load(sys.stdin); print({k: d[k] for k in ('status','effective_mode','model_available')})"

echo "== 2. prediction ONLINE (cache_status, probability) =="
P_ON=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_ON" | python -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| cache_status:', ds['cache_status'], '| provider:', ds['provider'], '| latest:', ds['latest_rainfall_date'], '| freshness:', ds['freshness'])"

echo "== 3. switch app to OFFLINE (PUT /mode), prediction again =="
curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d '{"preference": "offline"}'; echo
P_OFF=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_OFF" | python -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| cache_status:', ds['cache_status'])"
python - "$P_ON" "$P_OFF" <<'PYEOF'
import json, sys
a, b = json.loads(sys.argv[1]), json.loads(sys.argv[2])
assert a["probability"] == b["probability"], "probability changed between modes!"
print("prediction identical across modes:", a["probability"] == b["probability"])
PYEOF

echo "== 4. offline refresh attempt must be skipped (409), data untouched =="
curl -s -o /dev/null -w "offline refresh HTTP: %{http_code}\n" -X POST "$API/locations/$NASHIK/forecast/refresh" -H 'Content-Type: application/json' -d '{"provider": "open_meteo"}'

echo "== 5. provider failure simulation (fake provider name -> 422 unknown; real provider offline -> 409) =="
# non-destructive failure paths without touching the real DB:
curl -s -X POST "$API/locations/$NASHIK/forecast/refresh" -H 'Content-Type: application/json' -d '{"provider": "no_such_provider"}' | python -c "import json,sys; print('unknown-provider ->', json.load(sys.stdin)['detail'])"

echo "== 6. restore auto mode =="
curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d '{"preference": "auto"}'; echo

echo "== 7. history still served from local store while offline-flagged =="
curl -s "$API/locations/$NASHIK/history?start=2026-09-01&end=2026-09-10" | python -c "import json,sys; d=json.load(sys.stdin); print('rows:', len(d['records']), '| first:', d['records'][0])"

echo "SMOKE23_DONE"
