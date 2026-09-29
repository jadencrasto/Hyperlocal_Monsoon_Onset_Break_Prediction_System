# Step 9 — Analysis of the Pune Model Evaluation (SIH26086)

**Scope:** location 1 (Pune) only, explicit selection. Source artifact: `models/evaluation.json`
(created 2026-09-29T14:14:11+00:00 by the Step 10B controlled run; 2,626 rows, 26 years
2000–2025; train 2000–2012, validation 2013–2017, test 2018–2025; 808 test rows).
All rainfall is reanalysis-derived. This document analyzes; it proposes **no model change**.

---

## 1. What the results show

### Aggregate skill is real but modest
- Random Forest selected (validation Brier 0.1577 vs logistic 0.1620 — a near-tie; the
  selection margin is smaller than typical year-to-year noise).
- **Test BSS vs climatology = 0.103**, 95% year-block-bootstrap CI **[0.034, 0.151]**
  (500 resamples, seed 0). The CI excludes zero, so the model does beat its designated
  climatology baseline — but the lower bound is thin.
- **Critical baseline comparison:** the simple dry-run-conditioned baseline achieves test
  Brier **0.1358** vs the model's **0.1372** (log loss 0.4338 vs 0.4415). The trivial
  heuristic is marginally *ahead* of the trained model in absolute terms. The differences
  (~0.001–0.008) are within noise, so this is not proof the model is useless — but it is
  proof that **no added value over the dry-run heuristic has been demonstrated**.

### Per-year skill is unstable
| Year | Base rate | Model Brier | Per-year BSS | ROC-AUC |
|------|-----------|-------------|--------------|---------|
| 2018 | 0.267 | 0.152 | +0.233 | 0.812 |
| 2019 | 0.228 | 0.193 | +0.076 | 0.601 |
| 2020 | **0.040** | **0.056** | −0.029 | **0.402** |
| 2021 | 0.238 | 0.184 | +0.116 | 0.638 |
| 2022 | 0.089 | 0.071 | +0.080 | 0.832 |
| 2023 | 0.307 | 0.215 | +0.159 | 0.667 |
| 2024 | **0.109** | 0.097 | **−0.060** | 0.716 |
| 2025 | 0.158 | 0.131 | +0.002 | 0.591 |

- 5 of 8 test years show positive skill; 2020 and 2024 are negative; 2025 is a coin flip.
- Both negative years are the **two lowest-base-rate years** in the test set. In 2020 the
  model's absolute Brier (0.056) is the **best of all eight years** — it failed only
  *relative to climatology*, which had an exceptionally easy year. Negative per-year BSS
  in a rare-event year is a base-rate effect, not evidence of a broken model.

### Calibration is slightly biased toward under-forecasting
- `mean_diff = −0.028` (mean predicted 0.151 vs observed 0.179).
- The bias concentrates where the data is: bins [0.0,0.1) (n=372, diff −0.034) and
  [0.1,0.2) (n=171, diff −0.071) together hold 543 of 808 rows, all under-forecasting.
- Predicted probabilities never exceed 0.7 (only 3 rows in [0.6,0.7), none above). The RF
  (`min_samples_leaf=20`) outputs a compressed range; the model cannot express "high risk".

---

## 2. Genuine evidence-based issues

1. **No demonstrated advantage over the trivial baseline.** Dry-run heuristic ≥ model on
   test Brier and log loss. Whatever the RF has learned beyond recent dry-run length is
   not visible in aggregate test performance.
2. **Skill is not year-stable.** With per-year BSS spanning [−0.060, +0.233] and 3 of 8
   years ≤ +0.002, there is no evidence of reliable interannual skill; the honest claim is
   "modest average skill, inconsistent by year".
3. **Compressed probability range.** No predictions ≥ 0.7 limits operational usefulness
   for a risk-communication product, independent of skill.
4. **A consistent, data-dense under-forecast tendency.** −0.028 overall, concentrated in
   the two lowest bins that carry two-thirds of the rows. Small, but directionally
   consistent — worth tracking, not yet worth acting on.

## 3. Normal uncertainty — explicitly **not** issues

- **2020 ROC-AUC = 0.402.** Computed from 4 positives (388 positive–negative pairs); the
  estimate is dominated by sampling noise and is statistically indistinguishable from 0.5.
  It is not evidence of anti-skill, and no single-year AUC should drive changes.
- **2020/2024 negative BSS.** Both are low-base-rate years where climatology is naturally
  strong; per-year BSS-vs-climatology mechanically degrades there for *any* model
  calibrated to normal-season rates.
- **Only 8 test years / 808 autocorrelated rows.** The CI is itself coarse (a year-block
  bootstrap over 8 blocks resamples a small multiset); effective sample size is well below
  n due to within-year autocorrelation. Wide uncertainty here is a data limitation, not a
  modeling defect.
- **Reanalysis provenance.** Skill against reanalysis rainfall does not establish skill
  against gauge observations; this caps interpretation, it does not indicate a bug.

## 4. Recommendations (evidence-justified only)

1. **No model change now.** No retraining, no feature changes, no hyperparameter changes,
   no recalibration. Rationale: aggregate skill is positive (CI excludes 0); the negative
   years are explained by base-rate effects; the RF-vs-heuristic gap is within noise, so
   switching to the heuristic is equally unjustified; and with 26 years fully consumed by
   train+validation+test there is no honest data left to *fit* a recalibration on.
2. **Surface the dry-run baseline as a first-class comparison** in future evaluation
   reporting (a BSS-vs-dry-run alongside BSS-vs-climatology), so the "does the model beat
   the heuristic?" question is answered automatically each run. Reporting change only;
   batch with a later step, not now.
3. **Pre-register a recalibration trigger:** if the under-forecast tendency
   (|mean_diff| ≳ 0.03) or the model-vs-heuristic deficit persists on genuinely
   out-of-sample data — the 2026 season and/or Step 11 multi-location holdouts — then
   recalibrate (e.g., location-aware Platt scaling fit on held-out years). Until such data
   exists, act on neither.
4. **Resolve the open questions with more data, not more tuning:** Step 10 (history for
   Nashik, Kolhapur, Chhatrapati Sambhajinagar, Nagpur) and Step 11 (multi-location
   evaluation) directly target the small-sample limits identified above.

## 5. Current status of model changes

**No model change is currently justified by the evidence.** The Step 10B Pune artifact
stands as-is. Next roadmap action remains Step 10 (expand stored history to all five pilot
locations), which is also the cheapest way to strengthen every diagnostic flagged here.
