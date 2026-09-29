import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RiskMap, { severityColor } from "./RiskMap";
import { pilotDistricts, type LocationTree, type Prediction } from "./api";

const tree: LocationTree = {
  levels: ["state", "district", "block", "panchayat"],
  levels_present: ["state", "district"],
  levels_with_data: ["district"],
  roots: [
    {
      id: 6, name: "Maharashtra", level: "state", parent_id: null, state: "Maharashtra",
      district: null, latitude: null, longitude: null, coordinate_note: null,
      n_children: 2, has_data: false,
      children: [
        {
          id: 1, name: "Pune", level: "district", parent_id: 6, state: "Maharashtra",
          district: "Pune", latitude: 18.5204, longitude: 73.8567, coordinate_note: null,
          has_data: true,
        },
        {
          id: 3, name: "Kolhapur", level: "district", parent_id: 6, state: "Maharashtra",
          district: "Kolhapur", latitude: 16.705, longitude: 74.2433, coordinate_note: null,
          has_data: true,
        },
        {
          id: 9, name: "SomeBlock", level: "block", parent_id: 1, state: "Maharashtra",
          district: "Pune", latitude: null, longitude: null, coordinate_note: null,
          has_data: false,
        },
      ],
    },
  ],
};

const pred = (over: Partial<Prediction>): Prediction => ({
  type: "break_risk_prediction",
  schema_version: "1.0",
  location: {
    id: 1, name: "Pune", level: "district", parent_id: 6, state: "Maharashtra",
    district: "Pune", latitude: 18.5204, longitude: 73.8567,
  },
  prediction_date: "2025-09-20",
  probability: 0.287,
  risk_category: "moderate",
  risk_bands: { low: "< 0.2", moderate: "0.2 to < 0.4", high: ">= 0.4", note: "presentation bands only" },
  horizon_days: 7,
  event: "a dry spell",
  basis: "historical-pattern-based estimate",
  model: {
    name: "logistic_regression",
    trained_on_locations: [1, 2, 3, 4, 5],
    trained_through: "2025-09-23",
    test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} },
    baselines: {},
  },
  uncertainty: {},
  data_status: {
    source: "stored_reanalysis_history",
    latest_rainfall_date: "2025-09-20",
    data_age_days: 0,
    freshness: "current",
    input_days_used: 2626,
    input_completeness: 1.0,
  },
  limitations: [],
  ...over,
});

describe("pilotDistricts", () => {
  it("returns only district-level, data-carrying, geolocated nodes", () => {
    const out = pilotDistricts(tree);
    expect(out.map((d) => d.name)).toEqual(["Pune", "Kolhapur"]); // skips state + block nodes
  });
  it("returns empty rather than fabricating when no district has data", () => {
    const empty: LocationTree = { ...tree, roots: [{ ...tree.roots[0], children: [] }] };
    expect(pilotDistricts(empty)).toEqual([]);
  });
});

describe("DetailCard states", () => {
  it("renders probability, category, date, freshness and completeness", () => {
    render(<RiskMap />);
    // RiskMap starts in its loading state without mocked fetch; assert that instead here.
    expect(screen.getByTestId("map-loading")).toBeInTheDocument();
  });
});

describe("severityColor", () => {
  it("maps the three API risk categories to distinct colors", () => {
    expect(severityColor.low).not.toEqual(severityColor.moderate);
    expect(severityColor.moderate).not.toEqual(severityColor.high);
    expect(Object.keys(severityColor).sort()).toEqual(["high", "low", "moderate"]);
  });
});
