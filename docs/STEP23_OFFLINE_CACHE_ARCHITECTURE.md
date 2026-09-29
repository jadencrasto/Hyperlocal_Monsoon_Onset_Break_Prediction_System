# Step 23 — Offline / Cache Architecture (SIH26086)

**Date:** 2026-10-01 · **Scope:** cache provenance + frontend indicators on the *existing*
mode/refresh machinery. **No model, probability, schema-version, advisory, or Step-22
changes.** No new infrastructure.

## Architecture (unchanged shape, clearer contract)

```
External provider (Open-Meteo)          [Step 24 will extend this side]
        ↓  (online only; validated before write)
FastAPI WeatherService  ← mode: auto|online|offline  (existing Step-2 mechanism, reused)
        ↓
SQLite local store  (data/app/monsoon.db)  ← THE authoritative local cache
        ↓  (prediction always reads here)
Prediction API (schema v1.0)  →  data_status{... cache_status, provider}
        ↓
Dashboard / Map / Advisory  →  factual data-situation line
```

The SQLite database **is** the cache. Rainfall rows keep per-row provenance
(`provider`, `kind`, `fetched_at`); no Redis, no IndexedDB, no service worker, no second
database. Refreshes already validated-before-write and logged to `sync_log`
(`ok | error | skipped_offline`) — Step 23 adds a write-boundary guard and surfaces the
facts to the UI.

## Online vs offline (existing mechanisms, reused)

- `GET/PUT /api/mode` — preference `auto | online | offline`; `auto` detects connectivity
  via two Open-Meteo hosts (15 s cached check). **No second mode mechanism was added.**
- Prediction math is mode-independent: the model reads the same local series either way.
  Locked by tests and verified live (identical probability in every mode).

## `data_status` contract (extended, additive)

| Field | Meaning |
|---|---|
| `source` | `stored_reanalysis_history` (unchanged) |
| `provider` | **new** — provider of the most recent stored row (real provenance from `daily_rainfall`) |
| `latest_rainfall_date`, `data_age_days`, `freshness` | unchanged semantics; `current` still means age ≤ 2 days |
| `input_days_used`, `input_completeness` | unchanged |
| `cache_status` | **new** — `offline` when effective mode is offline, else `cached` |

Deliberate choices: the prediction **always** reads the local store, so `cache_status` is
never `live` (cached data is never presented as live); `unavailable` does not appear here
because unavailable data produces the existing structured errors (`404 no_stored_history`,
`422 insufficient_or_gappy_history`, `503 model_unavailable`) instead of a prediction.

## Cache / fallback behavior

- External fetches stay unavailable-in-sandbox; when the network or the provider fails,
  refresh returns `502 provider_failure` and **the local store is untouched**.
- A failed refresh can never delete or partially overwrite valid rows: the provider
  parses and validates the response *before* any DB statement, Step 23 adds a
  reject-on-invalid-values guard (`negative precipitation → 502, zero rows written`),
  and DB errors roll back. Successful writes are upserts keyed by
  `(location, date, kind, provider)` with per-row provenance preserved.
- Explicit offline mode skips provider calls entirely (`409 skipped_offline`) and serves
  the local store as-is.

## No usable cache

Too-old or gappy local data does **not** degrade into a fabricated prediction: the
existing freshness warning flags it (`data_warning`), and missing/gappy history returns
the same structured errors as before. Offline mode changes data *availability messaging*,
never prediction validity rules.

## Frontend indicators (existing data-quality card, no separate system)

A factual line at the top of the Data quality panel (`data-testid="cache-indicator"`):

- Online: **Cached rainfall data** — from the local rainfall store · provider: open_meteo ·
  latest observation 2026-09-29 (1 days old)
- Offline: **Offline mode** — using locally stored data · provider: … · latest observation …
- Stale/incomplete data still raises the existing ⚠ warning line; unavailable data still
  renders the existing structured error panel ("Prediction unavailable…").

Wording is deliberately non-alarming and never claims live weather (tests assert the
absence of "live"). Type additions to `Prediction["data_status"]` are optional fields, so
older payloads render with `provider: unknown`.

## Tests

Backend — `backend/tests/test_offline_cache.py` (15 new, mapping to the required cases):

1. valid local cached data usable (online *and* offline)
2. failed external refresh preserves local rows, latest date, and the prediction
3. cache/freshness metadata reported (`cache_status`, `provider`, full field set)
4. unavailable/incomplete local data → `404` / `422` (no fabricated prediction)
5. identical probability across `auto/online/offline` × connectivity (5 combos)
6. successful refresh preserves per-row provenance; newest-row provider reported
7. invalid external values rejected with zero writes (incl. partial-batch case)

Frontend — 5 new `Dashboard` tests: cached indicator + provider, offline indicator,
cached + stale warning pairing (external-failure-fallback presentation), unavailable-data
state, and graceful defaults for absent fields. **No existing tests deleted.**

Totals: backend **117 passed** (102 + 15), frontend **59 passed** (54 + 5),
`npm run build` OK.

## Smoke test (live, real DB)

`bash scripts/smoke_step23.sh` (read-only): mode → prediction online (`cache_status:
cached`, prob 0.6055024) → PUT offline → prediction again (**identical probability**,
`cache_status: offline`) → offline refresh 409 → unknown provider 422 → local history
still served. Headless-Chrome UI check: online shows "Cached rainfall data · provider:
open_meteo · latest observation 2026-09-29 (1 days old)"; offline shows "Offline mode ·
using locally stored data".

## Known limitations

- **No browser-only offline operation.** If the backend is unreachable, the frontend
  cannot render predictions (no service worker/PWA/IndexedDB, deliberately — the
  architecture doesn't require it and adds none).
- `cache_status` reflects *mode*, not per-request network state; in `auto` mode a
  just-flapped connection may briefly mislabel (15 s connectivity cache, pre-existing).
- Historical/`reanalysis` data is labeled as such everywhere; this step adds no new data
  sources and no forecast skill.
- No automatic background refresh: refreshing remains a manual API action
  (`POST .../refresh`); UI wiring of a refresh button is future work if wanted.

## Files relevant to Step 24 (external provider integration)

- `backend/app/providers/base.py`, `backend/app/providers/registry.py` — provider interface + registration
- `backend/app/services/weather_service.py` — `refresh_history/refresh_forecast`, mode logic, validation boundary
- `backend/app/api/routes.py` — `/history/refresh`, `/forecast/refresh`, `/mode`, `data_status`
- `backend/app/schemas.py` — refresh request models
- `backend/app/config.py` — provider URLs/timeouts
- `backend/tests/test_offline_cache.py`, `backend/tests/conftest.py` (FakeProvider) — test seams
