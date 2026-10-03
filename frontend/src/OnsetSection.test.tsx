import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OnsetSection from "./OnsetSection";

const sampleOnset = {
  location_id: 1,
  year: 2023,
  type: "observed_onset_detection",
  analysis_kind: "retrospective",
  status: "detected",
  observed_onset: "2023-06-08",
  onset_date: "2023-06-08",
  detail: { criteria: "imd_local" },
  config: { min_consecutive_days: 2, min_precip_mm: 2.5 },
  note: "Retrospective onset detection from historical rainfall",
};

const sampleOnsetPrediction = {
  location_id: 1,
  type: "onset_prediction",
  prediction_status: "not_implemented",
  predicted_onset: null,
  confidence: null,
  observed_onset: null,
  note: "Future onset prediction is not yet implemented.",
  requirements: [
    "Forecast-driven model (e.g. ECMWF S2S reforecast archive)",
    "Calibrated probability estimates for onset timing",
    "Validation against historical observed onsets",
  ],
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

describe("OnsetSection", () => {
  it("renders observed historical onset detection and clearly marks future prediction as unavailable", async () => {
    mockFetch((url) => {
      if (url.includes("/monsoon/onset-prediction")) {
        return { body: sampleOnsetPrediction };
      }
      return { body: sampleOnset };
    });

    render(<OnsetSection locationId={1} locationName="Pune" />);

    expect(await screen.findByTestId("onset-section")).toBeInTheDocument();

    // 1. Retrospective observed onset
    expect(screen.getByTestId("observed-onset-card")).toBeInTheDocument();
    expect(screen.getByTestId("onset-status")).toHaveTextContent(/Onset Detected/i);
    expect(screen.getByTestId("observed-onset-date")).toHaveTextContent("2023-06-08");
    expect(screen.getByTestId("onset-truthfulness-note")).toHaveTextContent(
      /retrospective onset detection/i
    );
    expect(screen.getByTestId("onset-truthfulness-note")).toHaveTextContent(
      /NOT a future onset prediction/i
    );

    // 2. Future onset prediction unavailable state
    expect(screen.getByTestId("future-onset-card")).toBeInTheDocument();
    expect(screen.getByTestId("future-onset-badge")).toHaveTextContent(/Not Available Yet/i);
    expect(screen.getByTestId("future-onset-unavailable-state")).toHaveTextContent(
      /Future monsoon onset prediction is not yet available/i
    );
    // Availability summary items
    expect(screen.getByText(/Observed onset detection/i)).toBeInTheDocument();
    expect(screen.getByText(/7-day weather forecast/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Future onset prediction/i).length).toBeGreaterThanOrEqual(1);
    // S2S still mentioned in technical prerequisites
    expect(screen.getByText(/ECMWF Sub-seasonal to Seasonal \(S2S\)/i)).toBeInTheDocument();
  });
});
