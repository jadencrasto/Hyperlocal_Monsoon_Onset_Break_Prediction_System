#!/usr/bin/env bash
# Steps 24-25 — live smoke test: real online refresh against Open-Meteo, provider-failure
# simulation, cache preservation, provenance/freshness reporting, mode matrix.
# NOTE: performs a REAL (small) history refresh for one location + year. Read-mostly.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

( cd backend && exec python -m uvicorn app.main:create_app --factory --port 8000 --log-level warning >/tmp/uv2425.log 2>&1 ) &
UVPID=$!
trap 'kill -9 $UVPID 2>/dev/null' EXIT
sleep 6

API=http://127.0.0.1:8000/api
NASHIK=2

echo "== 1. mode + provider reachability =="
curl -s $API/mode; echo

echo "== 2. baseline prediction (before refresh) =="
P_BASE=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_BASE" | python -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| latest:', ds['latest_rainfall_date'], '| freshness:', ds['freshness'], '| cache:', ds['cache_status'])"

echo "== 3. ONLINE refresh attempt (real Open-Meteo archive, Sep 2026, Nashik) =="
R=$(curl -s -X POST "$API/locations/$NASHIK/history/refresh" -H 'Content-Type: application/json' \
  -d '{"provider": "open_meteo", "start": "2026-09-01", "end": "2026-09-29"}')
echo "$R"
python - "$R" <<'PYEOF'
import json, sys
r = json.loads(sys.argv[1])
print("refresh status:", r["status"], "| category:", r["category"], "| rows:", r["n_records"])
PYEOF

echo "== 4. post-refresh prediction + provenance =="
P_AFTER=$(curl -s "$API/locations/$NASHIK/prediction/break-risk")
echo "$P_AFTER" | python -c "import json,sys; d=json.load(sys.stdin); ds=d['data_status']; print('prob:', d['probability'], '| provider:', ds['provider'], '| latest:', ds['latest_rainfall_date'], '| freshness:', ds['freshness'], '| cache:', ds['cache_status'], '| last_failure:', d['last_sync_failure'])"

echo "== 5. mode matrix (probability stability) =="
for M in offline online auto; do
  curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d "{\"preference\": \"$M\"}" >/dev/null
  curl -s "$API/locations/$NASHIK/prediction/break-risk" | python -c "import json,sys; d=json.load(sys.stdin); print('$M'.ljust(8), '->', d['probability'], d['data_status']['cache_status'])"
done
curl -s -X PUT $API/mode -H 'Content-Type: application/json' -d '{"preference": "auto"}' >/dev/null

echo "== 6. provider failure simulation (unknown provider -> structured 422) =="
curl -s -X POST "$API/locations/$NASHIK/forecast/refresh" -H 'Content-Type: application/json' -d '{"provider": "ghost"}' | python -c "import json,sys; print(json.load(sys.stdin)['detail'])"

echo "== 7. sync-log categories =="
curl -s "$API/sync-log?limit=5" | python -c "import json,sys; [print(e['kind'], e['status'], e['category'], (e['message'] or '')[:60]) for e in json.load(sys.stdin)]"

echo "== 8. sources last_error carries category =="
curl -s $API/sources | python -c "import json,sys; p=json.load(sys.stdin)['providers'][0]; print('provider:', p['name'], '| last_error:', p['last_error'])"

echo "SMOKE2425_DONE"
