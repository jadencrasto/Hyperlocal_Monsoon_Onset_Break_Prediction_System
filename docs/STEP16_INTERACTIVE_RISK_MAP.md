# Step 16 — Interactive Risk Map (SIH26086)

**Date:** 2026-09-29 · **Scope:** demo-ready map over the existing APIs. **No backend changes;
no ML changes; no fabricated values or boundaries.** Steps 17–23 not started.

## Frontend scaffold (created in this step)

`frontend/` was empty (the React app had never been scaffolded), so a minimal Vite + React 18 +
TypeScript app was created around the map:

- Vite 5 + `@vitejs/plugin-react`, dev proxy `/api -> http://127.0.0.1:8000`
- **Map library: Leaflet 1.9.4 via react-leaflet 4.2.1** (OpenStreetMap tiles)
- Vitest 2 + Testing Library (jsdom) for the focused tests
- `npm run dev` (5173) · `npm run build` (tsc + vite build, verified) · `npm test`

## Architecture

```
src/api.ts        typed client: fetchTree(), fetchPrediction(id), pilotDistricts(tree)
src/RiskMap.tsx   map + side panel + detail card; per-location prediction loading
src/App.tsx       header + disclaimer
src/styles.css    layout, severity badges, small-screen stack (@media <=800px)
```

`pilotDistricts()` walks `GET /api/locations/tree` and returns only nodes with
`level === "district" && has_data && latitude != null` — locations are **fully dynamic**;
nothing (names, coordinates, predictions) is hardcoded. The tree's `levels_present`
honestly reports that block/panchayat have no data yet; **no boundaries are fabricated** —
districts render as severity-colored circle markers, and the architecture (node-based
iteration) is polygon-ready if authoritative boundary data is added later.

## Prediction loading

For each pilot district: `GET /api/locations/{id}/prediction/break-risk` (Step 14 schema
v1.0). Failures are **isolated per location** — one 4xx/5xx never blanks the map; the failed
location shows a neutral marker, "(n/a)" in the list, and an error card when selected.

## UI states

| State | Behavior |
|---|---|
| loading | "Loading locations…" panel while the tree loads; "Loading predictions…" while per-location fetches are in flight |
| empty | Explicit message when no district has stored data (points to `download_history.py`) |
| API error (tree) | Full-width "Map unavailable" error state |
| API error (one prediction) | Neutral marker + "(n/a)" + error card (`detail-error`) |
| stale data | ⚠ flag in list and card ("rainfall data is N days old — treat with caution") straight from `data_status.freshness` |
| incomplete input | `input_completeness < 1` renders "⚠ gaps in recent rainfall" |
| provenance | Card shows model name, trained-through, trained locations, BSS vs climatology, and the `risk_bands` note that bands are **not calibrated thresholds** |

Severity styling uses only the API's three categories (low #2e7d32 / moderate #f9a825 /
high #c62828) — no new thresholds. A standing disclaimer marks these as historical-pattern
estimates, not forecasts; no 7–30 day skill is claimed anywhere.

Clicking a marker or list row opens the detail card (probability, category, date, freshness,
completeness, model provenance) — the same data shape Step 17's dashboard will consume, so
the card can evolve into the dashboard entry point without re-plumbing.

## APIs consumed

- `GET /api/locations/tree` (Step 15)
- `GET /api/locations/{id}/prediction/break-risk` (Steps 13–14)

## Visual smoke test (real backend, real DB)

Headless Chrome 1360×900 against `vite dev` + live uvicorn (`docs/step16_smoke.png`):

- all 5 districts rendered: Pune, Nashik, Kolhapur, Chhatrapati Sambhajinagar, Nagpur
- live probabilities in the side panel (46%–64%, model = Step 11 logistic, trained through
  2025-09-23); Leaflet tiles + fitBounds confirmed (2,945 distinct colors, terrain pixels sampled)
- **error path exercised for real:** Pune's stored history ends 2026-09-05, so the API
  returns 422 `insufficient_or_gappy_history`; the map rendered Pune as "(n/a)" with a
  neutral marker while the other four districts showed predictions — graceful degradation
  confirmed against production data, not a mock

## Tests

- Frontend: `npx vitest run` → **4 passed** (pilot-district extraction incl. level/has_data
  filtering and empty-tree case; loading-state render; severity color completeness)
- `npm run build` → tsc strict + production bundle OK
- Backend suite untouched: **102 passed** (no backend changes in this step)

## Limitations / notes for Step 17

- District markers only; block/panchayat polygons await authoritative boundary data.
- Predictions are fetched on mount, not auto-refreshed; Step 17 should decide on a refresh
  policy (manual refresh button at minimum).
- Pune currently can't produce a prediction (stored history gap after 2026-09-05); refreshing
  2026 history (flagged since Step 13) fixes the map's one "(n/a)" marker.
- The detail card is the seed of the Step 17 dashboard: promote it to a route/panel with
  historical charts rather than duplicating its data plumbing.
- OSM tiles require network; the offline app shell is explicitly later (roadmap) work.
