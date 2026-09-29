# Step 14 — Prediction Response Schema & Confidence/Uncertainty Metadata (SIH26086)

**Date:** 2026-09-29 · **Scope:** formalize the Step 13 prediction response into a versioned,
frontend-ready schema with uncertainty metadata limited to what the evaluation legitimately
supports. **No model change; `probability` and inference behavior are byte-identical to
Step 13.** No claim of 7–30 day forecast skill.

## Endpoint (unchanged route, versioned response)

```
GET /api/locations/{location_id}/prediction/break-risk?as_of=YYYY-MM-DD
```

`schema_version: "1.0"` — Steps 16–18 should read this field and treat the top-level key set
below as stable. Error responses (404/422/503 with structured `detail.error`) are unchanged
from Step 13.

## Final response schema (v1.0)

```jsonc
{
  "type": "break_risk_prediction",
  "schema_version": "1.0",

  // --- prediction (unchanged meaning) ---
  "probability": 0.2869741411562451,          // point probability, 0..1
  "risk_category": "low" | "moderate" | "high",  // presentation bands ONLY
  "risk_bands": { "low": "< 0.2", "moderate": "0.2 to < 0.4", "high": ">= 0.4",
                  "note": "presentation bands ... NOT calibrated decision thresholds" },
  "prediction_date": "YYYY-MM-DD",
  "horizon_days": 7,
  "event": "human description of the predicted event",
  "basis": "historical-pattern-based estimate from local past rainfall only (no weather-model forecast)",

  // --- who/where ---
  "location": { "id", "name", "level", "state", "district", "latitude", "longitude", "coordinate_note" },

  // --- model provenance / evaluation evidence ---
  "model": {
    "name": "logistic_regression",
    "class": "Pipeline",
    "trained_on_locations": [1, 2, 3, 4, 5],
    "trained_period": { "first_date": "2000-06-15", "last_date": "2025-09-23", "n_years": 26 },
    "trained_through": "2025-09-23",            // convenience duplicate of trained_period.last_date
    "test_skill": { "brier_skill_vs_climatology", "brier_skill_ci": {...} },
    "baselines": { "model_brier", "climatology_brier", "dry_run_baseline_brier" },
    "intended_use": "...",
    "caveats": [ ... ]
  },

  // --- NEW in Step 14: uncertainty metadata ---
  "uncertainty": { ...see below... },

  // --- data freshness ---
  "data_status": { "source", "latest_rainfall_date", "data_age_days", "freshness",
                   "input_days_used", "input_completeness" },

  "limitations": [ ... ]   // always present
}
```

## `uncertainty` block — fields and their statistical basis

| Field | Value (example run) | Statistical basis |
|---|---|---|
| `individual_prediction_interval` | `{available: false, reason: "..."}` | **Deliberately null.** The pipeline fits one point-probability model; no quantile/ensemble/conformal method was trained, so no statistically justified per-prediction interval exists. `null` means *not provided*, not zero. **No interval is invented.** |
| `evaluation_skill.brier_skill_vs_climatology` | 0.067 | Aggregate test-set BSS vs climatology (Step 11 evaluation, untouched test years 2018–2025). |
| `evaluation_skill.brier_skill_ci` | [0.041, 0.096], 500 resamples, seed 0 | **95% year-block bootstrap CI — population-level uncertainty over test years, explicitly NOT an interval around this prediction** (stated in `ci_interpretation`). |
| `evaluation_skill.n_test_years` | 8 | Number of distinct test years behind the CI. |
| `calibration.mean_predicted / observed_rate / mean_diff` | 0.196 / 0.135 / +0.061 | Reliability diagnostic from the evaluation: the model **over-predicts** event probability on average on the pooled test set (sign-aware `interpretation` included). Justifies "don't treat probabilities as calibrated". |
| `per_year_stability.n_years / bss_min / bss_max / negative_years` | 8 / 0.013 / 0.135 / 0 | Spread of per-year test skill: shows whether skill was year-stable. Wide spread ⇒ skill is not year-stable. |
| `evidence_level` | `modest_positive_skill_vs_climatology_only` | Mechanical label from the evaluation numbers: `positive_skill_vs_climatology_and_heuristic` / `modest_positive_skill_vs_climatology_only` / `no_skill_demonstrated` / `no_evaluation_available`. No percentages invented. |
| `data_caveats.freshness / data_age_days / note` | stale / 374 | Staleness lowers trust in input features but is **not quantifiable as probability** without assumptions the pipeline does not make. |

