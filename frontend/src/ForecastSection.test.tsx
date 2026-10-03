import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ForecastSection from "./ForecastSection";

const sampleForecast = {
  location_id: 1,
  type: "third_party_forecast",
  provider: "open_meteo",
  retrieved_at: "2026-09-30T06:00:00Z",
  age_hours: 1.5,
  freshness: "fresh",
  stale_after_hours: 24,
  spatial_note: "Nearest grid point",
  label: "Cached forecast, within freshness window",
  records: [
    { date: "2026-10-01", precip_mm: 8.5 },
    { date: "2026-10-02", precip_mm: 12.0 },
    { date: "2026-10-03", precip_mm: 0.0 },
    { date: "2026-10-04", precip_mm: 0.2 },
    { date: "2026-10-05", precip_mm: 1.1 },
    { date: "2026-10-06", precip_mm: 0.0 },
    { date: "2026-10-07", precip_mm: 4.5 },
  ],
};

const sampleForecastStatus = {
  location_id: 1,
  forecast_available: true,
  freshness: {
    status: "valid",
    age_hours: 1.5,
    stale: false,
    provider: "open_meteo",
    stale_after_hours: 24,
  },
  n_forecast_days: 7,
  prediction_integration: {
    integrated: false,
    reason:
      "The current ML model uses only historical rainfall features. Third-party forecast data is displayed separately but does NOT feed into the break-risk prediction model.",
    required_for_integration: [
      "Forecast-based features in the ML pipeline",
      "Reforecast archive for training (e.g. ECMWF S2S)",
      "Validation showing forecast features improve skill",
    ],
  },
  provider_info: {
    name: "open_meteo",
    retrieved_at: "2026-09-30T06:00:00Z",
    age_hours: 1.5,
    stale: false,
  },
  offline_usable: true,
  offline_note: "Cached forecast data can be served offline",
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

describe("ForecastSection", () => {
  it("renders weather forecast and clearly separates it from the ML break-risk prediction", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) {
        return { body: sampleForecastStatus };
      }
      return { body: sampleForecast };
    });

    render(<ForecastSection locationId={1} locationName="Pune" />);

    expect(await screen.findByTestId("forecast-section")).toBeInTheDocument();

    // 1. Distinction banner
    expect(screen.getByTestId("forecast-model-distinction")).toBeInTheDocument();
    expect(screen.getAllByText(/WEATHER FORECAST/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/MODEL PREDICTION/i)[0]).toBeInTheDocument();
    expect(screen.getByTestId("forecast-model-distinction")).toHaveTextContent(
      /Forecast currently informs the weather view; it is not yet an input to the break-risk model/i
    );

    // 2. Forecast records
    expect(screen.getByTestId("forecast-content")).toBeInTheDocument();
    expect(screen.getByText("8.5")).toBeInTheDocument();
    expect(screen.getByText("12.0")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-freshness-badge")).toHaveTextContent(/Fresh forecast/i);

    // 3. Integration panel
    expect(screen.getByTestId("forecast-integration-panel")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-integration-status")).toHaveTextContent(/Not Integrated/i);
    expect(screen.getByText(/Reforecast archive for training/i)).toBeInTheDocument();
  });

  // ISSUE 3: Location consistency — heading shows the correct location name
  it("displays the selected location name in the forecast heading", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) return { body: { ...sampleForecastStatus, location_id: 4 } };
      return { body: { ...sampleForecast, location_id: 4 } };
    });

    render(<ForecastSection locationId={4} locationName="Nagpur" />);
    expect(await screen.findByTestId("forecast-section")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-location-name")).toHaveTextContent("Nagpur");
  });

  // ISSUE 3: Regression test — switching location updates heading
  it("updates heading when location changes from Nagpur to Nashik", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) return { body: sampleForecastStatus };
      return { body: sampleForecast };
    });

    const { rerender } = render(<ForecastSection locationId={4} locationName="Nagpur" />);
    expect(await screen.findByTestId("forecast-location-name")).toHaveTextContent("Nagpur");

    rerender(<ForecastSection locationId={2} locationName="Nashik" />);
    // After rerender, the loading state shows Nashik
    expect(screen.getByText(/Loading forecast data for Nashik/i)).toBeInTheDocument();
  });

  // ISSUE 4: Forecast not loaded state
  it("shows 'forecast not loaded' when forecast API returns no records", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) {
        return { body: { ...sampleForecastStatus, forecast_available: true } };
      }
      return { body: { ...sampleForecast, records: [] } };
    });

    render(<ForecastSection locationId={1} locationName="Pune" />);
    expect(await screen.findByTestId("forecast-not-loaded")).toBeInTheDocument();
    expect(screen.getByText(/Forecast not loaded yet/i)).toBeInTheDocument();
  });

  // ISSUE 4: Forecast unavailable state
  it("shows 'forecast unavailable' when forecast status reports not available", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) {
        return {
          body: {
            ...sampleForecastStatus,
            forecast_available: false,
            freshness: { status: "no_data", message: "No data from provider" },
          },
        };
      }
      // forecast endpoint returns empty records (no data)
      return { body: { ...sampleForecast, records: [] } };
    });

    render(<ForecastSection locationId={1} locationName="Pune" />);
    expect(await screen.findByTestId("forecast-unavailable")).toBeInTheDocument();
  });

  // ISSUE 4: Stale forecast state
  it("shows stale notice when forecast is stale", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) return { body: sampleForecastStatus };
      return { body: { ...sampleForecast, freshness: "stale" } };
    });

    render(<ForecastSection locationId={1} locationName="Pune" />);
    expect(await screen.findByTestId("forecast-stale-notice")).toBeInTheDocument();
  });

  // ISSUE 5: Forecast response location mismatch — discard mismatched data
  it("discards forecast data when response location_id does not match selected location", async () => {
    mockFetch((url) => {
      if (url.includes("/forecast/status")) return { body: { ...sampleForecastStatus, location_id: 1 } };
      // Return forecast for location_id=2 (Nashik) when requesting location_id=4 (Nagpur)
      return { body: { ...sampleForecast, location_id: 2 } };
    });

    render(<ForecastSection locationId={4} locationName="Nagpur" />);
    // Should show error about mismatch, not Nashik data
    expect(await screen.findByTestId("forecast-failed")).toBeInTheDocument();
    // Heading still says Nagpur
    expect(screen.getByTestId("forecast-location-name")).toHaveTextContent("Nagpur");
  });
});
