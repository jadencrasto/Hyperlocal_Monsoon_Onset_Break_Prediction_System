# Step 10 — Historical Data Expansion to All 5 Pilot Locations (SIH26086)

**Date:** 2026-09-29 · **Scope:** data ingestion and verification only.
No model was trained; `models/break_risk.joblib` and `models/evaluation.json` are untouched.

## What was run

Using the existing pipeline (no code or configuration changes):

```
python scripts/download_history.py --start-year 2000 --end-year 2026 --location-id {2|3|4|5} --pause 1.0
```

One run per missing location (Nashik, Kolhapur, Chhatrapati Sambhajinagar, Nagpur), each
returning exit code 0 with **0 failed requests** — 108/108 year-fetches ok (27 years × 4
locations). Pune (`--location-id 1`) was never targeted, and the upsert key
`(location_id, date, kind, provider)` makes re-ingestion idempotent.

## Resulting database state (`data/app/monsoon.db`)

| id | Location | Rows | First date | Last date | Distinct years |
|----|----------|------|-----------|-----------|----------------|
| 1 | Pune *(preserved)* | 9,502 | 2000-01-01 | 2026-09-05 | 27 |
| 2 | Nashik *(new)* | 9,769 | 2000-01-01 | 2026-09-29 | 27 |
| 3 | Kolhapur *(new)* | 9,769 | 2000-01-01 | 2026-09-29 | 27 |
| 4 | Chhatrapati Sambhajinagar *(new)* | 9,769 | 2000-01-01 | 2026-09-29 | 27 |
| 5 | Nagpur *(new)* | 9,769 | 2000-01-01 | 2026-09-29 | 27 |

**Monsoon-window usability** (Jun 15–Sep 30 target window, ≥103 of 108 days present):
- Loc 1: 26 fully usable years 2000–2025 (2026 has 5 window days — season incomplete).
- Locs 2–5: 27 fully usable years 2000–2026 inclusive (ingested through 2026-09-29).

## Quality & provenance verification (read-only queries)

- **Missing/invalid data:** `precip_mm IS NULL` = 0 and `precip_mm < 0` = 0 for all 5 locations.
- **Duplicates:** 0 rows violate the `(location_id, date, kind, provider)` unique key.
- **Provenance:** uniform — `kind='reanalysis'`, `provider='open_meteo'` for every row at
  every location (Open-Meteo archive API, ERA5-family reanalysis; model grid-cell values,
  not gauge observations; CC BY 4.0 attribution applies). Same source as Pune's existing data.
- **Pune preservation:** 9,502 rows / 2000-01-01→2026-09-05 before **and** after ingestion.
- **Sync log:** 30 → 138 rows (+108, one per request). Post-run `kind='history'` statuses:
  135 ok / 0 error / 0 skipped_offline — i.e. 27 pre-existing history entries (all ok) + the
  108 new entries (all ok); the 3 remaining pre-existing rows are other kinds.

## Tests

`cd backend && python -m pytest tests/test_open_meteo.py tests/test_service.py -q`
→ **25 passed** (provider parsing + ingestion/upsert/read paths; all offline-safe, tmp_path
fixtures). The full suite (75 tests) also passed earlier on this working tree (Step 10A).

## Notes & known gaps

- The four new locations extend through the current 2026 season; Pune's stored history ends
  2026-09-05 (previous download). For like-for-like **Step 11 training (2000–2025 seasons)**,
  all five locations have 26 identical monsoon seasons available.
- Coverage numbers include Jan 1–Jun 14 / Oct 1–Dec 31 shoulder days; the training pipeline
  (`build_dataset`) selects the monsoon window itself.
- All data is reanalysis; gauge observations would override reanalysis per-day if ever added
  (`history_series` prefers `kind='observation'`).

## Verdict

**Step 10: PASS** — all 5 pilot locations hold usable, quality-checked, provenance-recorded
historical data; no model artifacts were modified; no failures or coverage gaps found.
