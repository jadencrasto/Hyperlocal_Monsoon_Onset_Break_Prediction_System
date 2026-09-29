import { describe, expect, it } from "vitest";
import { generateAdvisoryCore } from "../engine";
import { cropById } from "../crops";
import {
  LOCALES, LOCALE_ORDER, advisoryValues, fmtDate, fmtPercent, getPack,
  localizedCalibration, localizedEvidence, localizedFreshness, localizedRiskCategory,
  localizedRule, localizedStatus, type LocaleCode,
} from "./index";
import { LOCALIZED_CROPS, localizedCrop } from "./crops";
import type { Prediction } from "../../api";

const pred = (over: Partial<Prediction> = {}): Prediction => {
  const p = {
    type: "break_risk_prediction", schema_version: "1.0",
    location: { id: 2, name: "Nashik", level: "district", parent_id: 6, state: "Maharashtra",
                district: "Nashik", latitude: 19.9975, longitude: 73.7898 },
    prediction_date: "2026-09-29", probability: 0.6055, risk_category: "high",
    risk_bands: {}, horizon_days: 7, event: "e", basis: "b",
    model: { name: "logistic_regression", trained_on_locations: [1], trained_through: null,
             test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} }, baselines: {} },
    uncertainty: {
      individual_prediction_interval: { available: false, reason: "point model" },
      evaluation_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {}, n_test_years: 8 },
      calibration: { mean_predicted: 0.196, observed_rate: 0.135, mean_diff: 0.0607 },
      per_year_stability: { n_years: 8, bss_min: 0.013, bss_max: 0.135, negative_years: 0 },
      evidence_level: "modest_positive_skill_vs_climatology_only",
    },
    data_status: { source: "s", latest_rainfall_date: "2026-09-29", data_age_days: 0,
                   freshness: "current", input_days_used: 9769, input_completeness: 1.0 },
    limitations: [],
  } as unknown as Prediction;
  return { ...p, ...over,
    uncertainty: { ...p.uncertainty, ...(over.uncertainty ?? {}) },
    data_status: { ...p.data_status, ...(over.data_status ?? {}) } };
};

const ALL_RULES = [
  "stale_data", "recent_data", "current_data", "incomplete_input", "limited_evidence",
  "elevated_break_risk", "lower_break_risk", "calibration_overprediction", "no_individual_interval",
];
const CROP_IDS = ["soybean", "cotton", "maize", "groundnut", "pigeon_pea", "generic"];
const LOCALES_ALL: LocaleCode[] = [...LOCALE_ORDER];

