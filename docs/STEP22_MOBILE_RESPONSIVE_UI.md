# Step 22 — Mobile-Responsive UI (SIH26086)

**Date:** 2026-09-30 · **Scope:** CSS/layout + one small map-resize helper. **No backend, ML,
schema, advisory-logic, or localization changes.** Steps 7–21 functionality untouched.

## What changed

Two files carry the change; everything else is untouched:

1. **`frontend/src/styles.css`** — the responsive pass:
   - `overflow-wrap: break-word` on `.app` so long API tokens (e.g.
     `evidence_level` strings) wrap instead of forcing page-wide horizontal scroll.
   - `:focus-visible` outline (2px `#1976d2`) for keyboard/touch focus, plus a subtle
     `:active` brightness on buttons for tap feedback.
   - Map heights switched to `dvh` with a `vh` fallback (70/55 dvh) so mobile URL-bar
     show/hide doesn't clip the map bottom.
   - `.map-wrap { min-width: 0 }` — grid children default to `min-width:auto`, which can
     overflow the page from the inside.
   - `.loc-list button` switched from floated `%` to flexbox rows (name + % never wrap
     awkwardly on narrow screens).
   - Map-side detail-card `<dl>` gets a compact stacked layout instead of the browser's
     default `dd` indent.
   - Leaflet popups: larger close button (28×28 px target), more comfortable line-height.
   - Existing 800 px stack point kept; **new 600 px phone breakpoint**: all controls
     (location select, tabs, crop/language selects, season select, why-toggle) reach
     ≥44 px touch height, toolbar/tabs/advisory selectors go full-width single-column,
     fine print (`small`) bumped 0.8→0.85 rem for phone readability.
   - New 380 px tweak: `.big-prob` 2→1.8 rem so the probability + context stays on one
     line on the narrowest phones (still visually dominant).
2. **`frontend/src/RiskMap.tsx`** — new `AutoResize` component: a `ResizeObserver` on the
   map container calls `map.invalidateSize()` when the container changes size without a
   reload (mobile URL-bar collapse, rotation, window resize). Guarded for environments
   without `ResizeObserver`. Presentation-only; markers/popups/data flow unchanged.

Also added (test tooling, not app code): `frontend/public/step22-probe.html` (headless
probe harness) and `scripts/smoke_step22.sh` (reproducible smoke test).

## Audit → decision mapping

| Audit finding | Decision |
|---|---|
| Viewport meta, box-sizing, 800 px stacking already present | Kept; built on top rather than replaced |
| Selects/buttons 4–7 px padding (tiny targets) | ≥44 px height at ≤600 px; desktop sizes unchanged |
| No visible focus styles | `:focus-visible` outline only (no broad a11y rewrite) |
| Long enum strings could overflow | `overflow-wrap` on `.app` (measured: no overflow at 320–375 px) |
| `vh` map height vs mobile URL bars | `dvh` + `invalidateSize()` on resize |
| Desktop layout good | Desktop rules untouched; all new rules behind `max-width` queries |

## Responsive behavior

- **Desktop (>800 px):** unchanged — side panel + map grid, two-column summary grids.
- **Tablet (601–800 px):** map stacks above the side panel (55 dvh), summary grids become
  one-column term/definition stacks — the existing Step 17 stack point, verified live.
- **Phone (≤600 px):** single column; location selector and Map/Dashboard tabs become
  full-width 44 px controls; crop/language selectors stack full-width; fine print 0.85 rem.
  Nothing is hidden — every panel (summary, evidence/uncertainty, calibration, data
  quality, warnings, limitations, advisory, history) remains in the vertical flow, and the
  prediction summary (probability + risk badge) stays the first card on screen.

## Map behavior on mobile

- Map first (grid `order: -1`), 55 dvh / min 340 px tall — measured **336×447 px** at
  375×812 in the live probe. Tiles, fitBounds, circle markers, popups all verified working.
