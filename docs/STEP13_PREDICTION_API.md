# Step 13 — Backend Prediction API (SIH26086)

**Date:** 2026-09-29 · **Scope:** a demo-ready, frontend-facing prediction endpoint around the
existing Step 11 multi-location model. **No retraining, recalibration, or methodology change.**
No claim of validated 7–30 day forecast skill is made; see Limitations.

## Endpoint

```
GET /api/locations/{location_id}/prediction/break-risk?as_of=YYYY-MM-DD
```

- `location_id` (path): a pilot location id (`/api/locations` lists them).
- `as_of` (query, optional, ISO date): the prediction/reference date. Defaults to the latest
  stored rainfall date for the location. **Future dates are rejected (422)** — the model has
  no rainfall beyond today, so a future date would be fabricated. **Dates outside the monsoon
  season (Jun 15–Sep 30) are rejected (422)** — the model is trained only on in-season days,
  so off-season output would be extrapolation.

### Errors (structured `detail`)

| Status | `detail.error` | Cause |
|--------|----------------|-------|
| 404 | (plain string) | unknown location |
| 404 | `no_stored_history` | location has no rainfall rows |
| 422 | `future_date` | `as_of` after today |
| 422 | `out_of_season` | `as_of` outside Jun 15–Sep 30 |
| 422 | `insufficient_or_gappy_history` | <30 days of history, or gaps in the trailing feature window (the inference contract refuses to extrapolate across missing days) |
| 503 | `model_unavailable` | no trained artifact on disk |

## Response schema

```jsonc
{
  "type": "break_risk_prediction",
  "location": { "id", "name", "level", "state", "district", "latitude", "longitude", "coordinate_note" },
  "prediction_date": "YYYY-MM-DD",
  "probability": 0.0 - 1.0,
  "risk_category": "low" | "moderate" | "high",   // <0.2 / <0.4 / >=0.4 (demo bands)
  "horizon_days": 7,
  "event": "human description of the predicted event",
  "basis": "historical-pattern-based estimate from local past rainfall only (no weather-model forecast)",
  "model": {
    "name": "logistic_regression",
    "trained_on_locations": [1, 2, 3, 4, 5],
    "trained_through": "2025-09-23",
    "test_skill": { "brier_skill_vs_climatology", "brier_skill_ci": { "low", "high", ... } },
    "baselines": { "model_brier", "climatology_brier", "dry_run_baseline_brier" },
    "intended_use": "...",
    "caveats": [ ... ]
  },
  "data_status": {
    "source": "stored_reanalysis_history",
    "latest_rainfall_date": "YYYY-MM-DD",
    "data_age_days": 0,
    "freshness": "current" | "recent" | "stale",   // <=2 / <=7 / >7 days
    "input_days_used": 9395,
    "input_completeness": 1.0
  },
  "limitations": [ ... ]   // always present; plain-language uncertainty statements
}
```

## Example (real artifact + real database)

```
GET /api/locations/1/prediction/break-risk?as_of=2025-09-20
```
→ **200** with probability **0.287**, `risk_category: "moderate"`, `trained_on_locations:
[1,2,3,4,5]`, `test_skill.brier_skill_vs_climatology: 0.067` (CI [0.041, 0.096]),
`baselines: {model_brier: 0.118, climatology_brier: 0.127, dry_run_baseline_brier: 0.114}`,
`data_status.freshness: "stale"` (prediction date 374 days before today), and the four
standard `limitations` entries.

A second live check behaved correctly by *refusing*: the default `as_of` (Pune's latest
stored day, 2026-09-05) is out of season, and requesting it as an explicit date returns
422 `insufficient_or_gappy_history` because the stored series has gaps near that date —
the endpoint does not guess across missing data.

## Design notes

- Loads the artifact via the existing `load_artifact` and predicts via the unchanged
  `predict_break_risk` contract (StandardScaler+LogisticRegression pipeline inside).
- Legacy `/api/locations/{id}/monsoon/break-risk` remains for compatibility; the new
  endpoint adds risk categories, provenance, data-freshness, and structured errors.
- Provenance is read from `models/evaluation.json` (the artifact it describes), so the
  response can never quietly claim single-location training for a pooled model.
- Demo risk bands (0.2/0.4) are presentation thresholds, not calibrated decision
  thresholds — the evaluation explicitly found the model is not calibrated
  (Step 11 `mean_diff` = +0.061).

## Tests

`backend/tests/test_prediction_api.py` — 9 focused tests using a tiny real sklearn artifact
dumped into the tmp models dir (exercises the true inference path): success schema +
provenance, future-date 422, out-of-season 422, no-model 503, no-history 404, gappy-history
422, unknown-location 404, stale-data transparency, and `_risk_category` boundaries.

**Full suite: `python -m pytest -q` → 89 passed** (was 80; +9).

## Limitations

- This API exposes a historical-pattern-based estimate; it is **not** a weather forecast and
  holds no validated 7–30 day predictive skill.
- Inputs are ERA5-family reanalysis stored locally; Step 12 found event labels agree ~80–91%
  with independent gauges, but daily values disagree materially and the model has never been
  evaluated on gauge data.
- Pooled-model probabilities are over-predicted on average (calibration `mean_diff` +0.061)
  and no added value over the dry-run heuristic has been demonstrated (Step 11).
- One rainy-season year has elapsed since the last stored rainfall day; `data_status` reports
  staleness rather than hiding it. Refresh history before live demos.
- Nashik/Kolhapur gauge validation coverage was partial (Step 12); Nagpur/Chh. Sambhajinagar
  data gaps are visible via `input_completeness` when present.
