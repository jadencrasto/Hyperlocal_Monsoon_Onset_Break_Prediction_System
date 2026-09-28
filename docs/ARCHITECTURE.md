# Architecture

```
frontend (React/TS/Vite/Tailwind/Leaflet)   <-- NOT YET BUILT (Phase 6)
        | HTTP /api
backend/app
  api/routes.py                 thin handlers, validation, HTTP status mapping
  services/weather_service.py   fetch, cache, offline fallback, freshness, sync log
  providers/                    WeatherProvider interface + Open-Meteo (swap via registry)
  analysis/monsoon.py           onset + dry-spell detection (pure functions, configurable)
  ml/                           features (leakage-safe), train (time split + baselines), infer (offline)
  models.py, db.py              SQLAlchemy models, SQLite (WAL, foreign keys on)
scripts/                        import_locations, download_history, train_model
data/{raw,processed,app}  models/   kept out of Git
```

## Data labelling
Every API payload is typed: `historical_analysis` (stored history; `kind` = reanalysis|observation),
`third_party_forecast` (provider + `retrieved_at` + freshness), `own_model_prediction`.
Refresh failures go to `sync_log` and return HTTP 502 (provider) or 409 (offline). Nothing is substituted.
All forecast retrievals are kept (keyed by `retrieved_at`) so they can be scored against outcomes later.

## Capabilities (brief, section 5)
| | Status |
|---|---|
| A. Historical analysis | Implemented; unit-tested on constructed series; not yet run on real data. |
| B. ML prediction | Pipeline implemented. Target: >=5 consecutive days with rain < 2.5 mm within the next 7 days. Year-based train/val/test; baselines = climatology and dry-run-conditioned; Brier, log-loss, AUC, year-block bootstrap CI. **No real-data result exists yet.** |
| C. Forecast-driven prediction | **Not implemented.** Needs forecast/reforecast archives (e.g. ECMWF S2S). Third-party forecasts are shown as-is, labelled, and not fed into or validated against our model. |

## Definitions (configurable in `analysis/monsoon.py`)
- Onset: agronomic-style local proxy (>=20 mm in 3 days, first day >=1 mm, no 7-day dry run (<1 mm) in the next 20 days), searched Jun 1 - Jul 31. Not the IMD declaration.
- Dry spell: >=5 consecutive days < 2.5 mm within Jun 1 - Sep 30, tagged `local_dry_spell`. A meteorological monsoon break needs regional/synoptic information a single point cannot give.
- Resumption: first day at/above the threshold after a spell; null if the spell ends at a data gap or season end.

## Offline behaviour
Local SQLite + saved model + cached forecasts. `/api/mode` supports auto | online | offline. Offline: refresh returns 409, reads use cache with age and `freshness`. Map tiles are not stored locally; the future UI must show a coordinate fallback instead of promising offline maps.
