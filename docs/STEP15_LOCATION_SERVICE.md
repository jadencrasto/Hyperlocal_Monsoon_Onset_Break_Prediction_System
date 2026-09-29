# Step 15 — Location Service: District/Block/Panchayat Hierarchy (SIH26086)

**Date:** 2026-09-29 · **Scope:** a reusable hierarchy service and API over the existing
location table. **No ML changes**; existing location and prediction endpoints remain
backward compatible (verified). No map/UI work (Step 16).

## 1. Data model

`locations` table extended (additively) with `parent_id` (self-reference, `ON DELETE SET NULL`);
`latitude/longitude` are now nullable to support coordinate-less grouping nodes:

```
state (grouping node, no coordinates)
  └── district (analysis point: coordinates, rainfall data)
        └── block (schema ready - NO real data yet)
              └── panchayat / village cluster (schema ready - NO real data yet)
```

Rules enforced in code (`validate_parent_child`):
- a child's level must be **exactly one step below** its parent's (no skipping, no upward links);
- a state node only adopts districts whose `state` equals the state node's `name`;
- deeper nodes must share their parent's `state`;
- uniqueness: `(name, level, state, district)` preserved, plus `(parent_id, name, level)`.

**No block or panchayat rows exist** — the schema, validation, and endpoints are ready for
authoritative data (target: LGDirectory 2021 / IMD-linked sources; see `docs/DATA_SOURCES.md`),
but none were fabricated: no invented boundaries, coordinates, or parentage.

## 2. API (all under `/api`)

| Endpoint | Purpose |
|---|---|
| `GET /locations` *(existing)* | flat list, now including `parent_id`; `?level=` validated (422 `invalid_level` on unknown), `?state=` unchanged |
| `GET /locations/{id}` *(existing)* | detail, now including `parent_id` |
| `GET /locations/tree` *(new)* | full hierarchy for navigation: `{levels, levels_present, levels_with_data, roots:[{..., n_children, has_data, children:[...]}]}` — `levels_present` exposes which levels have real rows; `has_data` marks nodes with stored rainfall |
| `GET /locations/{id}/children` *(new)* | direct children (`404 location_not_found` on bad id) |
| `GET /locations/{id}/coverage` *(new)* | rainfall availability for a district, aggregated over descendant districts for grouping nodes |

Error handling: unknown location → 404 `location_not_found`; unknown `level` filter → 422
`invalid_level`; invalid parent/child relations raise `HierarchyError` (validated in the
service, reused by any future admin/import path).

## 3. Representation of the 5 pilot locations

Pilot district IDs **1–5 and their coordinates are unchanged** (`Pune 18.5204,73.8567`,
`Nashik 19.9975,73.7898`, `Kolhapur 16.7050,74.2433`, `Chhatrapati Sambhajinagar
19.8762,75.3433`, `Nagpur 21.1458,79.0882`). One grouping node was derived from data already
present (`Maharashtra`, id **6**, level `state`, `parent_id=null`, no coordinates) and the five
districts were linked to it via the validated `link_child` path. Live state aggregation:
`coverage` for id 6 = 48,578 rows across 5 districts, 2000-01-01 → 2026-09-29.

Applied to the real database:
- backup: `data/app/backups/monsoon.db.pre-step15-20260929-212950`
- `ensure_schema` added `parent_id` and relaxed `latitude/longitude` NOT NULL
  (add-temp-column → copy → drop → rename; SQLite-safe, idempotent, data verified intact)
- `scripts/seed_hierarchy.py --commit` created the state node; `link_child` attached districts

## 4. Real data vs unavailable levels

| Level | Status |
|---|---|
| state | **Real** (1 node, derived from existing district state values) |
| district | **Real** (5 pilot districts, coordinates + rainfall) |
| block | **Schema ready, no data** — never fabricated; `levels_present` / `n_children: 0` make the gap visible to the frontend |
| panchayat | **Schema ready, no data** — same |

## 5. Reuse (Steps 16–18)

`backend/app/services/location_service.py` is framework-free (takes a `Session`, returns
dicts): `list_locations`, `get_location`, `children_of`, `tree`, `link_child`,
`validate_parent_child`, `ensure_state_nodes`, `count_descendants`, `rainfall_coverage`,
plus `LEVELS`/`HierarchyError`. The map (Step 16) can drive from `GET /locations/tree`
(`has_data`, coordinates on districts only) without duplicating hierarchy logic; dashboard
selectors (Steps 17–18) can reuse `tree`/`children_of` for cascading dropdowns.

## 6. Tests

`backend/tests/test_location_hierarchy.py` (9 tests): level-adjacency and state-match
validation (including cross-state adoption rejection), link idempotency + not-found errors,
children/tree shape (levels_present, has_data, coordinate policy), list filters + unknown
level, coverage empty/populated, `ensure_state_nodes` idempotency + dry-run, endpoint
behaviors (tree/children/detail `parent_id`/flat list compat/422+404 errors), prediction
endpoint compatibility, and a migration test simulating a pre-Step-15 database (parent_id
added, NOT NULL relaxed, data intact, second run a no-op).

**Full suite: `python -m pytest -q` → 102 passed** (was 93; +9).

## 7. Backward compatibility

- `/api/locations` and `/api/locations/{id}` unchanged except the **additive** `parent_id`
  field; filters behave identically for valid inputs.
- Prediction path verified on the real DB: `GET /api/locations/1/prediction/break-risk?as_of=2025-09-20`
  → 200 with the same probability as Step 14 (0.2869741411562451), and the response's
  `location` block now carries `parent_id: 6`.
- Model, evaluation artifacts, and rainfall data untouched (48,578 rows unchanged).

## 8. Limitations / notes for Step 16

- Block/panchayat levels are structurally present but **empty**; the map must render them
  from `levels_present` rather than assuming all four levels have content.
- Only Maharashtra has a state node; adding other states later is `ensure_state_nodes` +
  `link_child` (or an import script) — no schema change needed.
- Coordinates exist for district HQ points only; block/panchayat geometry will need
  authoritative boundary data before any polygon mapping.
- `count_descendants`/`rainfall_coverage` walk the tree recursively; fine at demo scale.
