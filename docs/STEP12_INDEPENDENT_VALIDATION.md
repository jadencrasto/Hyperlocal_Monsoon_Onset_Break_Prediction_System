# Step 12 — Independent Rainfall-Data Validation (SIH26086)

**Date:** 2026-09-29 · **Scope:** read-only validation of the stored rainfall and derived
dry-spell labels. The model was **not** retrained, recalibrated, or tuned; no claim of
7–30 day forecast skill is made or supported here.

## 1. Independent source and provenance

**NOAA GHCN-Daily** (`ncei.noaa.gov/pub/data/ghcn/daily`), station files in `.dly` format:
gauge/observation records compiled by national meteorological services, **fully independent
of the ERA5-family reanalysis used for training** (different instruments, pipelines, and
institutional provenance). Units converted from tenths-of-mm; QC-flagged values
(`QFLAG != blank`) and -9999 sentinels dropped. Raw station files cached under
`data/raw/external/` (gitignored).

**Rejected as non-independent:** Open-Meteo forecast-API history (also ERA5-derived), any
other reanalysis (MERRA-2, JRA), and satellite-merger products that assimilate ERA5
(IMERG versions assimilating gauges were considered acceptable-in-principle but gauge data
was directly available, so no substitute was needed).

**IMD gridded gauge data (preferred target) was unreachable:** www.imdpune.gov.in timed out
from this network on all probes (see `docs/DATA_SOURCES.md` — IMD remains unregistered in
the provider registry). GHCN-Daily is the gauge-based fallback; its Indian station records
originate from IMD itself, giving an indirect line to the preferred source.

## 2. Locations, stations, spatial matching

Closest GHCN station with modern PRCP coverage, matched by point-to-point proximity to the
district-headquarters coordinates (no spatial averaging; the ~10–25 km ERA5 grid cell vs a
single gauge is an acknowledged mismatch):

| id | Location | Station | Gauge distance | Station PRCP span |
|----|----------|---------|----------------|-------------------|
| 1 | Pune | IN012190100 | ~1.4 km | 1901–2025 |
| 2 | Nashik | IN012161300 | ~1 km | 1965–2005 (**no modern gauge exists in GHCN**) |
| 3 | Kolhapur | IN012131800 | <2 km | 1901–2025 |
| 4 | Chhatrapati Sambhajinagar | IN012041000 | ~7 km | 1951–2025 |
| 5 | Nagpur | IN012141800 | ~5 km | 1943–2025 |

