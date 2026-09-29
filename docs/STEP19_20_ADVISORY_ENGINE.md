# Steps 19–20 — Advisory / Rule Engine & Crop Templates (SIH26086)

**Date:** 2026-09-29 · **Scope:** informational agricultural advisories over the existing
Step 14 prediction data. **No backend changes, no ML changes, no second data path** — the
engine consumes the same `Prediction` object the dashboard already renders. Steps 21–23 not
started.

**Honest framing (applies to every advisory the system generates):** current model evidence
is modest (positive skill vs climatology only), the trained model does **not** beat the
simple dry-run heuristic on the documented aggregate test Brier score, pooled calibration
over-predicts (mean_diff ≈ +0.061), no individual prediction intervals exist, and **no 7–30
day forecast skill is established**. Advisories are informational; local agricultural
conditions and extension guidance remain necessary.

## Step 19 — Rule engine (`src/advisory/engine.ts`)

Pure, deterministic function: `generateAdvisoryCore(pred) -> AdvisoryCore`. No I/O, no
fetching, no randomness — identical input always yields identical output (tested).

**Inputs used (all from the existing Step 14 response):** `risk_category`, `probability`,
`horizon_days`, `location.name`, `uncertainty.evidence_level`, `uncertainty.calibration`,
`uncertainty.per_year_stability`, `data_status.freshness/data_age_days/input_completeness`,
`uncertainty.individual_prediction_interval`.

**Output:** `{ status, headline, message, cautions[], triggers[] }` where `status ∈
{informational, caution, limited_data}` is a *communication state* (escalation only, most
severe wins) — **not** a new scientific score. `triggers` is the ordered audit log.

### Rules (explicit, inspectable)

| Rule | Trigger | Effect |
|---|---|---|
| A `stale_data` | `freshness === "stale"` | status → `limited_data`; caution: indication may not reflect current field conditions; check updated local observations |
| B `incomplete_input` | `input_completeness < 1` | status → `caution`; caution about gaps lowering confidence |
| C `limited_evidence` | evidence ≠ `positive_skill_vs_climatology_and_heuristic` | status → `caution`; caution: "model-based indication, not a dependable forecast" |
| D `elevated_break_risk` | `risk_category !== "low"` | elevated dry-spell indication wording with explicit non-guarantee + "consider monitoring" |
| E `lower_break_risk` | `risk_category === "low"` | lower-risk indication; "local rainfall can still differ"; the word *safe* never appears |
| F `calibration_overprediction` | `calibration.mean_diff > 0.03` | caution: model historically predicts higher probabilities than observed; **probability is not adjusted** |
| G `no_individual_interval` | `ipi.available !== true` | logged for explainability; an interval is never implied |

Threshold note: 0.03 only decides whether the *calibration caution text* appears — it is not
a probability correction, not a recalibration, and no calibrated value is invented anywhere.

## Step 20 — Crop templates (`src/advisory/crops.ts`)

Structured data (no logic duplicated per crop): `Step 19 = what situation; Step 20 = how to
express it for the crop`. Composition: `composeAdvisory(core, crop)` = Step 19 situation +
crop situation body + crop monitoring + crop caveat.

**Supported crops (Maharashtra kharif starter set — not claimed exhaustive):** Soybean,
Cotton, Maize, Groundnut, Pigeon pea (Tur), plus a *General cropping* fallback.

**Agricultural safety:** templates contain only informational direction — monitor soil
moisture, review local rainfall observations, prepare contingency irrigation where
available, consider extension guidance, avoid high-cost decisions from this indication
alone. A test enforces that no doses (mm/kg/ha), sprays, pesticides, fertilizer doses, or
sowing dates appear in any template. Unknown crop IDs fall back to the generic template.

## UI integration

`src/AdvisoryPanel.tsx` *(new)* — placed between the dashboard panels and the history
charts in `App.tsx`. The app fetches the prediction **once** and passes the same object to
both `Dashboard` and `AdvisoryPanel` (no refetch, no second path). Features: crop selector
(5 crops + general), status badge, headline, message, monitoring list, cautions, the shared
disclaimer ("Informational advisory only. Confirm with local agricultural guidance before
making high-cost decisions…"), and a collapsible **"Why this advisory?"** panel listing the
actual triggers with real values (category, probability, freshness, completeness, evidence
level, calibration) plus model context.

**Error integrity:** the panel renders *only when a prediction exists* (`{pred && …}` in
`App.tsx`). If the prediction fails (e.g., Pune's current `insufficient_or_gappy_history`
422), the dashboard shows its structured error and **no advisory is generated** — a fake
advisory from missing data is impossible by construction (verified live).

## Wording philosophy

Allowed: "informational advisory", "model-based indication", "consider monitoring…",
"review local field conditions…", "this indication is not a guarantee…", "confirm with local
agricultural guidance before making high-cost decisions".
Forbidden (and asserted absent in tests): "you should definitely", "the crop will fail",
guaranteed rainfall, "do X because the model predicts", any "safe/unsafe" crop label.

## API changes

None. Rule engine is frontend application logic over the existing shared client (`src/api.ts`).

## Tests

- `src/advisory/engine.test.ts` (20): elevated/lower indication wording, stale →
  `limited_data`, incomplete → `caution`, limited-evidence conservatism (and its absence
  with strong evidence), calibration caution firing/not firing, no-interval guarantee,
  determinism (incl. `structuredClone`), monotone escalation, disclaimer wording, all 5 crop
  compositions + unknown-crop fallback, and a no-fabricated-agronomy scan.
- `src/AdvisoryPanel.test.tsx` (5): render for selected crop, crop change re-phrasing,
  why-panel with real fields, stale-data cautions, all crops render.
- Existing tests untouched and passing. **`npx vitest run` → 37 passed** ·
  `npm run build` (tsc strict + bundle) OK · backend untouched (**102 passed**).

## Visual smoke test

`docs/step19_advisory_smoke.png` (headless Chrome, real backend/frontend, Nashik):
advisory panel with "Caution" status, elevated dry-spell headline, Soybean template,
over-prediction caution, disclaimer; crop selector present. Pune (`loc=1`): **0 advisory
panels** — dashboard error (`insufficient_or_gappy_history`) shown instead. No
console-breaking errors.

## Known limitations

- Advisories are English-only (regional languages = Step 21); templates are structured to
  make text replacement straightforward.
- The 0.03 calibration-caution threshold is a communication heuristic, not a statistical
  correction.
- Crop set is small and kharif-focused; extending is additive data (id/name/bodies/
  monitoring/caveat) with no engine changes.
- Static crop text: the system cannot know actual crop stage per field; users must map the
  indication window to their own crop stage.
- No advisory persistence/log (each render recomputes deterministically).
