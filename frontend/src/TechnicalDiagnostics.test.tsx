import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TechnicalDiagnostics from "./TechnicalDiagnostics";

const sampleModelEval = {
  model_name: "logistic_regression",
  model_class: "LogisticRegression",
  intended_use: "Demonstration of monsoon break-risk probability",
  caveats: ["Point estimate only"],
  dataset: { first_date: "1997-01-01", last_date: "2025-09-23", n_years: 29 },
  test: {
    brier_skill_vs_climatology: 0.067,
    brier_skill_ci: { low: 0.041, high: 0.096, n_years: 8 },
    model: { brier: 0.11838 },
    baseline_climatology: { brier: 0.12689 },
    baseline_dry_run_conditioned: { brier: 0.11445 },
    calibration: { mean_predicted: 0.243, observed_rate: 0.182, mean_diff: 0.061 },
  },
};

const sampleSpatial = {
  is_spatially_aware: false,
  spatial_features_in_model: false,
  current_features: [
    "r1",
    "sum3",
    "sum7",
    "sum14",
    "sum30",
    "rainy_frac14",
    "dry_run",
    "doy_sin",
    "doy_cos",
  ],
  n_features: 9,
  location_treatment: "pooled_identical",
  location_treatment_note: "Model has no spatial features",
  candidate_approaches: [
    {
      name: "Spatial Lags",
      description: "Neighborhood rainfall features",
      status: "not_implemented",
    },
  ],
};

const sampleQuality = {
  location_id: 1,
  status: "valid",
  issues: [],
  total_records: 9769,
  first_date: "1997-01-01",
  last_date: "2025-09-23",
  expected_days: 9769,
  actual_days: 9769,
  missing_days: 0,
  duplicate_count: 0,
  null_precip_count: 0,
  impossible_values: 0,
  continuity_ratio: 1.0,
  providers: ["open_meteo"],
  kinds: ["reanalysis"],
};

function mockFetch(handler: (url: string) => { status?: number; body?: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const { status = 200, body } = handler(String(url));
      return {
        ok: (status ?? 200) === 200,
        status,
        json: async () => body,
      } as Response;
    })
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("TechnicalDiagnostics", () => {
  it("renders model features, spatial status, and honest Brier score comparison", async () => {
    mockFetch((url) => {
      if (url.includes("/model/spatial-status")) return { body: sampleSpatial };
      if (url.includes("/model/evaluation")) return { body: sampleModelEval };
      if (url.includes("/data-quality")) return { body: sampleQuality };
      return { body: {} };
    });

    render(<TechnicalDiagnostics locationId={1} locationName="Pune" />);

    expect(await screen.findByTestId("technical-diagnostics")).toBeInTheDocument();

    // 0. User-facing model summary (Issue 6)
    expect(screen.getByTestId("model-summary")).toBeInTheDocument();
    expect(screen.getByText(/Current Break-Risk Model/i)).toBeInTheDocument();
    expect(screen.getByText(/5 Maharashtra pilot locations/i)).toBeInTheDocument();
    expect(screen.getAllByText(/7-day break risk/i).length).toBeGreaterThanOrEqual(1);

    // 1. Model specs & features
    expect(screen.getByText(/r1, sum3, sum7, sum14, sum30, rainy_frac14, dry_run, doy_sin, doy_cos/i)).toBeInTheDocument();
    expect(screen.getByTestId("spatial-status-text")).toHaveTextContent(
      /None — Model has no spatial features/i
    );

    // 2. Brier score comparison table
    expect(screen.getByTestId("brier-comparison-table")).toBeInTheDocument();
    expect(screen.getByText("0.12689")).toBeInTheDocument(); // Climatology
    expect(screen.getByText("0.11838")).toBeInTheDocument(); // Model
    expect(screen.getByText("0.11445")).toBeInTheDocument(); // Dry-run heuristic
    expect(screen.getByTestId("brier-honesty-note")).toHaveTextContent(
      /The system does not claim superiority over the heuristic/i
    );
  });

  it("switches to Data Quality Audit tab and shows audit metrics", async () => {
    mockFetch((url) => {
      if (url.includes("/model/spatial-status")) return { body: sampleSpatial };
      if (url.includes("/data-quality")) return { body: sampleQuality };
      return { body: {} };
    });

    render(<TechnicalDiagnostics locationId={1} locationName="Pune" />);
    await screen.findByTestId("technical-diagnostics");

    fireEvent.click(screen.getByTestId("tech-tab-quality"));
    expect(screen.getByTestId("panel-quality-diagnostics")).toBeInTheDocument();
    expect(screen.getByText(/Zero invalid physical values detected/i)).toBeInTheDocument();
    expect(screen.getByText(/Zero duplicate records/i)).toBeInTheDocument();
  });
});
