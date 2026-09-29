# Steps 17–18 — Prediction Dashboard & Historical Charts (SIH26086)

**Date:** 2026-09-29 · **Scope:** dashboard + historical view on the Step 16 frontend.
**No ML, prediction-semantics, schema, or hierarchy changes.** Steps 19–23 not started.
The model remains a historical break-risk model — no 7–30 day forecast-skill claims anywhere.

## Step 17 — Prediction dashboard

### Architecture (reuse, no second data layer)

`App.tsx` is the shared shell: it loads the location tree **once** and passes districts to
both the map and the new location selector. Selecting on the map or in the selector drives
the same `selectedId` state; the view is tabbed (`Map` / `Dashboard`) and deep-linkable via
`?tab=dashboard&loc=<id>` (useful for demos and Step 19+ navigation). `RiskMap` gained
optional `selectedId`/`onSelect` props — Step 16 behavior is preserved when they are omitted.

Components:

- `src/Dashboard.tsx` *(new)* — summary / evidence / data-quality panels for the selected
  location; pure function of `locationId`.
- `src/HistoryCharts.tsx` *(new)* — Step 18 observed-history view (below the dashboard).
- `src/api.ts` *(extended, same client)* — added `fetchHistory`, `fetchDrySpells`,
  `fetchCoverage`, typed `HistoryRecord`/`DrySpell`/`Coverage`, and a shared `errorText()`
  that unwraps the backend's structured `{detail:{error,hint}}` errors.
- `src/App.tsx` *(rewritten)* — shell: selector + tabs + shared tree.
- `src/RiskMap.tsx` *(small edit)* — optional controlled-selection props.
- `src/styles.css` *(extended)* — toolbar, tabs, dashboard grid, history chart, legend.

### Main prediction summary (all values verbatim from the API)

Location (+state), prediction date (labeled **model as-of**), probability (big number),
risk category badge, event description with horizon, model name + trained-through,
`uncertainty.evidence_level`.

### Risk presentation

Uses `risk_bands` from the API; the note line renders the bands plus the API's own text that
they are **presentation bands, not calibrated decision thresholds**. No new thresholds.

### Evidence / uncertainty (Step 14 `uncertainty` object)

Displayed with an explicit framing paragraph:

> These are **population-level evaluation results over historical test years** … **not an
> uncertainty interval around this individual prediction**, which is not available.

Fields: evidence level · evaluation BSS vs climatology · BSS 95% CI (labeled year-block
bootstrap) · number of test years · calibration (interpretation + mean predicted vs observed)
· per-year stability (BSS min–max across N years, negative-year count) · **individual
prediction interval: explicitly "Not available — the pipeline fits a point-probability model
only"** (no interval invented).

### Data-quality panel

Source · latest rainfall date (labeled *observed*) · data age · freshness · input days used ·
input completeness. When `freshness === "stale"` or `input_completeness < 1`, a warning banner
("Rainfall data is N days old / Recent rainfall has gaps. Treat this prediction with
caution.") is shown — warnings are never hidden. Model caveats + limitations are in a
collapsed `<details>` (present, unobtrusive).

### Error states

`dash-loading` while fetching; a structured error panel distinguishes "Prediction unavailable
for this location" (no_stored_history / model_unavailable / insufficient_or_gappy_history /
out_of_season / future_date) from a generic "Dashboard error"; the app shell separately
handles tree failure (`app-error`) and unknown locations (404 text via `errorText`).
One location's failure never affects others — the selector and map remain usable.

## Step 18 — Historical charts

### Data-rule inspection (done first)

Existing APIs were inventoried before any chart work: `GET /history` (daily observed
rainfall, provenance noted), `GET /monsoon/dry-spells` (**the backend's scientific dry-spell
definition** — ≥5 consecutive days <2.5 mm within a 7-day window; the frontend does not
re-define events), and `GET /locations/{id}/coverage` (real min/max stored dates).

**Historical prediction probabilities are NOT available** — the backend computes predictions
on demand and stores none. Accordingly, **no probability timeline is manufactured**. The
panel states this explicitly in its caption ("the model computes probabilities on demand and
stores none") and the UI separates *observed history* (charts) from the *current prediction*
(dashboard above).

### Backend endpoint added

**None.** The existing endpoints were sufficient; nothing was added to the backend, and the
full backend suite passes untouched.

### Charts implemented

- **Observed rainfall chart** (`rainfall-chart`): daily mm/day bars for a monsoon season
  (Jun 15–Sep 30), colored wet (≥2.5 mm) vs dry, with hover tooltips per day; dry-spell event
  starts outlined in red with full spell detail in the tooltip; legend + wet-day share.
- **Season selector**: Latest / Previous / 5 back / 10 back, bounded by real coverage.
- **Empty state** names the stored coverage window ("stored coverage starts …, ends …") so a
  blank season is explained, not mysterious; error and loading states included.
- Dates are consistent ISO local dates; observation dates are labeled "observed" and the
  prediction date "model as-of" — the two are never mixed.

## Data integrity

No hardcoded probabilities, historical values, thresholds, or intervals anywhere in the
components; all displayed numbers come from API responses (verified in tests via mocked
fetches with realistic payloads, and in the live smoke test against the real backend).

## Visual smoke test (real backend + frontend)

`docs/step17_dashboard_smoke.png` (headless Chrome, `?tab=dashboard&loc=2` → Nashik):
- dashboard summary rendered: **60.6%**, risk badge, evidence level
  `modest_positive_skill_vs_climatology_only`, calibration "over-predicts",
  individual-interval "Not available", source `stored_reanalysis_history`
- `history-panel` + `rainfall-chart` rendered (blue rain-bar pixels confirmed by sampling);
  DOM check confirmed dash-summary / dash-uncertainty / dash-data-quality / history-panel all
  present; all 5 districts present in the selector; no console-breaking errors observed.

## Tests

- `npx vitest run` → **12 passed** (8 Step 16 kept + 4 new: dashboard summary/evidence,
  stale+incomplete warnings, structured 422/503 error states, loading state; history bars +
  spell count, honest empty state, history error state)
- `npm run build` → tsc strict + production bundle OK
- Backend: unmodified; `python -m pytest -q` still **102 passed**

## Limitations

- No historical probability timeline exists (nothing stored to plot); if that becomes a
  requirement it needs a prediction-persistence subsystem (out of scope, correctly).
- Rainfall bars are reanalysis data — the provenance note is displayed.
- Season selector offers fixed offsets (latest/prev/5/10); a free year picker can come later.
- Full mobile optimization remains Step 22; layout stacks sensibly below 800 px.
- Charts are dependency-free (CSS bars) — deliberate for the demo; a charting library can be
  introduced later if richer interaction is needed.
