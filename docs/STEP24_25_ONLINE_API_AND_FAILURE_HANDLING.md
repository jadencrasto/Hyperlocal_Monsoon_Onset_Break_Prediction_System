# Steps 24–25 — Online API Integration & Failure/Stale Detection (SIH26086)

**Date:** 2026-10-01 · **Scope:** provider failure categories, structured failure surfacing,
stale/fallback indicators, and the project's **first verified live online refresh**.
**No model, probability-math, schema-version, advisory, Step-22 or Step-23-architecture
changes.** No new provider, no new infrastructure.

## Architecture (provider-first, unchanged shape)

```
             External Weather API (Open-Meteo)
                      |
                Provider Adapter  (open_meteo.py — URLs, JSON parsing, retries, categories)
                      |
                 Validation       (types, dates, precip >= 0, field presence)
                 /        \
              valid       invalid/failure
                |            |
                v            v
           SQLite cache    Structured failure (SyncResult.category -> sync_log -> API)
                |                 |
                v                 v
          Prediction API     last_sync_failure (24h window)
                |                 |
       +--------+--------+--------+
       |                          |
    Dashboard                  Risk Map / Advisory
  (cache/offline/stale/
   fallback indicators)
```

The weather service contains **no provider-specific logic** — that stays in the adapter
(`backend/app/providers/open_meteo.py`), which was already the case; Steps 24–25 added
machine-readable failure classification inside that adapter.

## Step 24 — what was verified/added

### Provider adapter (existing, extended)
- Open-Meteo remains the only registered provider (`providers/registry.py`); forecast
  (`/v1/forecast`) and archive/reanalysis history (`/v1/archive`) stay **conceptually
  distinct** (`kind = 'reanalysis'` vs forecast rows in separate tables, separate endpoints).
- Timeout (`request_timeout_s`, default 10 s), bounded retries with backoff, 429/4xx/5xx
  handling, non-JSON rejection, per-record validation (date format, numeric type,
  `precip >= 0`) — all pre-existing, all still tested.
- **New:** every `ProviderError` now carries a `category` (below); timeout vs
  network-failure are distinguished after retry exhaustion.

### Validation before persistence (Step 23 guard, still true)
A batch containing any invalid record is rejected **whole** — no partial write, cache
untouched, `SyncLog` records the failure. Successful writes are idempotent upserts keyed
by `(location_id, date, kind, provider)`; re-refreshing a range never duplicates logical
observations (re-tested).

### Online refresh flow (online mode active)
determine location/range → call provider → validate → persist valid rows → per-row
provenance (`provider`, `kind`, `fetched_at`) → structured `SyncResult` → freshness
recomputed from stored observations (`data_age_days` from the latest stored row).

**Live result (this machine, 2026-09-29):** `POST /api/locations/2/history/refresh`
(open_meteo, 2026-09-01→2026-09-29) → `{"status": "ok", "n_records": 29}` — the first
successful live provider call in the project (the build sandbox of earlier steps blocked
the network). Post-refresh: `provider: open_meteo`, `freshness: current`,
`cache_status: cached`, `last_sync_failure: null`.

## Step 25 — failure categories & stale detection

### Failure categories (plain strings; no error framework)
| category | source |
|---|---|
| `network_failure` | `requests.ConnectionError` after retries |
| `timeout` | `requests.Timeout` after retries |
| `http_failure` | 4xx/5xx/429, exhausted 5xx retries, default |
| `malformed_response` | non-JSON body, missing/mismatched `daily` fields, bad dates |
| `invalid_data` | negative / non-numeric precipitation |

Non-category outcomes stay as before: `unknown provider` → 422 with available-providers
hint; `offline` → 409 `skipped_offline`; no usable local data → existing 404/422
prediction errors. Provider exceptions never crash the app — they become structured
failures.

### Surfacing
- `POST .../refresh` responses (success *and* failure) now include `category`.
- Failure rows in `sync_log` carry a `[category: x]` tag in `message` (no DB migration);
  `GET /sync-log` and `GET /sources` parse it out (`category` field, clean message).
- Prediction response gains `last_sync_failure` — the location's most recent failed
  refresh within 24h, else `null` (deliberate additive schema extension; the Step 14
  exact-key test was updated accordingly).

