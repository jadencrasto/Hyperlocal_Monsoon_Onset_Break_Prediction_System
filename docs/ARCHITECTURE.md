# Architecture

```
frontend (React 18 / TypeScript / Vite 5 / Leaflet 1.9)
  src/App.tsx               shell: 7-tab navigation, location selector, status bar
  src/Dashboard.tsx          prediction summary, evidence, data quality, risk badges
  src/RiskMap.tsx            Leaflet map with severity-colored district markers
  src/HistoryCharts.tsx      observed rainfall bars, dry-spell overlay, season selector
  src/AdvisoryPanel.tsx      deterministic advisory engine (en/mr/hi), crop templates
  src/ForecastSection.tsx    third-party forecast display (NOT fed into ML model)
  src/OnsetSection.tsx       retrospective onset detection viewer
  src/RainfallAnalysis.tsx   rainfall analysis and statistics
  src/TechnicalDiagnostics.tsx  model benchmarks, data quality audit, sync log
  src/SystemStatusBar.tsx    operating mode (online/offline/degraded)
  src/DataStatusBadge.tsx    live/cached/stale data status indicator
  src/api.ts                 typed API client for all backend endpoints
  src/advisory/              rule engine, crop templates, locales (en/mr/hi)
        | HTTP /api (Vite dev proxy → localhost:8000)
backend/app
  api/routes.py              thin handlers, validation, HTTP status mapping
  services/weather_service.py  fetch, cache, offline fallback, freshness, sync log
  services/data_quality.py   data validation: gaps, staleness, coverage, impossible values
  services/cache_manager.py  TTL-based caching, failure cooldown, cache validity
  services/location_service.py  hierarchy tree, parent-child validation, coverage
  providers/                 WeatherProvider interface + Open-Meteo adapter (swap via registry)
  analysis/monsoon.py        onset + dry-spell detection (pure functions, configurable)
  ml/                        features (leakage-safe), train (time split + baselines), infer (offline)
  ml/spatial.py              spatial experiment boundary (documents: no spatial features in model)
  models.py, db.py           SQLAlchemy models, SQLite (WAL, foreign keys on)
scripts/                     import_locations, download_history, train_model
data/{raw,processed,app}  models/   kept out of Git
```

## Data flow

```
External Weather API (Open-Meteo)
        ↓  (online only; validated before write)
Provider Adapter (open_meteo.py — URLs, JSON parsing, retries, failure categories)
        ↓
Validation (types, dates, precip >= 0, field presence)
       /        \
    valid       invalid/failure
      |              |
      v              v
SQLite local store   Structured failure (SyncResult.category → sync_log → API)
      |
      ↓
Feature generation (r1, sum3, sum7, sum14, sum30, rainy_frac14, dry_run, doy_sin, doy_cos)
      ↓
ML model (LogisticRegression, StandardScaler pipeline)
      ↓
Prediction API (schema v1.0, uncertainty, limitations, provenance)
      ↓
React frontend (7 tabs: Overview, Rainfall, Onset & Forecast, Advisory, Risk Map, Historical, Model & Data)
```

## Geographic model
```
state (grouping node, no coordinates)
  └── district (5 pilot points: approximate district-HQ coords, grid-cell data ~10-25 km)
        └── block (schema ready, NO real data)
              └── panchayat (schema ready, NO real data)
```
Current resolution: **district-HQ coordinate points only**. The grid-cell data from Open-Meteo
is approximately 10-25 km resolution. This is NOT hyperlocal, block-level, or village-level.
Block/panchayat hierarchy levels are schema-ready but empty.

## Data labelling
Every API payload is typed: `observed_onset_detection` (stored history; `kind` = reanalysis|observation),
`third_party_forecast` (provider + `retrieved_at` + freshness), `break_risk_prediction` (own ML model).
Refresh failures go to `sync_log` and return HTTP 502 (provider) or 409 (offline). Nothing is substituted.
All forecast retrievals are kept (keyed by `retrieved_at`) so they can be scored against outcomes later.

## Capabilities
| | Status |
|---|---|
| A. Historical analysis | Implemented; unit-tested; onset detection is **retrospective**, not predictive. |
| B. ML break-risk prediction | Pipeline implemented and trained. Target: >=5 consecutive days with rain < 2.5 mm within the next 7 days. Year-based train/val/test; baselines = climatology and dry-run-conditioned; Brier, log-loss, AUC, year-block bootstrap CI. BSS 0.067 vs climatology; model does NOT beat the dry-run heuristic. Model uses **only temporal/rainfall features** — no spatial features, no forecast data. |
| C. Forecast-driven prediction | **Not implemented.** Needs forecast/reforecast archives (e.g. ECMWF S2S). Third-party forecasts are shown as-is, labelled, and not fed into or validated against our model. |
| D. Onset prediction | **Not implemented.** `/monsoon/onset` is retrospective detection only. `/monsoon/onset-prediction` returns NOT_IMPLEMENTED. |
| E. Spatial awareness | **Not implemented.** Model treats all locations identically (pooled). See `ml/spatial.py` for candidate approaches. |
| F. Advisory engine | Implemented. Deterministic rule engine over the prediction API. 7 rules, 5 crops + generic, 3 languages (en/mr/hi). Informational only. |
| G. Online/Offline operation | Implemented. Auto/online/offline modes, automatic online→offline fallback, cache TTL, failure cooldown, freshness indicators. |

## Definitions (configurable in `analysis/monsoon.py`)
- Onset: agronomic-style local proxy (>=20 mm in 3 days, first day >=1 mm, no 7-day dry run (<1 mm) in the next 20 days), searched Jun 1 - Jul 31. Not the IMD declaration. This is **retrospective detection**, not prediction.
- Dry spell: >=5 consecutive days < 2.5 mm within Jun 1 - Sep 30, tagged `local_dry_spell`. A meteorological monsoon break needs regional/synoptic information a single point cannot give.
- Resumption: first day at/above the threshold after a spell; null if the spell ends at a data gap or season end.

## Online/Offline behaviour
Local SQLite + saved model + cached forecasts. `/api/mode` supports auto | online | offline.
- **Online:** Live provider fetch → validate → persist → prediction from updated cache. Failure → cooldown → fallback to cache.
- **Offline:** Refresh returns 409, reads use cache with age and `freshness`. Stale cache older than `max_cache_age_days` rejected with 422.
- **Auto:** Connectivity detected via TCP to Open-Meteo hosts (15s cached check). Falls back to offline if unreachable.
- Map tiles (OSM) require network; no offline tile cache.

## Data quality
`/api/locations/{id}/data-quality` reports gaps, staleness, impossible values, null values, duplicates, coverage.
`/api/data-quality/coverage` reports data coverage across all district locations.
Data is never silently repaired — issues are flagged for callers to handle.
