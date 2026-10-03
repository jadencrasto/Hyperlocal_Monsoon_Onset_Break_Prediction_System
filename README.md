# SIH26086 — Monsoon Onset & Break Prediction System

## Current implementation

| Aspect | Status |
|---|---|
| **Geographic resolution** | 5 Maharashtra **district-HQ approximate coordinate points** (Pune, Nashik, Kolhapur, Chhatrapati Sambhajinagar, Nagpur). Grid-cell data (~10-25 km). NOT block/village/panchayat-scale. |
| **Onset analysis** | **Retrospective detection** from historical rainfall (type A). NOT future onset prediction. |
| **Break-risk prediction** | ML model trained and evaluated on historical rainfall features only (BSS 0.067 vs climatology; does NOT beat the simple dry-run heuristic). No forecast integration, no spatial features. |
| **Forecast data** | Live from Open-Meteo. Displayed as-is. **NOT fed into the prediction model.** |
| **Spatial ML** | The model treats all locations identically (pooled). No location-specific learning. |
| **Hierarchy** | state → district (populated) → block → panchayat (schema ready, no data). |
| **Frontend** | React 18 + TypeScript + Vite + Leaflet. 7 tabs: Overview, Rainfall Analysis, Onset & Forecast, Advisory, Risk Map, Historical, Model & Data. |
| **Advisory engine** | Deterministic rule engine: 7 rules, 5 Maharashtra kharif crops + generic, 3 languages (en/mr/hi). Informational only. |
| **Online/Offline** | Auto/online/offline modes with automatic fallback, cache TTL, failure cooldown, freshness indicators. |
| **Provider integration** | Open-Meteo (archive + forecast). Live refresh verified. Failure categories surfaced (network/timeout/http/malformed/invalid). |

## Windows setup (PowerShell)
```powershell
cd monsoon
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
Copy-Item .env.example .env

# Backend
cd backend ; python -m pytest -q ; cd ..

# Import pilot locations
python scripts\import_locations.py data\locations_pilot.csv

# Start backend
cd backend ; uvicorn app.main:create_app --factory --port 8000   # http://127.0.0.1:8000/docs

# Start frontend (separate terminal)
cd frontend ; npm install ; npm run dev   # http://localhost:5173
```

### Data download and model training (needs internet)
```powershell
# Verify the live provider works
curl -X POST http://127.0.0.1:8000/api/locations/1/forecast/refresh -H "content-type: application/json" -d "{\"provider\":\"open_meteo\"}"

# Download pilot history (resumable; start small)
python scripts\download_history.py --start-year 2005 --end-year 2024 --location-id 1

# Train + evaluate once ~15+ years are stored
python scripts\train_model.py
```
Afterwards `/api/model/evaluation` and `/api/locations/{id}/prediction/break-risk` work fully offline.

## API capabilities

See [docs/API.md](docs/API.md) for the full API reference.

| Endpoint | Type | Description |
|---|---|---|
| `/locations/{id}/monsoon/onset?year=` | Retrospective detection | Detects onset from stored history. Not a prediction. |
| `/locations/{id}/monsoon/onset-prediction` | Not implemented | Reserved for future onset prediction when forecast-driven model is built. |
| `/locations/{id}/prediction/break-risk` | ML prediction | Dry-spell break risk from historical rainfall features. Schema v1.0 with uncertainty, provenance, and limitations. |
| `/locations/{id}/forecast` | Third-party forecast | Cached Open-Meteo forecast with freshness/staleness. NOT an ML prediction. |
| `/locations/{id}/forecast/status` | Contract | Forecast availability and prediction integration status (currently: NOT integrated). |
| `/locations/{id}/data-quality` | Quality | Data quality assessment: gaps, staleness, coverage. |
| `/data-quality/coverage` | Quality | Coverage summary across all locations. |
| `/model/evaluation` | Report | Trained model evaluation report with baselines and skill metrics. |
| `/model/spatial-status` | Contract | Spatial awareness status (currently NOT spatially aware) and candidate approaches. |

## Testing

```
Backend:  192 passed (pytest)
Frontend:  79 passed (vitest, 11 test files)
Production build: tsc --noEmit + vite build OK
```

## Known limitations

- Grid-cell resolution (~10-25 km, not hyperlocal); onset/dry-spell rules are local proxies, not IMD declarations.
- Test-year rows are autocorrelated; datetimes stored as naive UTC.
- Mode preference lives in memory and resets on restart.
- The connectivity check tests only a TCP connection (a blocked provider shows as an error on refresh, not as "offline").
- The model has no spatial awareness — all locations are treated identically.
- The model does not beat the simple dry-run heuristic on the documented aggregate test Brier score.
- Model probabilities are over-predicted on average (calibration `mean_diff` ≈ +0.061).
- No browser-only offline operation (no service worker/PWA/IndexedDB); the frontend requires the local backend to be reachable.
- Block/panchayat boundaries and coordinates: not included. Only 5 approximate district-HQ points. Supply real block data via `scripts/import_locations.py`.
- IMD, CHIRPS, ERA5-direct, ECMWF S2S: not integrated (see docs/DATA_SOURCES.md).
- Forecast-driven prediction (capability C): not implemented. The model uses past local rainfall only.