### Freshness semantics (unchanged thresholds)
`current` ≤ 2 days · `recent` ≤ 7 · `stale` > 7 · **unavailable** = no usable local data
(structured error, never a fabricated prediction). Verified by direct tests on each
boundary. Staleness always refers to the **data**, never claimed as "stale weather".

### Frontend indicators (existing data-quality card — no second status system)
- **Cached (online):** "Cached rainfall data — from the local rainfall store · provider:
  open_meteo · latest observation … (… days old)"
- **Offline:** "Offline mode — using locally stored data · provider: … · latest …"
- **Stale:** same line plus "· **rainfall data is stale**" (`stale-indicator` testid),
  alongside the existing ⚠ warning and limitations.
- **Online failure + fallback:** "Online data unavailable (timeout) — using cached
  rainfall data. Last refresh attempt …" (`fallback-indicator` testid, only when
  `last_sync_failure` is present).
- **Unavailable:** existing structured error panel ("Prediction unavailable…").
Nothing is hidden at mobile widths (Step 22 layout untouched).

## Tests

Backend — `backend/tests/test_online_integration.py` (34 new) + updates:
- online integration: provider called, valid records stored (incl. `null` precip),
  per-row provenance, idempotent re-refresh (upsert, newest wins)
- failure categories: all 5 categories + legacy default, through service → 502 detail →
  sync-log; unknown provider 422; offline makes **zero** provider calls
- cache preservation: for **every** failure class, rows/latest-date/provenance unchanged
  and prediction probability identical; negative-precip batch → no partial write
- freshness: current/recent/stale boundaries + unavailable 404 + full provenance fields
- modes: `auto/online/offline` × connectivity — `cache_status` correct, probability
  identical everywhere
- adapter (mocked HTTP): timeout/network/5xx/malformed/invalid categories; success after retry

Frontend — 5 new Dashboard tests (stale indicator, fallback line, healthy-null, provider/
source/age facts) on top of the Step 23 indicator tests; advisory/localization suites
untouched and passing.

Totals: backend **151 passed** (117 + 34), frontend **63 passed** (59 + 4 + fixture
alignment), `npm run build` OK.

## Live smoke test (real backend + real provider)

`bash scripts/smoke_step24_25.sh` (performs one small real history refresh):
1. mode `auto` → internet reachable ✓
2. baseline prediction: prob 0.6055024, freshness current ✓
3. **real Open-Meteo archive refresh** → `ok, 29 records`, category null ✓
4. post-refresh: provider open_meteo, latest 2026-09-29, current, `last_sync_failure` null ✓
5. probability now 0.6066654 — changed **only because the stored input history genuinely
   changed** with fresh September data; identical across offline/online/auto (model untouched) ✓
6. unknown provider → structured 422 ✓
7. sync-log + sources expose categories ✓
(Steps 9–12 of the smoke matrix — provider failure with cache retention — are covered by
the mocked-HTTP and service-level regression tests above; a live negative test would mean
deliberately hammering the free provider.)

## Honest capability statement

- This integration does **not** establish 7–30 day forecast skill; the model remains a
  historical-pattern estimate with modest evaluation skill (see Step 11/12 docs).
- Reanalysis rows are labelled `kind="reanalysis"` and never presented as gauge
  observations or live measurements; cached data is never labelled live.
- Current model limitations (uncalibrated, per-year variability, presentation-only bands)
  remain exactly as documented in Steps 11–14.
- **Browser-only offline operation is not implemented** (no service worker/PWA/IndexedDB);
  the frontend requires the local backend to be reachable.

## Files relevant to Steps 26–29

- `backend/app/providers/base.py` — categories, ProviderError.category
- `backend/app/providers/open_meteo.py` — adapter with classified failures
- `backend/app/providers/registry.py` — provider registration point
- `backend/app/services/weather_service.py` — refresh pipeline, validation boundary, SyncResult.category
- `backend/app/api/routes.py` — refresh/mode/prediction endpoints, `last_sync_failure`, sync-log/sources parsing
- `backend/app/models.py` — SyncLog (message-tag approach; no schema change)
- `backend/app/schemas.py`, `backend/app/config.py` — request models, timeouts/URLs
- `backend/tests/test_online_integration.py`, `test_offline_cache.py`, `conftest.py` — test seams
- `scripts/smoke_step24_25.sh` — live verification harness
