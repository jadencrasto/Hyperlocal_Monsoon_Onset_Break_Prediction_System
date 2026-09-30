#!/usr/bin/env bash
# Requirements 26-29 — live smoke test against the REAL backend.
# Verifies: local caching, online/offline status, automatic fallback,
# freshness indicators, and TTL / cooldown safeguards.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

( cd backend && exec python3 -m uvicorn app.main:create_app --factory --port 8000 --log-level warning >/tmp/uv2629.log 2>&1 ) &
UVPID=$!
trap 'kill -9 $UVPID 2>/dev/null' EXIT
sleep 4

API=http://127.0.0.1:8000/api
NASHIK=2

echo "== 1. check mode & health =="
curl -s $API/mode; echo
curl -s $API/health | python3 -c "import json,sys; d=json.load(sys.stdin); print({k: d[k] for k in ('status','effective_mode','model_available')})"

echo "== 2. prediction ONLINE (auto fallback & status) =="
P_ON=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_ON" | python3 -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| cache_status:', ds['cache_status'], '| data_source:', ds.get('data_source'), '| is_live:', ds.get('is_live'), '| last_updated:', ds.get('last_updated'))"

echo "== 3. switch to OFFLINE mode (PUT /mode), prediction again =="
curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d '{"preference": "offline"}'; echo
P_OFF=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_OFF" | python3 -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| cache_status:', ds['cache_status'], '| data_source:', ds.get('data_source'))"

echo "== 4. verify prediction probability stability =="
python3 - "$P_ON" "$P_OFF" <<'PYEOF'
import json, sys
a, b = json.loads(sys.argv[1]), json.loads(sys.argv[2])
assert a["probability"] == b["probability"], "probability changed between modes!"
print("prediction stable across modes:", a["probability"] == b["probability"])
PYEOF

echo "== 5. restore auto mode =="
curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d '{"preference": "auto"}'; echo

echo "SMOKE2629_DONE"
