import { describe, expect, it } from "vitest";
import { generateAdvisoryCore, ADVISORY_DISCLAIMER } from "./engine";
import { CROPS, GENERIC_TEMPLATE, composeAdvisory, cropById } from "./crops";
import type { Prediction } from "../api";

const pred = (over: Partial<Prediction> = {}): Prediction => {
  const p: Prediction = {
    type: "break_risk_prediction",
    schema_version: "1.0",
    location: { id: 2, name: "Nashik", level: "district", parent_id: 6, state: "Maharashtra",
                district: "Nashik", latitude: 19.9975, longitude: 73.7898 },
    prediction_date: "2026-09-29",
    probability: 0.6055,
    risk_category: "high",
    risk_bands: { low: "< 0.2", moderate: "0.2 to < 0.4", high: ">= 0.4", note: "presentation bands only" },
    horizon_days: 7,
    event: "a dry spell",
    basis: "historical-pattern-based estimate",
    model: { name: "logistic_regression", trained_on_locations: [1, 2, 3, 4, 5],
             trained_through: "2025-09-23",
             test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} }, baselines: {} },
    uncertainty: {
      individual_prediction_interval: { available: false, reason: "point model" },
      evaluation_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: { low: 0.041, high: 0.096 },
                          n_test_years: 8 },
      calibration: { mean_diff: 0.0607, interpretation: "over-predicts" },
      per_year_stability: { n_years: 8, bss_min: 0.013, bss_max: 0.135, negative_years: 0 },
      evidence_level: "modest_positive_skill_vs_climatology_only",
    },
    data_status: { source: "stored_reanalysis_history", latest_rainfall_date: "2026-09-29",
                   data_age_days: 0, freshness: "current", input_days_used: 9769,
                   input_completeness: 1.0 },
    limitations: [],
  };
  return { ...p, ...over,
    uncertainty: { ...p.uncertainty, ...(over.uncertainty ?? {}) },
    data_status: { ...p.data_status, ...(over.data_status ?? {}) } };
};

const rules = (core: ReturnType<typeof generateAdvisoryCore>) => core.triggers.map((t) => t.rule);

