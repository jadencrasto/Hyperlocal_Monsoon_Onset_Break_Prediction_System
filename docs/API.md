# API (interactive docs at http://127.0.0.1:8000/docs when running). Base path `/api`.

## System
| Method | Path | Purpose |
|---|---|---|
| GET | /health | status, DB, effective mode, actual operating state, model present, spatial awareness, geographic scope |
| GET/PUT | /mode | connectivity preference `auto`, `online`, `offline` |

## Locations & data
| Method | Path | Purpose |
|---|---|---|
| GET | /locations, /locations/{id} | locations (optional `level`, `state`); includes `parent_id` |
| GET | /locations/tree | full hierarchy: state → district → (block → panchayat when data exists) |
| GET | /locations/{id}/children | direct children in the hierarchy |
| GET | /locations/{id}/coverage | rainfall availability for a location and descendants |
| GET | /locations/{id}/history?start&end | stored rainfall with `kind` and provider |
| POST | /locations/{id}/history/refresh | fetch history (409 offline, 502 provider failure with `category`) |
| GET | /locations/{id}/forecast | latest cached third-party forecast with age/freshness |
| POST | /locations/{id}/forecast/refresh | fetch forecast (409 offline, 502 provider failure) |
| GET | /locations/{id}/forecast/status | forecast freshness + prediction integration status (currently: NOT integrated) |

## Monsoon analysis & prediction
| Method | Path | Purpose |
|---|---|---|
| GET | /locations/{id}/monsoon/onset?year | **Retrospective** onset detection from stored history (type: `observed_onset_detection`). NOT a prediction. |
| GET | /locations/{id}/monsoon/onset-prediction | **NOT IMPLEMENTED.** Reserved for future forecast-driven onset prediction. |
| GET | /locations/{id}/monsoon/dry-spells?year&after_onset | local dry spells + resumption |
| GET | /locations/{id}/monsoon/break-risk?as_of | ML dry-spell risk prediction (works offline; uses historical rainfall only, no forecast data) |

## Model & evaluation
| Method | Path | Purpose |
|---|---|---|
| GET | /model/evaluation | saved evaluation report (404 until trained) |
| GET | /model/spatial-status | spatial awareness status: currently NOT spatially aware, candidate approaches listed |

## Data quality
| Method | Path | Purpose |
|---|---|---|
| GET | /locations/{id}/data-quality | gaps, staleness, impossible values, coverage for one location |
| GET | /data-quality/coverage | coverage summary across all district locations |

## Observability
| Method | Path | Purpose |
|---|---|---|
| GET | /sources | providers, last success/error (+ failure `category`), not-integrated list |
| GET | /sync-log?limit | recent sync attempts (+ parsed failure `category`) |

## Key distinctions
- **Onset detection** (`/monsoon/onset`): Analyses past data to identify when onset occurred. Type A (retrospective).
- **Onset prediction** (`/monsoon/onset-prediction`): Would predict future onset. NOT IMPLEMENTED. Type B (prospective).
- **Break-risk prediction** (`/monsoon/break-risk`): ML model prediction of dry-spell risk. Uses historical rainfall features ONLY. No forecast data, no spatial features.
- **Forecast data** (`/forecast`, `/forecast/status`): Third-party weather forecast. Displayed as-is. NOT fed into the prediction model.
