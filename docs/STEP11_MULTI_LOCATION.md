# Step 11 — Multi-Location Model Training + Evaluation (SIH26086)

**Date:** 2026-09-29 · **Scope:** pooled training across all 5 pilot districts on the common
**2000–2025** window — like-for-like with the Step 10B Pune-only run. Step 12 (independent
rainfall validation) was **not** started.

## 1. Pipeline changes (minimal, tested)

- `scripts/train_model.py`: added `--all-locations` (mutually exclusive with `--location-id`;
  the no-flag multi-location refusal guard remains), plus `--start-year` / `--end-year` window
  flags. Provenance `location_selection.mode` now distinguishes `explicit_location_id`,
  `all_locations`, `automatic_single_location`, and reports `selected_location_ids`.
- `backend/app/ml/train.py`: added an additive `by_location` test-report block
  (`by_location_metrics()`): per-location n, positives/negatives, Brier, log loss, ROC-AUC,
  BSS vs climatology, **and Brier difference vs the dry-run heuristic**. Same predictions as
  the aggregate; no refitting, no effect on training or model selection.
- `backend/app/ml/features.py` and `backend/app/ml/infer.py` unchanged: features are computed
  per location from trailing data only, and the artifact/inference contract is
  location-agnostic (verified below).

## 2. Leakage safety

Splits remain **year-based** (`split_years` on the pooled distinct years): train 2000–2012,
validation 2013–2017, test 2018–2025. Every location contributes exactly the same split
years, so no calendar year crosses a split boundary, and no location's test rows can
influence any training fit. Features use trailing windows only (covered by
`test_features_do_not_use_future_data`).

## 3. Experiment

```
python scripts/train_model.py --all-locations --start-year 2000 --end-year 2025
```
Exit 0. Dataset: **13,130 rows = 5 locations × 2,626**, 26 years (2000-06-15 → 2025-09-23),
kinds `['reanalysis']`, all from `open_meteo` (same source as Pune). Splits: train
6,565 rows / 13 y; validation 2,525 / 5 y; test **4,040 / 8 y** (2018–2025). All three
splits contain all 5 locations (verified in `splits.*.location_ids`).

**Model selection (validation Brier):** `logistic_regression` **0.1725** < `random_forest`
0.1760 → logistic selected (model_class `Pipeline` = StandardScaler+LogisticRegression).

## 4. Aggregate results (test 2018–2025, n=4,040, base rate 0.135)

| Model | Brier | Log loss | ROC-AUC |
|---|---|---|---|
| **Trained (logistic)** | 0.11838 | 0.3892 | 0.6787 |
| Dry-run heuristic baseline | **0.11445** | **0.3810** | 0.6749 |
| Climatology baseline | 0.12689 | 0.4211 | 0.5538 |

- **BSS vs climatology = 0.067**, 95% year-block-bootstrap CI **[0.041, 0.096]**
  (500 resamples, seed 0, n_years=8) — positive, CI excludes 0.