describe("Step 19 rule engine", () => {
  it("elevated break-risk fires rule D with non-guarantee wording", () => {
    const core = generateAdvisoryCore(pred());
    expect(rules(core)).toContain("elevated_break_risk");
    expect(core.headline).toMatch(/elevated dry-spell risk/i);
    expect(core.message).toMatch(/not a guarantee/i);
    expect(core.message).toMatch(/Consider monitoring|consider monitoring/);
  });

  it("low break-risk fires rule E and never becomes 'safe'", () => {
    const core = generateAdvisoryCore(pred({ risk_category: "low", probability: 0.05 }));
    expect(rules(core)).toContain("lower_break_risk");
    expect(core.headline).toMatch(/lower dry-spell risk/i);
    expect(core.message).toMatch(/local rainfall can still differ/i);
    expect(core.message.toLowerCase()).not.toMatch(/\bsafe\b/);
  });

  it("stale data escalates to limited_data with precedence wording", () => {
    const core = generateAdvisoryCore(
      pred({ data_status: { freshness: "stale", data_age_days: 24 } as any })
    );
    expect(core.status).toBe("limited_data");
    expect(rules(core)).toContain("stale_data");
    expect(core.cautions.join(" ")).toMatch(/may not reflect current (field )?conditions/i);
  });

  it("incomplete input escalates to caution", () => {
    const core = generateAdvisoryCore(
      pred({ data_status: { input_completeness: 0.97 } as any })
    );
    expect(core.status).toBe("caution");
    expect(rules(core)).toContain("incomplete_input");
    expect(core.cautions.join(" ")).toMatch(/gaps/i);
  });

  it("limited evidence produces conservative 'model-based indication' wording", () => {
    const core = generateAdvisoryCore(pred()); // modest evidence by default
    expect(rules(core)).toContain("limited_evidence");
    expect(core.cautions.join(" ")).toMatch(/model-based indication, not a dependable forecast/i);
  });

  it("strong evidence does not add the limited-evidence caution", () => {
    const core = generateAdvisoryCore(
      pred({ uncertainty: { evidence_level: "positive_skill_vs_climatology_and_heuristic" } as any })
    );
    expect(rules(core)).not.toContain("limited_evidence");
  });

  it("over-prediction calibration adds a caution but never alters the probability", () => {
    const core = generateAdvisoryCore(pred());
    expect(rules(core)).toContain("calibration_overprediction");
    expect(core.cautions.join(" ")).toMatch(/higher probabilities than the observed event frequency/i);
    expect(core.cautions.join(" ")).toMatch(/has not been adjusted/i);
  });

  it("small calibration differences do not fire the caution", () => {
    const core = generateAdvisoryCore(pred({ uncertainty: { calibration: { mean_diff: 0.01 } } as any }));
    expect(rules(core)).not.toContain("calibration_overprediction");
  });

  it("unavailable individual interval is logged and never presented as an interval", () => {
    const core = generateAdvisoryCore(pred());
    expect(rules(core)).toContain("no_individual_interval");
    const text = JSON.stringify(core);
    expect(text).not.toMatch(/interval: \[/);
    expect(text).not.toMatch(/confidence interval around this prediction/i);
  });

  it("is deterministic: identical input, identical output", () => {
    const p = pred();
    expect(generateAdvisoryCore(p)).toEqual(generateAdvisoryCore(p));
    expect(generateAdvisoryCore(p)).toEqual(generateAdvisoryCore(structuredClone(p)));
  });

  it("status escalates monotonically to the most severe condition", () => {
    const worst = generateAdvisoryCore(
      pred({ data_status: { freshness: "stale", data_age_days: 30, input_completeness: 0.8 } as any })
    );
    expect(worst.status).toBe("limited_data");
  });

  it("exports the shared disclaimer with local-guidance wording", () => {
    expect(ADVISORY_DISCLAIMER).toMatch(/Informational advisory only/i);
    expect(ADVISORY_DISCLAIMER).toMatch(/local agricultural guidance/i);
  });
});

describe("Step 20 crop templates", () => {
  it("has exactly the five documented crops plus a generic fallback", () => {
    expect(CROPS.map((c) => c.id)).toEqual(
      ["soybean", "cotton", "maize", "groundnut", "pigeon_pea"]
    );
    expect(cropById("nonexistent")).toBe(GENERIC_TEMPLATE);
  });

  for (const crop of CROPS) {
    it(`${crop.id}: elevated + lower compose distinct, crop-specific advisories`, () => {
      const elevated = composeAdvisory(generateAdvisoryCore(pred()), crop);
      const lower = composeAdvisory(generateAdvisoryCore(pred({ risk_category: "low", probability: 0.05 })), crop);
      expect(elevated.cropName).toBe(crop.name);
      expect(elevated.message).toContain(crop.elevatedBody);
      expect(lower.message).toContain(crop.lowerBody);
      expect(elevated.message).not.toBe(lower.message);
      expect(elevated.monitoring).toEqual(crop.monitoring);
      expect(elevated.cautions).toContain(crop.caveat);
    });
  }

  it("unknown crop falls back to the generic template without crashing", () => {
    const t = cropById("banana");
    const out = composeAdvisory(generateAdvisoryCore(pred()), t);
    expect(out.cropName).toBe("General cropping");
    expect(out.message).toMatch(/kharif crops/i);
  });

  it("templates contain no fabricated doses, doses-like numbers, or sowing dates", () => {
    for (const c of [...CROPS, GENERIC_TEMPLATE]) {
      const text = [c.elevatedBody, c.lowerBody, ...c.monitoring, c.caveat].join(" ");
      expect(text).not.toMatch(/\b\d+\s?(mm|kg|litres|liters|L\/ha|kg\/ha)\b/i);
      expect(text).not.toMatch(/spray|pesticide|fertilizer dose|urea|sow before/i);
    }
  });
});
