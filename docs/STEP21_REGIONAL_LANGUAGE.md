# Step 21 — Regional-Language Advisory Layer (SIH26086)

**Date:** 2026-09-29 · **Scope:** localization of the advisory system only. **No ML changes,
no rule changes, no crop-logic changes, no backend changes.** Predictions, risk categories,
rule conditions, and probabilities are byte-identical across languages (verified by tests).
Steps 22–23 not started.

## 1. Supported languages

| Code | Language | Native label |
|---|---|---|
| `en` | English | English (default + universal fallback) |
| `mr` | Marathi | मराठी |
| `hi` | Hindi | हिन्दी |

Architecture is additive: a new language = one new `LocalePack` file + one registry entry.
The advisory engine, rules, and crop IDs never change.

## 2. Localization architecture

```
src/advisory/locales/
  types.ts    LocaleCode, AdvisoryValues (raw numbers only), LocalePack, LocalizedCropTemplate
  en.ts       English reference pack (mirror of Step 19/20 texts)
  mr.ts       Marathi pack
  hi.ts       Hindi pack
  crops.ts    LOCALIZED_CROPS: locale × crop-ID → localized template
  index.ts    registry, per-key English fallback, values extraction, Intl formatters
```

**Rule-ID based lookup, exactly as required:** locale packs expose
`rules[ruleID].label/.detail(values)`. Selection is by the stable Step 19 rule IDs
(`stale_data`, `incomplete_input`, `limited_evidence`, `elevated_break_risk`,
`lower_break_risk`, `calibration_overprediction`, `no_individual_interval`, plus the data-age
variants `recent_data`/`current_data`). **No English string is ever parsed** to pick a
translation.

## 3. Structured triggers preserved (no preformatted strings as source)

`generateAdvisoryCore` gained an **additive** block (English output unchanged): `situation`
(`elevated`/`lower`), `fired_rules` (IDs), and `values` — a raw-number snapshot (probability,
risk category, horizon, location name, data age, completeness, freshness, calibration values,
evidence level). Percentages, dates, and ages are formatted **only at render time** via
`Intl.NumberFormat`/`Intl.DateTimeFormat` (`mr-IN`/`hi-IN`/`en-IN`); `0.6055` never becomes
`"60.6%"` inside the engine. A test proves the same pack formats `0.4 → "40.0%"` and
`0.6 → "60.0%"` from raw values.

## 4. Crop-template localization

`LOCALIZED_CROPS[locale][cropID]` — IDs unchanged across locales. Each locale provides
localized name/context/elevated body/lower body/monitoring/caveat. `localizedCrop(locale,
id)` falls back per-key: selected locale → English → generic. The `en` pack is asserted
identical to the Step 20 registry (no accidental rewording).

## 5. Fallback behavior (fail-safe)

1. Selected locale for that exact key → 2. **English for that key** → 3. safe generic line.
Never `undefined`, never blank, never a bare internal rule ID shown to users (tested,
including a simulated hole in the Marathi pack and a simulated missing locale).

## 6. Agricultural terminology decisions

Farmer-usable phrasing over literal translation; uncertainty preserved in every locale:

| Concept | Marathi | Hindi | Note |
|---|---|---|---|
| dry spell / break phase | कोरडा काळ / पाऊस थांबणे (मान्सून स्थगित) | शुष्क दौर / बारिश रुकना (मानसून विराम) | everyday phrasing preferred |
| soil moisture | मातीतील ओलावा | मिट्टी की नमी | |
| rainfall gap | पावसाच्या नोंदींमधील तूट | वर्षा रिकॉर्ड में कमी | phrase, not forced literal |
| contingency irrigation | जिथे शक्य असेल तेथे पाणी पुरवठ्याची/सिंचनाची तयारी | जहाँ संभव हो सिंचाई की तैयारी | deliberate non-specificity |
| extension guidance | कृषी विभागाचे मार्गदर्शन | कृषि विभाग / कृषि सलाहकार की सलाह | |
| pod filling | शेंगा भरणे | फली भरने | |
| pegging (groundnut) | बिड़वणी | गांठ जकड़न | regional term documented |
| flowering | फुल येणे | फूल आना | |
| evidence level | पुराव्याची पातळी | प्रमाण का स्तर | values translated descriptively, metrics unchanged |
| historical over-prediction | ऐतिहासिक जास्त अंदाज | ऐतिहासिक अधिक अनुमान | "over-prediction" as concept, not math jargon |
| possibility (not guarantee) | शक्यता … हमी नाही | संभावना … गारंटी नहीं | core uncertainty pair |

