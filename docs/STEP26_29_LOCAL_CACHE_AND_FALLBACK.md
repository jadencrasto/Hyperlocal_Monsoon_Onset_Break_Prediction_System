# Steps 26–29 — Local Caching, Offline Prediction, Fallback & Freshness (SIH26086)

**Date:** 2026-10-01 · **Scope:** automated Online → Offline fallback, local observation caching with TTL & failure cooldown, expired cache rejection, and minimal frontend status indicators.
**No model training, probability-math, schema-version, or advisory architecture changes.** No new dependencies.

## Architecture

```
                      Client Prediction Request
                                 │
                         Effective Mode?
                        /               \
                  "online"             "offline"
                     │                     │
           Cache within TTL or             │
           Failure Cooldown Active?        │
              /            \               │
            YES            NO              │
            │               │              │
      Use Fresh Cache   Try Live API       │
      (Skip Provider)   (Open-Meteo)       │
            │             /      \         │
            │         SUCCESS   FAILURE    │
            │            │         │       │
            │      Write Cache  Record Err │
            │      is_live=true Cooldown   │
            │            │         │       │
            └───────┬────┴─────────┴───────┘
                    │
            Check Cache Validity
                    │
          ┌─────────┴─────────┐
        VALID              INVALID / STALE
          │                   │
    Run ML Model      Return Structured Error
          │           - 404 no_stored_history
     Return 200       - 422 cached_data_too_old
   Prediction API     - 422 insufficient_or_gappy_history
          │
      Dashboard
  (Status Indicator:
   Online/Offline,
   Live/Cached,
   Update Time, Source)
```

## 1. Requirement 26 — Local Caching

* **Authoritative Store**: SQLite tables `daily_rainfall` and `forecast_rainfall` store all observations, timestamps (`fetched_at`), provider provenance, and values.
* **Configurable Policies**:
  * `cache_ttl_minutes` (`MONSOON_CACHE_TTL_MINUTES`, default `15.0`): prevents redundant upstream queries when data was refreshed within the TTL window.
  * `api_cooldown_seconds` (`MONSOON_API_COOLDOWN_SECONDS`, default `60.0`): when an upstream failure occurs, throttles retries to prevent hammering failed APIs.
  * `max_cache_age_days` (`MONSOON_MAX_CACHE_AGE_DAYS`, default `30`): maximum allowable observation age for offline predictions before rejection.
* **Cache Manager**: `backend/app/services/cache_manager.py` abstracts TTL checks, circuit-breaker cooldowns, and integrity validation.

## 2. Requirement 27 — Offline Prediction

* When offline or when upstream fails, prediction executes against the local SQLite store without fabricating data or using fake predictions.
* **Preserved Schema**: Top-level keys remain exactly the 15 versioned keys defined in Step 14.
* **Stale / Expired Cache Rejection**: If local data is older than `max_cache_age_days`, the API returns HTTP 422 `cached_data_too_old` with an actionable hint instead of silently predicting on outdated data.

## 3. Requirement 28 — Automatic Online → Offline Fallback

* Seamless automatic flow without requiring manual mode switching:
  1. If `online`, attempts live fetch if outside TTL and not in cooldown.
  2. If live fetch succeeds, SQLite cache is updated and prediction runs with `is_live=true` and `cache_status="live"`.
  3. If live fetch fails (timeout, network, HTTP 5xx), the failure is recorded in `sync_log`, cooldown is triggered, and the pipeline automatically falls back to valid local cache with `cache_status="cached"` and `last_sync_failure` surfaced.
  4. Once connectivity or provider recovers, live fetching automatically resumes on subsequent requests outside cooldown.

## 4. Requirement 29 — Data Freshness / Status Indicators

* Minimal, professional status strip in `frontend/src/DataStatusBadge.tsx`:
  * **Connectivity**: `ONLINE` (green dot) / `OFFLINE` (slate dot).
  * **Data State**: `Live data` (blue chip) / `Using cached data` (slate chip).
  * **Update Timestamp**: Human-friendly relative age (`Updated 4 min ago`, `Last updated 2 hr ago`).
  * **Data Source**: Source chip (`source: open_meteo`).
  * **Stale / Offline Error State**: When cache exceeds maximum age, displays `OFFLINE · Cached data too old · Prediction unavailable`.

## 5. Verification & Tests

* **Backend**: `backend/tests/test_requirements_26_29.py` (10 test cases) + full test suite:
  ```bash
  python3 -m pytest -q
  # 161 passed in 5.64s
  ```
* **Frontend**: `frontend/src/Dashboard.test.tsx` (new status indicator suite) + full test suite & production build:
  ```bash
  cd frontend && npm test -- --run && npm run build
  # 66 passed in 1.14s; production build succeeded
  ```
* **Live Smoke Test**: Real backend verification against Open-Meteo with live cache update, offline toggle, and mode probability stability:
  ```bash
  bash scripts/smoke_step26_29.sh
  # SMOKE2629_DONE (Online live fetch prob: 1.054e-15, Offline cached prob: 1.054e-15, identical across modes)
  ```