- **The dry-run heuristic again beats the trained model on every absolute metric**
  (Brier +0.0039, log loss +0.0083 in the model's disfavor; AUC near-identical). This
  replicates the Step 9 Pune finding at 5× the data and now at the aggregate level.

## 5. Per-location results (test years 2018–2025, n=808 each)

| id | Location | Pos. | ROC-AUC | BSS vs clim | Brier diff vs dry-run |
|----|----------|------|---------|-------------|------------------------|
| 1 | Pune | 145 | 0.689 | +0.082 | +0.0050 |
| 2 | Nashik | 88 | 0.631 | +0.038 | +0.0043 |
| 3 | Kolhapur | 87 | 0.712 | +0.054 | +0.0042 |
| 4 | Chh. Sambhajinagar | 144 | 0.665 | +0.053 | +0.0029 |
| 5 | Nagpur | 81 | 0.679 | +0.107 | +0.0032 |

- Positive BSS vs climatology at **all five locations** (range +0.038 to +0.107); the raw
  Brier difference vs climatology is correspondingly negative everywhere (lower is better).
- The heuristic wins at **every single location** too (model Brier − dry-run Brier is
  positive ≈ +0.003 to +0.005 everywhere).

## 6. Per-year (pooled) stability

BSS by test year: 2018 +0.063, 2019 +0.135, 2020 +0.086, 2021 **+0.013**, 2022 +0.066,
2023 +0.053, 2024 +0.038, 2025 +0.105 — **all 8 positive** (unlike the Pune-only run, where
2020 and 2024 were negative; pooling locations stabilized per-year estimates). Weakest year
2021 (+0.013) is still marginally positive.

## 7. Calibration

`mean_diff = +0.061` (mean predicted 0.196 vs observed 0.135) — the pooled model now
**over-predicts** dry-spell risk, the opposite direction of the Pune-only artifact
(−0.028). Under-prediction in the Pune-only model vs over-prediction here is consistent
with a pooled base rate (0.135) that mixes high-risk (Pune, Chh. Sambhajinagar ≈ 0.18) and
low-risk (Nagpur ≈ 0.10) districts. Over-prediction grows monotonically with predicted
probability (bin diffs +0.03 → +0.41 in the sparse upper bins).

## 8. Baselines, caveats, and honest scope

- Both reported baselines are fit on train+validation years only, then evaluated on the
  untouched test years; the dry-run heuristic is a legitimate, hard-to-beat predictor for
  persistence-driven dry-spell events at these horizons.
- Inference contract verified post-training: `load_artifact` + `predict_break_risk` on the
  new artifact via Pune's stored series (probability 0.287 for 2025-09-20, model
  `logistic_regression`) — the API path works unchanged.
- **Scope:** this experiment tests historical-pattern-based skill on reanalysis data with
  chronological year splits. It does **not** validate real-world 7-day-ahead forecasting,
  does not use weather-model forecasts, and does not establish skill against gauge
  observations (Step 12 territory).

## 9. Files changed / created

- `scripts/train_model.py`, `backend/app/ml/train.py` — multi-location + `by_location` (code)
- `backend/tests/test_ml.py` — new tests: `--all-locations` pooling, year-window restriction,
  mutual exclusion, `by_location_metrics` unit test, pooled-report integration test
- `models/break_risk.joblib`, `models/evaluation.json` — replaced by the pooled run
  (logistic; 12,559 B report). Pune-only artifacts backed up first:
  `models/backups/*.pune-step10b-20260929-201822` (+ earlier `*.pre-step10b-20260929-194339`)
- `docs/STEP11_MULTI_LOCATION.md` — this report

## 10. Tests

`cd backend && python -m pytest -q` → **80 passed** (was 75; +5 new Step 11 tests; the 8
failures seen mid-development were a bad `pd.Timestamp(...)` construction in the new test
helper, fixed before the training run).

## 11. Evidence-based issues

1. **The model still does not beat the trivial dry-run heuristic** — now demonstrated at
   aggregate level and at all 5 locations simultaneously. This is the single most important
   finding of Step 11 and mirrors Step 9.
2. **Calibration flipped sign after pooling** (−0.028 Pune-only → +0.061 pooled): the pooled
   model systematically over-predicts in low-base-rate districts. A single global model
   compresses location differences; per-location calibration (or a location feature) is the
   natural follow-up — but with all 26 years already consumed by train+val+test, there is no
   honest held-out data left to fit it on this window (same constraint as Step 9).
3. Logistic beating the RF here (and by a larger margin than in the Pune run) suggests the
   RF's validation edge in Step 10B was within noise — consistent with Step 9's caution.
4. All findings remain reanalysis-based and year-block-CI-coarse (8 test years).

## 12. Verdict

**Step 11: PASS** — pooled multi-location training/evaluation works safely (no leakage:
year-based splits shared by all locations), all requested metrics are reported, both
baselines are compared, artifacts replaced only after backup, and the full suite passes.
The honest summary: modest, location-uniform, positive skill over climatology, but **no
demonstrated added value over the persistence-style dry-run heuristic**, and pooled
calibration is biased (+0.061 over-prediction). Operational claims beyond this experiment
are not supported.