**Explicitly NOT included:** any per-prediction confidence interval, any "confidence: 73%"
style number, any calibrated decision threshold, any weather-forecast information. The
0.2/0.4 risk bands are labeled as presentation-only in `risk_bands.note` and in
`limitations`.

## Distinguishing the four information layers

1. **Predicted probability** — `probability` (point estimate from the model, unchanged).
2. **Uncertainty/confidence** — `uncertainty.evaluation_skill` (population-level CI),
   `uncertainty.per_year_stability`, `uncertainty.data_caveats`; the absent
   individual interval is explicitly declared.
3. **Calibration limitations** — `uncertainty.calibration` + `risk_bands.note` +
   `limitations`.
4. **Historical/evaluation evidence** — `model.test_skill`, `model.baselines`,
   `model.trained_period`, `uncertainty.evidence_level`.

## Example response (real artifact, real DB)

```
GET /api/locations/1/prediction/break-risk?as_of=2025-09-20
```
→ 200, `schema_version: "1.0"`, probability **0.2869741411562451** (identical to Step 13),
`risk_category: "moderate"`, `evidence_level: "modest_positive_skill_vs_climatology_only"`,
CI [0.041, 0.096], calibration `mean_diff` +0.061 ("over-predicts"),
`per_year_stability` 0.013–0.135 across 8 years, `individual_prediction_interval.available:
false`, freshness "stale" (374 days).

## Files changed

- `backend/app/api/routes.py` — additive only: `SCHEMA_VERSION`, `_evidence_level()`,
  `_uncertainty_block()`, `schema_version`/`risk_bands`/`uncertainty`/`model.trained_period`/
  `model.class` response fields, one new `limitations` entry. Prediction logic untouched.
- `backend/tests/test_prediction_api.py` — +4 tests (schema stability/key set, uncertainty
  honesty incl. null interval, `_evidence_level` truth table, calibration sign logic).
- `docs/STEP14_RESPONSE_SCHEMA.md` — this document.

## Tests

`cd backend && python -m pytest -q` → **93 passed** (was 89; +4). Live smoke test on the real
artifact: probability byte-identical to Step 13; uncertainty block fully populated.

## Forward-compatibility notes for Steps 15–18

- Read `schema_version`; treat top-level keys as stable. Additive evolution bumps the minor
  version; any breaking change must bump major and be documented here first.
- `uncertainty.individual_prediction_interval.available` will flip to `true` with an actual
  interval payload only if a quantile/conformal/ensemble method is trained — that is a
  methodology change and must not be done by Steps 16–18 client-side.
- `risk_category`/`risk_bands` may be re-thresholded per-UI; do not persist them as
  decisions server-side.
- `input_completeness < 1.0` and `freshness != "current"` should surface as UI warnings
  (Nagpur/Chh. Sambhajinagar have known gauge/reanalysis gaps; Pune history currently ends
  2026-09-05).

## Limitations

- All uncertainty here is **evaluation-level** (how the model performed on held-out test
  years), not per-prediction uncertainty.
- The CI is computed from 8 test years — coarse by construction.
- Calibration is a pooled diagnostic; per-location calibration bias (+0.061 mean_diff) means
  individual districts may deviate more.
- No forecast-skill claim: this remains a historical-pattern-based estimate from past
  rainfall only.
