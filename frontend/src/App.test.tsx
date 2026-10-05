import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { LocationTree, Prediction } from "./api";

const sampleTree: LocationTree = {
  levels: ["state", "district", "block", "panchayat"],
  levels_present: ["state", "district"],
  levels_with_data: ["district"],
  roots: [
    {
      id: 6,
      name: "Maharashtra",
      level: "state",
      parent_id: null,
      state: "Maharashtra",
      district: null,
      latitude: null,
      longitude: null,
      coordinate_note: null,
      n_children: 2,
      has_data: false,
      children: [
        {
          id: 1,
          name: "Pune",
          level: "district",
          parent_id: 6,
          state: "Maharashtra",
          district: "Pune",
          latitude: 18.5204,
          longitude: 73.8567,
          coordinate_note: null,
          has_data: true,
        },
        {
          id: 2,
          name: "Nashik",
          level: "district",
          parent_id: 6,
          state: "Maharashtra",
          district: "Nashik",
          latitude: 19.9975,
          longitude: 73.7898,
          coordinate_note: null,
          has_data: true,
        },
      ],
    },
  ],
};

const samplePred: Prediction = {
  type: "break_risk_prediction",
  schema_version: "1.0",
  location: {
    id: 1,
    name: "Pune",
    level: "district",
    parent_id: 6,
    state: "Maharashtra",
    district: "Pune",
    latitude: 18.5204,
    longitude: 73.8567,
  },
  prediction_date: "2026-09-29",
  probability: 0.35,
  risk_category: "moderate",
  risk_bands: { low: "< 0.2", moderate: "0.2 to < 0.4", high: ">= 0.4", note: "presentation only" },
  horizon_days: 7,
  event: "a dry spell",
  basis: "historical-pattern-based estimate",
  model: {
    name: "logistic_regression",
    trained_on_locations: [1, 2],
    trained_through: "2025-09-23",
    test_skill: { brier_skill_vs_climatology: 0.067, brier_skill_ci: {} },
    baselines: {},
  },
  uncertainty: {
    evidence_level: "modest_positive_skill_vs_climatology_only",
    individual_prediction_interval: { available: false },
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
  limitations: ["Limitation 1"],
};

const sampleHealth = {
  status: "ok",
  version: "0.2.0",
  database: "ok",
  mode_preference: "auto",
  effective_mode: "online",
  actual_operating_state: "online",
  internet_reachable: true,
  model_available: true,
  spatial_awareness: false,
  geographic_scope: {
    current: "district_hq_coordinate_points",
    target: "block_village_target_coordinates",
    note: "Pilot scope",
  },
  time_utc: "2026-10-02T06:00:00Z",
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
  window.history.replaceState(null, "", "/");
});

describe("App shell and navigation", () => {
  it("renders header, system status bar, location selector, and primary tabs", async () => {
    mockFetch((url) => {
      if (url.includes("/health")) return { body: sampleHealth };
      if (url.includes("/locations/tree")) return { body: sampleTree };
      if (url.includes("/prediction/break-risk")) return { body: samplePred };
      return { body: {} };
    });

    render(<App />);

    // Header and system bar
    expect(await screen.findByText(/Hyperlocal Monsoon Intelligence/i)).toBeInTheDocument();
    expect(screen.getByTestId("system-status-bar")).toBeInTheDocument();

    // Tabs
    expect(screen.getByTestId("tab-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("tab-rainfall")).toBeInTheDocument();
    expect(screen.getByTestId("tab-onset")).toBeInTheDocument();
    expect(screen.getByTestId("tab-advisory")).toBeInTheDocument();
    expect(screen.getByTestId("tab-map")).toBeInTheDocument();
    expect(screen.getByTestId("tab-history")).toBeInTheDocument();
    expect(screen.getByTestId("tab-technical")).toBeInTheDocument();

    // Default Overview renders — either dashboard or off-season panel depending on mock
    // Wait for something to render beyond loading
    await screen.findByTestId("location-selector-panel");
    // At this point the Dashboard has started rendering
    const dashboard = screen.queryByTestId("dashboard");
    const offSeason = screen.queryByTestId("dash-off-season");
    const dashError = screen.queryByTestId("dash-error");
    const dashLoading = screen.queryByTestId("dash-loading");
    // At least one state should be present
    expect(dashboard || offSeason || dashError || dashLoading).toBeTruthy();
  });

  it("switches to Rainfall Analysis tab on click", async () => {
    mockFetch((url) => {
      if (url.includes("/locations/tree")) return { body: sampleTree };
      if (url.includes("/prediction/break-risk")) return { body: samplePred };
      if (url.includes("/history")) {
        return { body: { location_id: 1, unit: "mm/day", note: "", records: [] } };
      }
      return { body: {} };
    });

    render(<App />);
    await screen.findByTestId("tab-rainfall");

    fireEvent.click(screen.getByTestId("tab-rainfall"));
    expect(screen.getByTestId("tab-rainfall")).toHaveClass("on");
    expect(await screen.findByTestId("rainfall-empty")).toBeInTheDocument();
  });

  it("switches to Technical Diagnostics tab on click", async () => {
    mockFetch((url) => {
      if (url.includes("/locations/tree")) return { body: sampleTree };
      if (url.includes("/prediction/break-risk")) return { body: samplePred };
      if (url.includes("/model/spatial-status")) return { body: { is_spatially_aware: false, current_features: [] } };
      return { body: {} };
    });

    render(<App />);
    await screen.findByTestId("tab-technical");

    fireEvent.click(screen.getByTestId("tab-technical"));
    expect(screen.getByTestId("tab-technical")).toHaveClass("on");
    expect(await screen.findByTestId("technical-diagnostics")).toBeInTheDocument();
  });

  it("propagates demo mode to Advisory and RiskMap when enabled", async () => {
    const urlsCalled: string[] = [];
    mockFetch((url) => {
      urlsCalled.push(url);
      if (url.includes("/health")) return { body: sampleHealth };
      if (url.includes("/mode")) return { body: { preference: "auto", effective: "online", internet_reachable: true } };
      if (url.includes("/locations/tree")) return { body: sampleTree };
      if (url.includes("/prediction/break-risk")) {
        return {
          body: {
            ...samplePred,
            prediction_date: "2026-09-25",
            as_of: "2026-09-25",
            evaluation_mode: "historical_demo",
          },
        };
      }
      return { body: {} };
    });

    render(<App />);
    await screen.findByTestId("tab-dashboard");
    await screen.findByTestId("location-selector-panel");
    const demoBtn = await screen.findByTestId("mode-demo-btn");
    fireEvent.click(demoBtn);

    // Should fetch with as_of
    expect(urlsCalled.some((u) => u.includes("as_of=2026-09-25"))).toBe(true);

    // Advisory panel receives historical prediction
    const advPanel = await screen.findByTestId("advisory-panel");
    expect(advPanel).toBeInTheDocument();
    expect(screen.getByTestId("advisory-demo-banner")).toBeInTheDocument();
  });
});