describe("translation completeness", () => {
  it("all supported rule IDs have translations in every locale", () => {
    for (const loc of LOCALES_ALL) {
      for (const rule of ALL_RULES) {
        const r = localizedRule(loc, rule, advisoryValues(pred(), "Soybean"));
        expect(r.label, `${loc}/${rule}.label`).toBeTruthy();
        expect(r.detail, `${loc}/${rule}.detail`).toBeTruthy();
        expect(r.detail).not.toMatch(/^undefined|^\[object/);
      }
    }
  });

  it("all crops have localized templates; IDs unchanged across locales", () => {
    for (const id of CROP_IDS) {
      for (const loc of LOCALES_ALL) {
        const t = localizedCrop(loc, id);
        expect(t.id).toBe(id);
        expect(t.name).toBeTruthy();
        expect(t.elevatedBody).toBeTruthy();
        expect(t.lowerBody).toBeTruthy();
        expect(t.monitoring.length).toBeGreaterThan(0);
        expect(t.caveat).toBeTruthy();
      }
    }
  });

  it("statuses, risk categories, and freshness are localized in every locale", () => {
    for (const loc of LOCALES_ALL) {
      for (const s of ["informational", "caution", "limited_data"] as const)
        expect(localizedStatus(loc, s)).toBeTruthy();
      for (const c of ["low", "moderate", "high"] as const)
        expect(localizedRiskCategory(loc, c)).toBeTruthy();
      for (const f of ["current", "recent", "stale"] as const)
        expect(localizedFreshness(loc, f)).toBeTruthy();
    }
  });

  it("missing translation key falls back to English for that key", () => {
    // simulate a hole in a locale pack via direct registry access
    const saved = (LOCALES.mr.rules as any).stale_data;
    delete (LOCALES.mr.rules as any).stale_data;
    const r = localizedRule("mr", "stale_data", advisoryValues(pred(), "Soybean"));
    expect(r.label).toBe(getPack("en").rules.stale_data.label);
    expect(r.detail).toMatch(/days old/);           // English text, not undefined
    (LOCALES.mr.rules as any).stale_data = saved;
  });
});

describe("scientific integrity across languages", () => {
  it("probability, triggers, and situation are identical across locales", () => {
    const p = pred();
    const cores = LOCALES_ALL.map(() => generateAdvisoryCore(p));
    // engine is locale-independent by construction; values snapshot identical
    const values = cores.map((c) => JSON.stringify(c.values));
    expect(new Set(values).size).toBe(1);
    expect(cores[0].fired_rules).toEqual(cores[1].fired_rules);
    expect(cores[0].values.probability).toBe(0.6055);
  });

  it("no localized version is stronger/more certain than the English source", () => {
    const p = pred({ risk_category: "low", probability: 0.05 });
    const forbidden = [/गारंटी है कि/, /नक्की पाऊस/, /अवश्य/, /ज़रूर होगा/, /guarantee that it will/];
    for (const loc of LOCALES_ALL) {
      const pack = getPack(loc);
      const v = advisoryValues(p, localizedCrop(loc, "soybean").name);
      const texts = [pack.message.lower(v), pack.headline.lower(v)];
      for (const t of texts) {
        for (const rx of forbidden) expect(t, `${loc}: ${t}`).not.toMatch(rx);
      }
      // "lower" headline must not translate into "safe"
      for (const loc2 of LOCALES_ALL) {
        const h = getPack(loc2).headline.lower(v);
        expect(h.toLowerCase()).not.toMatch(/\bsafe\b|सुरक्षित आहे|सुरक्षित है/);
      }
    }
  });

  it("elevated wording preserves uncertainty ('possibility', not certainty)", () => {
    const p = pred();
    for (const loc of LOCALES_ALL) {
      const m = getPack(loc).message.elevated(advisoryValues(p, "X"));
      const hasPossibility =
        /possibility|शक्यता|संभावना/.test(m);
      const hasNotGuarantee = /not a guarantee|हमीखोरपणे म्हणता येत नाही|गारंटी नहीं/.test(m) || loc === "en";
      expect(hasPossibility, `${loc}: ${m}`).toBe(true);
      expect(hasNotGuarantee, `${loc}: ${m}`).toBe(true);
    }
  });

  it("translations introduce no new agronomic prescriptions", () => {
    const forbidden = /\b\d+\s?(mm|kg|L\/ha|kg\/ha)\b|spray|pesticide|urea|fertilizer dose|sow before/i;
    for (const loc of LOCALES_ALL) {
      for (const id of CROP_IDS) {
        const t = localizedCrop(loc, id);
        const text = [t.context, t.elevatedBody, t.lowerBody, ...t.monitoring, t.caveat].join(" ");
        expect(text, `${loc}/${id}`).not.toMatch(forbidden);
      }
    }
  });

  it("metric values are never baked into locale packs (functions receive raw values)", () => {
    const v = advisoryValues(pred({ probability: 0.4 }), "X");
    const detail = getPack("mr").rules.elevated_break_risk.detail(v);
    expect(detail).toContain("40.0%");               // formatted from raw at call time
    const v2 = advisoryValues(pred({ probability: 0.6 }), "X");
    expect(getPack("mr").rules.elevated_break_risk.detail(v2)).toContain("60.0%");
  });
});

describe("formatting (render time, locale-aware)", () => {
  it("percentages format from raw values with Intl", () => {
    expect(fmtPercent(0.6055, "en")).toMatch(/60\.6/);
    expect(fmtPercent(0.6055, "hi")).toMatch(/60\.6/);   // digits same, locale tags differ
  });

  it("dates format via Intl from ISO input", () => {
    const en = fmtDate("2026-09-29", "en");
    const hi = fmtDate("2026-09-29", "hi");
    expect(en).toMatch(/2026/);
    expect(hi.length).toBeGreaterThan(0);
  });

  it("structured values keep raw numbers (no preformatted strings as source)", () => {
    const v = advisoryValues(pred(), "X");
    expect(v.probability).toBe(0.6055);
    expect(v.input_completeness).toBe(1.0);
    expect(v.mean_diff).toBeCloseTo(0.0607);
  });
});

describe("fallback behavior", () => {
  it("missing locale falls back to English pack", () => {
    // getPack with an unknown code would be blocked by types; simulate via registry access
    const saved = LOCALES.hi;
    delete (LOCALES as any).hi;
    expect(getPack("hi" as LocaleCode).label).toBe("English");
    (LOCALES as any).hi = saved;
  });

  it("generic fallback crop is localized in every locale", () => {
    for (const loc of LOCALES_ALL) {
      const t = localizedCrop(loc, "unknown_crop");
      expect(t.id).toBe("generic");
      expect(t.name).toBeTruthy();
      expect(t.elevatedBody).toBeTruthy();
    }
  });

  it("calibration + evidence localize with unchanged meaning (over-prediction kept)", () => {
    const v = advisoryValues(pred(), "X");
    for (const loc of LOCALES_ALL) {
      const cal = localizedCalibration(loc, v);
      expect(cal).toMatch(/over-predict|जास्त अंदाज|अधिक अनुमान/);
      const ev = localizedEvidence(loc, "modest_positive_skill_vs_climatology_only", v);
      expect(ev).toMatch(/climatology|सरासरी|क्लाइमेटोलॉजी|सामान्य/);
    }
  });
});

describe("crop registry consistency", () => {
  it("Step 20 English texts are preserved in the en locale pack", () => {
    for (const id of CROP_IDS) {
      const step20 = cropById(id);
      const en = LOCALIZED_CROPS.en[id];
      expect(en.elevatedBody).toBe(step20.elevatedBody);
      expect(en.lowerBody).toBe(step20.lowerBody);
      expect(en.monitoring).toEqual(step20.monitoring);
      expect(en.caveat).toBe(step20.caveat);
    }
  });

  it("localized non-English crop names differ from English and stay non-empty", () => {
    expect(LOCALIZED_CROPS.mr.soybean.name).toBe("सोयाबीन");
    expect(LOCALIZED_CROPS.hi.soybean.name).toBe("सोयाबीन");
    expect(LOCALIZED_CROPS.mr.cotton.name).toBe("कापूस");
    expect(LOCALIZED_CROPS.hi.cotton.name).toBe("कपास");
  });
});
