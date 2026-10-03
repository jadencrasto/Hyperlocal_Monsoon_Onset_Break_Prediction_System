# Data sources

Status legend: **Integrated** = code exists, is unit-tested, and live calls have been verified.
**Not integrated** = no verified programmatic access yet; nothing is faked.

## Open-Meteo - Integrated (`backend/app/providers/open_meteo.py`)
| Item | Detail |
|---|---|
| Supplies | Daily precipitation sum. Forecast endpoint (`/v1/forecast`) and archive endpoint (reanalysis-based history). |
| Coverage | Global. Archive marketed as reaching back ~80 years. |
| Forecast horizon | Up to 16 days (provider-documented). |
| Update frequency | Forecast models refresh through the day; this app treats cached data older than `MONSOON_FORECAST_STALE_HOURS` (default 12) as stale. |
| Key / registration | None. |
| Limits / terms | Free for **non-commercial** use, CC BY 4.0 attribution; a daily request cap applies (community sources cite ~10,000/day; confirm at open-meteo.com/en/terms). Check terms before any commercial or government deployment. |
| Village/block limits | Values are model grid cells (~10-25 km). A grid cell is not a block/village measurement, and reanalysis rainfall is not a gauge observation. History rows are labelled `kind="reanalysis"`. |
| Validation | Live archive and forecast calls verified (Step 24). Failure categories classified: network, timeout, HTTP, malformed, invalid data. |

## IMD (India Meteorological Department) - Not integrated
IMD publishes gridded rainfall, station data and warnings, but I have not verified a public, stable, unauthenticated API
suitable for automated use. Access may need a data request, registration or fees. `MONSOON_IMD_API_KEY` in `.env.example`
is only a placeholder that nothing reads. To add IMD: implement `WeatherProvider`, register it in `providers/registry.py`,
document its terms here. IMD gridded rainfall (0.25 deg) is the best target for real skill claims.

## CHIRPS - Not integrated
Satellite-gauge rainfall (~0.05 deg) distributed as files by UCSB CHC. Good for historical training; needs a file-download
ingester (not an API). The host was blocked in the build sandbox, so terms/paths were not checked.

## ERA5 (direct, Copernicus CDS) - Not integrated
Requires a free CDS account and API key and uses a queued request system. Open-Meteo's archive already exposes reanalysis
for point queries; direct ERA5 is only needed for extra atmospheric variables (winds, humidity, etc.).

## ECMWF S2S reforecasts - Not integrated (needed for genuine 2-4 week forecasting)
Required for a defensible extended-range (7-30 day) monsoon forecast with hindcast evaluation. Access is via the S2S
database with registration and licence conditions. Until integrated, **the project does not claim a validated 7-30 day
forecast** (see docs/ARCHITECTURE.md, capability C).
