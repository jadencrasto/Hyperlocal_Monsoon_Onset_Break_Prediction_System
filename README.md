# SIH26086 - Hyperlocal Monsoon Onset & Break Prediction (work in progress)

**Status: backend, data layer and ML baseline pipeline are built and tested. The React dashboard is NOT built yet.
No real-data model has been trained, so there are no accuracy figures. Do not present any prediction as validated.**

## Windows setup (PowerShell)
```powershell
cd monsoon-sih
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
cd backend ; python -m pytest -q ; cd ..                 # expect 38 passed
python scripts\import_locations.py data\locations_pilot.csv
cd backend ; uvicorn app.main:create_app --factory --port 8000   # http://127.0.0.1:8000/docs
```
Manual steps (need internet, on your machine):
```powershell
# 5. verify the live provider works (one small call)
curl -X POST http://127.0.0.1:8000/api/locations/1/forecast/refresh -H "content-type: application/json" -d "{\"provider\":\"open_meteo\"}"
# 6. pilot history (resumable; start small)
python scripts\download_history.py --start-year 2005 --end-year 2024 --location-id 1
# 7. train + evaluate once ~15+ years are stored
python scripts\train_model.py
```
Afterwards `/api/model/evaluation` and `/api/locations/1/monsoon/break-risk` work fully offline.

## Manual end-to-end demo
1. Start the API. 2. `PUT /api/mode {"preference":"online"}`, refresh the forecast, `GET forecast` shows `freshness: fresh`.
3. `PUT /api/mode {"preference":"offline"}`: refresh returns 409, `GET forecast` still returns the cached forecast with its age.
4. Lower `MONSOON_FORECAST_STALE_HOURS` (or wait) to see `freshness: stale`. 5. Try `monsoon/onset?year=2023`, `dry-spells?year=2023`, `break-risk`.

## Implemented and tested
Provider interface + Open-Meteo provider (mocked-HTTP tests: retries, 429, malformed payloads); SQLite storage with upsert;
sync log; online/offline modes; freshness; onset and dry-spell detection (constructed-series tests); leakage-safe features
(a test proves future data cannot change features or predictions); year-based split; baselines; API including failure paths.
**38 tests passed** in the build sandbox, plus a live-server smoke test (health, locations, provider-failure path).

## NOT verified / incomplete
- **No live Open-Meteo call has succeeded** (the sandbox blocks the host). The smoke test confirmed the failure path: HTTP 502, nothing stored, error logged.
- Frontend (Overview, Rainfall Analysis, Map, Model Evaluation, Data Sources), charts, Leaflet, offline app shell: not started.
- Block/village boundaries and coordinates: not included. Only 5 approximate district-HQ points. Supply real block data (e.g. LGD/Census-derived) via `scripts/import_locations.py`.
- IMD, CHIRPS, ERA5-direct, ECMWF S2S: not integrated (docs/DATA_SOURCES.md).
- Forecast-driven prediction (capability C): not implemented. The model uses past local rainfall only.
- Model metrics: none yet. Reanalysis rainfall is not gauge truth; skill on it does not automatically transfer.

## Known limitations
Grid-cell resolution; onset/dry-spell rules are local proxies, not IMD declarations; test-year rows are autocorrelated;
datetimes stored as naive UTC; mode preference lives in memory and resets on restart; the connectivity check tests only a
TCP connection (a blocked provider shows as an error on refresh, not as "offline").
