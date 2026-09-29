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
    provider: "open_meteo",
    latest_rainfall_date: "2026-09-29",
    data_age_days: 0,
    freshness: "current",
    input_days_used: 9769,
    input_completeness: 1.0,
    cache_status: "cached",
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

// ---- Step 23: cache/offline indicators ----------------------------------------------

describe("Step 23 cache/offline indicators", () => {
  it("shows the cached-data indicator with provider provenance (online default)", async () => {
    mockFetch(() => ({ body: pred() }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    const panel = await screen.findByTestId("dash-data-quality");
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/Cached rainfall data/i);
    expect(screen.getByTestId("cached-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("offline-indicator")).not.toBeInTheDocument();
    expect(screen.getByTestId("cache-provider")).toHaveTextContent("provider: open_meteo");
    expect(screen.getByTestId("data-provider")).toHaveTextContent("open_meteo");
    expect(panel).toHaveTextContent(/latest observation/i);
    // never claims live data
    expect(panel.textContent).not.toMatch(/live/i);
  });

  it("shows the offline indicator when the API reports offline cache_status", async () => {
    mockFetch(() => ({
      body: pred({
        data_status: {
          source: "stored_reanalysis_history", provider: "open_meteo",
          latest_rainfall_date: "2026-09-29", data_age_days: 0, freshness: "current",
          input_days_used: 9769, input_completeness: 1.0, cache_status: "offline",
        },
      }),
    }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/Offline mode/i);
    expect(screen.getByTestId("offline-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("cached-indicator")).not.toBeInTheDocument();
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/using locally stored data/i);
  });

  it("pairs the cached indicator with the stale-data warning (external failure + fallback)", async () => {
    mockFetch(() => ({
      body: pred({
        data_status: {
          source: "stored_reanalysis_history", provider: "open_meteo",
          latest_rainfall_date: "2026-09-05", data_age_days: 24, freshness: "stale",
          input_days_used: 100, input_completeness: 1.0, cache_status: "cached",
        },
      }),
    }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    // cached fallback is stated factually, and the stale warning is still shown
    expect(screen.getByTestId("cached-indicator")).toHaveTextContent(/Cached rainfall data/i);
    expect(screen.getByTestId("data-warning")).toHaveTextContent(/24 days old/);
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/24 days old/);
  });

  it("shows the unavailable-data state when local history is insufficient", async () => {
    mockFetch(() => ({
      status: 422,
      body: { detail: { error: "insufficient_or_gappy_history", hint: "gap in recent rainfall" } },
    }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    const err = await screen.findByTestId("dash-error");
    expect(err).toHaveTextContent(/Prediction unavailable/);
    expect(err).toHaveTextContent(/insufficient_or_gappy_history/);
  });  it("defaults provider and cache_status gracefully when absent (older payload)", async () => {
    const p = pred();
    delete (p.data_status as Record<string, unknown>).provider;
    delete (p.data_status as Record<string, unknown>).cache_status;
    mockFetch(() => ({ body: p }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    expect(screen.getByTestId("cache-provider")).toHaveTextContent("provider: unknown");
    // no cache_status -> treated as the normal online cached case
    expect(screen.getByTestId("cached-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("offline-indicator")).not.toBeInTheDocument();
  });

  it("shows the explicit stale-data indicator when freshness is stale", async () => {
    mockFetch(() => ({
      body: pred({
        data_status: {
          source: "stored_reanalysis_history", provider: "open_meteo",
          latest_rainfall_date: "2026-08-15", data_age_days: 45, freshness: "stale",
          input_days_used: 9769, input_completeness: 1.0, cache_status: "cached",
        },
      }),
    }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    // staleness refers to the DATA, and stays explicit — never downgraded to current
    expect(screen.getByTestId("stale-indicator")).toHaveTextContent(/rainfall data is stale/i);
    expect(screen.getByTestId("freshness")).toHaveTextContent("stale");
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/45 days old/);
  });

  it("shows the online-failure + cached-fallback line from last_sync_failure", async () => {
    mockFetch(() => ({
      body: pred({
        last_sync_failure: {
          kind: "history", provider: "open_meteo", category: "timeout",
          message: "Open-Meteo timed out after 3 attempts",
          finished_at: "2026-09-30T05:12:00+00:00",
        },
      }),
    }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    const fb = screen.getByTestId("fallback-indicator");
    expect(fb).toHaveTextContent(/Online data unavailable \(timeout\)/i);
    expect(fb).toHaveTextContent(/using cached rainfall data/i);
  });

  it("shows no fallback line when last_sync_failure is null (healthy)", async () => {
    mockFetch(() => ({ body: pred({ last_sync_failure: null }) }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    expect(screen.queryByTestId("fallback-indicator")).not.toBeInTheDocument();
  });

  it("displays provider, source and age facts in the data-quality panel", async () => {
    mockFetch(() => ({ body: pred() }));
    render(<Dashboard locationId={2} locationName="Nashik" />);
    await screen.findByTestId("dash-data-quality");
    expect(screen.getByTestId("data-provider")).toHaveTextContent("open_meteo");
    expect(screen.getByTestId("cache-provider")).toHaveTextContent("provider: open_meteo");
    expect(screen.getByTestId("cache-indicator")).toHaveTextContent(/latest observation 2026-09-29 \(0 days old\)/);
    expect(screen.getByTestId("freshness")).toHaveTextContent("current");
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
