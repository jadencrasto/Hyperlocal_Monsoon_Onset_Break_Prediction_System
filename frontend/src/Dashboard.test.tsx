import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import HistoryCharts from "./HistoryCharts";
import { ApiError, type Prediction } from "./api";

const basePred: Prediction = {
  type: "break_risk_prediction",
  schema_version: "1.0",
  location: {
    id: 2, name: "Nashik", level: "district", parent_id: 6, state: "Maharashtra",
    district: "Nashik", latitude: 19.9975, longitude: 73.7898,
  },
  prediction_date: "2026-09-29",
  probability: 0.6055,
  risk_category: "high",
  risk_bands: { low: "< 0.2", moderate: "0.2 to < 0.4", high: ">= 0.4", note: "presentation bands only" },
  horizon_days: 7,
  event: "a run of >= 5 consecutive days with rain < 2.5 mm within the next 7 days",
  basis: "historical-pattern-based estimate",
  model: {
    name: "logistic_regression",
    trained_on_locations: [1, 2, 3, 4, 5],
    trained_through: "2025-09-23",
    test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} },
    baselines: {},
  },
  uncertainty: {
    individual_prediction_interval: { available: false, reason: "point model only" },
    evaluation_skill: {
      brier_skill_vs_climatology: 0.067,
      brier_skill_ci: { low: 0.041, high: 0.096 },
      ci_interpretation: "population-level",
      n_test_years: 8,
    },
    calibration: { mean_diff: 0.0607, interpretation: "model over-predicts event probability on average" },
    per_year_stability: { n_years: 8, bss_min: 0.013, bss_max: 0.135, negative_years: 0 },
    evidence_level: "modest_positive_skill_vs_climatology_only",
  },
  data_status: {
    source: "stored_reanalysis_history",
    latest_rainfall_date: "2026-09-29",
    data_age_days: 0,
    freshness: "current",
    input_days_used: 9769,
    input_completeness: 1.0,
  },
  limitations: ["L1", "L2"],
} as unknown as Prediction;

const pred = (over: Partial<Prediction> = {}): Prediction => {
  const p = JSON.parse(JSON.stringify(basePred));
  return { ...p, ...over, model: { ...p.model, ...(over.model ?? {}) },
           data_status: { ...p.data_status, ...(over.data_status ?? {}) },
           uncertainty: { ...p.uncertainty, ...(over.uncertainty ?? {}) } };
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

describe("Dashboard", () => {
  it("renders summary, evidence, and data quality from the API", async () => {
    mockFetch(() => ({ body: pred() }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("dash-probability")).toHaveTextContent("60.6%");
    expect(screen.getByTestId("risk-category")).toHaveTextContent("high");
    expect(screen.getByTestId("dash-date")).toHaveTextContent("2026-09-29");
    expect(screen.getByTestId("evidence-level")).toHaveTextContent("modest_positive_skill_vs_climatology_only");
    expect(screen.getByTestId("eval-bss")).toHaveTextContent("6.700%");
    expect(screen.getByTestId("eval-ci")).toHaveTextContent("[0.041, 0.096]");
    expect(screen.getByTestId("ipi")).toHaveTextContent(/Not available/);
    expect(screen.getByTestId("calibration")).toHaveTextContent(/over-predicts/);
    expect(screen.getByTestId("per-year-stability")).toHaveTextContent(/0\.013 to 0\.135/);
    expect(screen.getByTestId("completeness")).toHaveTextContent("100%");
    expect(screen.queryByTestId("data-warning")).not.toBeInTheDocument();
  });

  it("shows stale + incomplete warnings when the API reports them", async () => {
    mockFetch(() => ({
      body: pred({
        data_status: {
          source: "stored_reanalysis_history", latest_rainfall_date: "2026-09-05",
          data_age_days: 24, freshness: "stale", input_days_used: 100, input_completeness: 0.97,
        },
      }),
    }));
    render(<Dashboard locationId={1} locationName="Pune" />);
    const warn = await screen.findByTestId("data-warning");
    expect(warn).toHaveTextContent(/24 days old/);
    expect(warn).toHaveTextContent(/gaps/);
    expect(screen.getByTestId("freshness")).toHaveTextContent("stale");
  });

  it("renders structured API error states without crashing", async () => {
    mockFetch(() => ({
      status: 422,
      body: { detail: { error: "insufficient_or_gappy_history", hint: "Recent rainfall has gaps" } },
    }));
    render(<Dashboard locationId={1} locationName="Pune" />);
    const err = await screen.findByTestId("dash-error");
    expect(err).toHaveTextContent(/Prediction unavailable/);
    expect(err).toHaveTextContent(/insufficient_or_gappy_history/);
  });

  it("renders model-unavailable (503) as an unavailable state", async () => {
    mockFetch(() => ({
      status: 503,
      body: { detail: { error: "model_unavailable", hint: "Run scripts/train_model.py first." } },
    }));
    render(<Dashboard locationId={1} locationName="Pune" />);
    expect(await screen.findByTestId("dash-error")).toHaveTextContent(/Prediction unavailable/);
  });

  it("shows the loading state before the fetch resolves", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    expect(screen.getByTestId("dash-loading")).toBeInTheDocument();
  });
});

describe("HistoryCharts", () => {
  const coverage = {
    location_id: 2, level: "district", n_locations_with_data: 1,
    rows: 9769, first_date: "2000-01-01", last_date: "2026-09-29",
  };
  const history = (n: number) => ({
    location_id: 2, unit: "mm/day", note: "reanalysis",
    records: Array.from({ length: n }, (_, i) => ({
      date: `2023-06-${String(i + 1).padStart(2, "0")}`,
      precip_mm: i % 3 === 0 ? 0 : 5.5,
      kind: "reanalysis", provider: "open_meteo", fetched_at: null,
    })),
  });

  it("renders observed rainfall bars and spell count", async () => {
    mockFetch((url) =>
      url.includes("/monsoon/dry-spells")
        ? { body: { location_id: 2, year: 2023, type: "historical_analysis", note: "", onset_date: null,
                    spells: [{ start: "2023-06-02", end: "2023-06-06", length_days: 5, total_mm: 0,
                               ended_by: "rain", scope: "local_dry_spell", resumption_date: "2023-06-07" }] } }
        : { body: history(30) }
    );
    render(<HistoryCharts locationId={2} />);
    expect(await screen.findByTestId("rainfall-chart")).toBeInTheDocument();
    expect(screen.getByTestId("spell-count")).toHaveTextContent(/1 dry-spell event/);
    expect(screen.getAllByTitle(/dry spell 2023-06-02/).length).toBeGreaterThan(0);
  });

  it("shows an honest empty state for seasons without stored data", async () => {
    // history returns empty records; spells return empty
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const body = String(url).includes("/monsoon/dry-spells")
        ? { location_id: 2, year: 1999, spells: [] }
        : { location_id: 2, unit: "mm/day", note: "", records: [] };
      return { ok: true, status: 200, json: async () => body } as Response;
    }));
    render(<HistoryCharts locationId={2} />);
    expect(await screen.findByTestId("history-empty")).toHaveTextContent(/No stored rainfall for this season/);
  });

  it("renders an error state when the history API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/coverage")) {
        return { ok: true, status: 200, json: async () => coverage } as Response;
      }
      return {
        ok: false, status: 422,
        json: async () => ({ detail: { error: "invalid_range", hint: "start must be on or before end" } }),
      } as Response;
    }));
    render(<HistoryCharts locationId={2} />);
    expect(await screen.findByTestId("history-error")).toHaveTextContent(/Historical view unavailable/);
  });
});