**Terms needing future agricultural review:** बिड़वणी (pegging; some regions say गांठ
पकडणे), कोरडा काळ vs थांबा-हव्वा for dry spell, and the calibrated-skill phrases — a
district-extension officer should validate before field use.

## 7. Scientific meaning preservation (tested)

- probability identical across locales (0.6055 → `60.6%` in en/mr/hi — live-verified);
- risk categories map 1:1 (`low/moderate/high` ↔ कमी/मध्यम/जास्त ↔ कम/मध्यम/अधिक);
- rule triggers/fired_rules identical across locales;
- elevated text must contain a *possibility* word AND a non-guarantee statement in every
  locale; lower-risk text must never contain "safe" (सुरक्षित), "अवश्य", "गारंटी है कि",
  "नक्की पाऊस", or similar stronger-certainty phrasing (regex-enforced);
- localized crop text passes the same no-fabricated-agronomy scan as Step 20.

## 8. Language selector & accessibility

`AdvisoryPanel` header now hosts **Language** (`English/मराठी/हिन्दी`) beside **Crop**,
each with a proper `<label>`, native select (keyboard accessible). Language switch is
instant — same prediction object, same crop ID, **no refetch**. Persistence: `?lang=` URL
param (deep-linkable demos) → `localStorage` → English. Panel sets `lang` attribute
(`mr`/`hi`) with raised line-height/font-size for Devanagari readability; the responsive
layout (flex-wrap) prevents card overflow.

## 9. Tests

`src/advisory/locales/locales.test.ts` (13): rule-ID completeness ×3 locales, crop-template
completeness, status/category/freshness localization, per-key English fallback (with pack
mutation + restore), missing-locale fallback, cross-locale identical values/triggers,
no-stronger-certainty regexes, no-new-agronomy scan, raw-value formatting, registry-vs-Step-20
identity, generic-crop localization. AdvisoryPanel test updated to the localized why-panel
(labels not bare rule IDs). **`npx vitest run` → 54 passed** (37 + 17). `npm run build` OK.
Backend untouched.

## 10. Visual smoke test

Real backend + frontend, headless Chrome:
- EN/MR/HI dashboards (`?tab=dashboard&loc=2&lang=…`): localized titles (Agricultural
  advisory / कृषी सल्ला / कृषि सलाह), statuses (Caution / सावधानता / सावधानी), why-toggles,
  crop names (सोयाबीन in both), monitoring terms (मातीतील ओलावा / मिट्टी की नमी);
- probability `60.6%` identical across all three dumps;
- Pune (`loc=1`): **0 advisory panels** — error state only, in every language;
- screenshots: `docs/step21_marathi_smoke.png`, `docs/step21_hindi_smoke.png` (content-pixel
  sampling confirms rendered Devanagari; layout intact, no card overflow).

## 11. Known limitations

- Three languages; more are additive (no engine change).
- No font subsetting/embedding — system Devanagari fonts assumed (Step 23 territory).
-mr/hi packs are engineering-authored; **agricultural-review sign-off is recommended before
  farmer-facing deployment**.
- The dashboard's non-advisory panels (summary/evidence/history) remain English; their
  localization would follow the same registry pattern if wanted.
- Language persistence is per-browser (`localStorage`) + URL param; no server-side profile.
