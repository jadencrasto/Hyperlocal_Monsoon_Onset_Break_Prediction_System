# API (interactive docs at http://127.0.0.1:8000/docs when running). Base path `/api`.

| Method | Path | Purpose |
|---|---|---|
| GET | /health | status, DB, effective mode, model present |
| GET/PUT | /mode | connectivity preference `auto`, `online`, `offline` |
| GET | /locations, /locations/{id} | locations (optional `level`, `state`) |
| GET | /locations/{id}/history?start&end | stored rainfall with `kind` and provider |
| POST | /locations/{id}/history/refresh | fetch history (409 offline, 502 provider failure) |
| GET | /locations/{id}/forecast | latest cached third-party forecast with age/freshness |
| POST | /locations/{id}/forecast/refresh | fetch forecast (409 offline, 502 provider failure) |
| GET | /locations/{id}/monsoon/onset?year | local onset proxy |
| GET | /locations/{id}/monsoon/dry-spells?year&after_onset | local dry spells + resumption |
| GET | /locations/{id}/monsoon/break-risk?as_of | own-model dry-spell risk (works offline) |
| GET | /model/evaluation | saved evaluation report (404 until trained) |
| GET | /sources | providers, last success/error, not-integrated list |
| GET | /sync-log?limit | recent sync attempts |
