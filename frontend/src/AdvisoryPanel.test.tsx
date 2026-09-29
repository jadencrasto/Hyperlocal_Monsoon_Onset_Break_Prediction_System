import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AdvisoryPanel from "./AdvisoryPanel";
import type { Prediction } from "./api";

const pred = (over: Partial<Prediction> = {}): Prediction => {
  const p = {
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
             test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} }, baselines: {},
             caveats: ["c1"] },
    uncertainty: {
      individual_prediction_interval: { available: false, reason: "point model" },
      evaluation_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: { low: 0.041, high: 0.096 }, n_test_years: 8 },
      calibration: { mean_diff: 0.0607, interpretation: "model over-predicts event probability on average" },
      per_year_stability: { n_years: 8, bss_min: 0.013, bss_max: 0.135, negative_years: 0 },
      evidence_level: "modest_positive_skill_vs_climatology_only",
    },
    data_status: { source: "stored_reanalysis_history", latest_rainfall_date: "2026-09-29",
                   data_age_days: 0, freshness: "current", input_days_used: 9769,
                   input_completeness: 1.0 },
    limitations: ["L1"],
  } as unknown as Prediction;
  return { ...p, ...over };
};

describe("AdvisoryPanel", () => {
  it("renders advisory for a selected crop with status and headline", () => {
    render(<AdvisoryPanel pred={pred()} />);
    expect(screen.getByTestId("advisory-panel")).toBeInTheDocument();
    expect(screen.getByTestId("advisory-status")).toHaveTextContent(/caution/i);
    expect(screen.getByTestId("advisory-headline")).toHaveTextContent(/elevated dry-spell risk/i);
    expect(screen.getByTestId("advisory-message")).toHaveTextContent(/flowering or pod fill/);
    expect(screen.getByTestId("advisory-panel")).toHaveTextContent(/Soybean/);
    expect(screen.getByTestId("advisory-disclaimer")).toHaveTextContent(/Informational advisory only/);
  });

  it("changes crop and re-phrases the advisory", () => {
    render(<AdvisoryPanel pred={pred()} />);
    const first = screen.getByTestId("advisory-message").textContent;
    fireEvent.change(screen.getByTestId("crop-select"), { target: { value: "cotton" } });
    expect(screen.getByTestId("advisory-message")).toHaveTextContent(/boll development/);
    expect(screen.getByTestId("advisory-message").textContent).not.toBe(first);
    expect(screen.getByTestId("advisory-panel")).toHaveTextContent(/Cotton/);
  });

  it("explains why it was generated using real prediction fields (localized labels, not raw IDs)", () => {
    render(<AdvisoryPanel pred={pred()} />);
    fireEvent.click(screen.getByTestId("why-toggle"));
    const why = screen.getByTestId("why-panel");
    // Step 21: labels are localized; bare internal rule IDs must not be shown
    expect(why).toHaveTextContent(/Elevated break-risk indication:.*60\.6%/);
    expect(why).toHaveTextContent(/Limited evaluation evidence:.*modest_positive_skill_vs_climatology_only/);
    expect(why).toHaveTextContent(/Historical over-prediction/);
    expect(why).toHaveTextContent(/logistic_regression/);
    expect(why.textContent).not.toMatch(/elevated_break_risk|limited_evidence:/);
  });

  it("flags stale data in cautions", () => {
    const p = pred();
    p.data_status = { ...p.data_status, freshness: "stale", data_age_days: 24 };
    render(<AdvisoryPanel pred={p} />);
    expect(screen.getByTestId("advisory-cautions")).toHaveTextContent(/may not reflect current field conditions/);
    expect(screen.getByTestId("advisory-status")).toHaveTextContent(/Limited data/i);
  });

  it("renders for every documented crop without crashing", () => {
    for (const id of ["soybean", "cotton", "maize", "groundnut", "pigeon_pea", "generic"]) {
      const { unmount } = render(<AdvisoryPanel key={id} pred={pred()} />);
      expect(screen.getByTestId("advisory-panel")).toBeInTheDocument();
      unmount();
    }
  });
});