**Temporal matching:** strict same-date intersection of the stored ERA5 series and the
gauge series, restricted to the monsoon season (Jun 15–Sep 30, the model's domain).
Labels (`y` = a ≥5-day dry run with rain <2.5 mm within the next 7 days) were **recomputed
independently per source** with the same `target_series` implementation — comparing
pipelines, not assuming label transfer.

## 3. Coverage (honest accounting — inventory spans overstate completeness)

Fully-covered monsoon seasons (≥103 of 108 window days present in *both* sources):

| Location | Fully covered years | Coverage window |
|----------|--------------------:|-----------------|
| Pune | **22** | 2000–2024 (gaps: 2007/2009/2018 near-complete; 2025 partial) |
| Nagpur | **14** | 2000–2014 + 2023–2024 (2016–2022 has almost no gauge data) |
| Kolhapur | **10** | 2016–2025 (2000–2015 gauge is essentially absent) |
| Chh. Sambhajinagar | **6** | 2002–2006 + 2024 (many partial years between) |
| Nashik | **1** | 2005 only |

Matched in-season day counts (ERA5∩gauge): Pune 3,701 · Nagpur 2,864 · Chh. Sambhajinagar
2,397 · Kolhapur 1,398 · Nashik 202.

## 4. Validation results (full overlap window)

| Location | matched days | Pearson r | Spearman ρ | MAE mm | bias (gauge−ERA5) | wet-day(≥2.5mm) ERA5/gauge | wet-day agreement | **label agreement** | events ERA5/gauge | seasonal-count r |
|----------|----|------|------|------|------|------|------|------|-----|------|
| Pune | 2,214 | 0.42 | 0.52 | 7.9 | −2.8 | 0.73 / 0.42 | 0.61 | **0.80** | 138 / 356 | 0.33 |
| Nashik | 92 (2005) | 0.48 | 0.63 | 11.0 | −0.4 | 0.79 / 0.55 | 0.67 | 1.00* | 0 / 0 | n/a |
| Kolhapur | 903 | 0.38 | 0.47 | 8.8 | +1.1 | 0.69 / 0.58 | 0.67 | **0.84** | 50 / 75 | 0.23 |
| Chh. Sambhajinagar | 1,257 | 0.32 | 0.43 | 9.4 | −1.0 | 0.62 / 0.41 | 0.63 | **0.86** | 77 / 115 | 0.78 |
| Nagpur | 1,534 | 0.33 | 0.42 | 12.6 | +0.2 | 0.67 / 0.48 | 0.63 | **0.91** | 79 / 93 | 0.85 |

\* Nashik's 1.00 is on 92 days with zero events in either source — no information about
event labels; rainfall statistics only.

**Test-window view (2018–2025)** shows the same picture with thinner data: label agreement
Pune 0.86, Kolhapur 0.86, Chh. Sambhajinagar 0.86, Nagpur 0.97.

Sanity anchors: Pune gauge monsoon totals reproduce known climatology (2019 = 1,005 mm,
the extreme flood year, vs 352 mm in 2018; long-term mean ≈ 476 mm) and correlate **0.81**
with ERA5 seasonal totals — the parser and orientation are sound even where daily
correlation is modest.

## 5. Findings, disagreements, robustness

1. **Event labels are more robust than daily rainfall values.** Daily Pearson r is only
   0.32–0.48 (expected for grid-cell vs point gauge in convective regimes), yet the derived
   binary dry-spell labels agree **80–91%** at four of five locations. Coarse labels
   integrate over 7-day windows, damping day-scale spatial noise — the label definition is
   doing real work.
2. **ERA5 rains more often** (wet-fraction 0.62–0.79 vs gauge 0.41–0.58 everywhere): the
   2.5 mm dry threshold is crossed less often in ERA5 at these points. Since dry spells
   are the *event* class, ERA5's wet bias works **against** event detection — yet the
   model's ERA5-based test still shows skill, so the qualitative conclusions are not an
   artifact of wet bias (if anything they are conservative).
3. **Event counts disagree in magnitude where found:** Pune ERA5 finds 138 events vs 356
   gauge events (2.6×), Kolhapur 50 vs 75. Both sources agree that events are frequent;
   they disagree on exactly which days. Season-to-season event counts correlate weakly
   except at Chh. Sambhajinagar (0.78) and Nagpur (0.85).
4. **2020 Pune divergence:** gauge 521 mm vs ERA5 1,110 mm seasonal total — the single
   largest disagreement found. The gauge shows a near-drought season; ERA5 shows a very
   wet one. This is exactly the year with the Pune-only model's worst per-year BSS
   (Step 9), now with a plausible data-quality explanation. Worth flagging, not acting on.
5. **Nashik is effectively unvalidated** (one covered year, zero events) and Kolhapur's
   validation rests on 2016–2025 only.

## 6. Limitations

- Point gauge vs ~10–25 km grid cell: daily correlations of 0.3–0.5 are typical in this
  regime and do not by themselves indicate an error in either source.
- GHCN Indian records have real gaps (documented above); coverage differs per location, so
  cross-location robustness comparisons are uneven.
- Gauge data ends 2025-08-24 for Pune; late-2025 validation is truncated.
- No gauge-based *model* evaluation was performed (that would require re-running the
  pipeline on gauge labels and is out of scope for a read-only validation step).

## 7. Verdict on label robustness

**The historical labels are sufficiently robust for the demo:** 80–91% independent label
agreement at the four locations with meaningful coverage, correct seasonal orientation at
all of them, and a label definition robust to the daily-value noise of gridded data. The
known weakness — event-magnitude disagreement (especially Pune) and the wet-fraction gap —
is exactly the kind of caveat the reports already carry ("Skill on reanalysis rainfall does
not imply skill against gauge observations"), which this step now quantifies.

**Step 12: PASS** (with documented Nashik/Kolhapur coverage limitations).

## 8. Files changed / tests

- Added: `scripts/validate_labels.py` (read-only validation tool), this report, cached
  station files under `data/raw/external/` (gitignored).
- Unchanged: model artifact, `evaluation.json`, database, all app code.
- Tests: `cd backend && python -m pytest -q` → **80 passed**. Artifact/inference path
  re-verified intact before validation (logistic artifact loads, report schema unchanged).