- `dvh` keeps the bottom attribution visible when the URL bar collapses;
  `AutoResize` re-measures the canvas on rotation/URL-bar changes so tiles don't smear.
- Popups have larger close targets and 1.45 line-height. No new boundaries, markers, or
  fabricated geography — the polygon-ready district-marker architecture is untouched.

## Dashboard / advisory / charts

- All dashboard cards stack vertically at ≤800 px with `dt`/`dd` stacked pairs; risk
  badge and big probability remain prominent (only shrunk below 380 px).
- Advisory panel: crop + language selectors become full-width stacked 44 px selects;
  Devanagari line-height 1.65 / 0.98 rem retained from Step 21; `overflow-wrap` protects
  long Marathi/Hindi words; disclaimer and monitoring/caution lists all wrap naturally.
- Rainfall strip: bars are flexed with a 3 px floor and the strip scrolls **internally**
  (`overflow-x: auto`), so 107-day seasons never overflow the page — per requirement,
  scrolling is constrained to the chart. Season selector is a 44 px control on phones.

## Accessibility / touch

44 px minimum control height at phone widths; visible `:focus-visible` rings; tap
feedback (`:active`); every control already had a real `<label>`/`aria-label`; all
interactions are buttons/selects (nothing hover-exclusive; bar tooltips are `title`, also
available via long-press). Deliberately *not* done: focus-trap/roving-tabindex work,
ARIA tree semantics for the location selector — that's a larger a11y pass, not this step.

## Smoke test (real backend + frontend)

`bash scripts/smoke_step22.sh` boots uvicorn + vite, then drives headless Chrome through
`step22-probe.html`, which loads the app in an iframe at the target width, waits for all
expected panels, and reports: page `scrollWidth` vs viewport (horizontal overflow),
per-panel internal overflow, required testids, runtime errors, vite error overlay,
advisory `lang`, probability text, map presence/size.

| Run | Viewport | Result |
|---|---|---|
| dashboard | 375×812 | PROBE_OK — no overflow, all panels, prob 60.6% |
| dashboard | 390×844 | PROBE_OK |
| dashboard | 768×1024 | PROBE_OK |
| dashboard | 1440×900 | PROBE_OK |
| map | 375×812 | PROBE_OK — leaflet 336×447, no overflow, no map error |
| dashboard `lang=mr` | 375×812 | PROBE_OK — `advisory_lang: "mr"`, prob identical |

Screenshots: `docs/step22_*.png` (mobile dash/map/mr, 390, tablet, desktop). No console
errors or vite overlays in any run; backend reported 200 and the live Nashik prediction
(60.6%) matches earlier steps — proving no API/data semantics changed.

## Tests

- `npx vitest run` → **54 passed** (unchanged suite: engine 20, locales 17, Dashboard 8,
  AdvisoryPanel 5, RiskMap 4)
- `npm run build` → tsc strict + vite production bundle OK
- `pytest -q` (root) → **102 passed** (backend untouched)
- Smoke: `SMOKE_FAIL=0`, all six runs PROBE_OK (table above)

## Known limitations

- Verified on headless Chrome (Windows) at 375/390/768/1440 px only — real iOS/Android
  browsers, Safari, and Firefox mobile are **not** verified; `dvh` and `:focus-visible`
  fall back gracefully on older engines, but no claim of universal support is made.
- The 44 px touch-target rule applies at ≤600 px; between 601–800 px some selects remain
  at desktop sizing (still usable, larger than before via `line-height`).
- `data-testid="leaflet-map"` (Step 16) has never actually reached the DOM — react-leaflet
  v4 drops `data-*` props. Left as-is (cosmetic; tests never relied on it); the probe
  verifies the map via `.leaflet-container` instead. Noting it for a future cleanup.
- `orientationchange` handling is best-effort (single re-measure); ResizeObserver covers
  the common cases.
- History season picker remains fixed offsets (latest/prev/5/10) — unchanged from Step 18.
