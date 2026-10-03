import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RainfallAnalysis from "./RainfallAnalysis";

const sampleHistory = {
  location_id: 1,
  unit: "mm/day",
  note: "reanalysis",
  records: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-09-${String(i + 1).padStart(2, "0")}`,
    precip_mm: i >= 25 ? 0.0 : i % 2 === 0 ? 5.0 : 1.0,
    kind: "reanalysis",
    provider: "open_meteo",
    fetched_at: null,
  })),
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

describe("RainfallAnalysis", () => {
  it("renders loading state initially", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    render(<RainfallAnalysis locationId={1} locationName="Pune" />);
    expect(screen.getByTestId("rainfall-loading")).toBeInTheDocument();
  });

  it("renders rainfall metrics, trend analysis, and charts from history data", async () => {
    mockFetch(() => ({ body: sampleHistory }));
    render(<RainfallAnalysis locationId={1} locationName="Pune" />);

    expect(await screen.findByTestId("rainfall-analysis")).toBeInTheDocument();
    expect(screen.getByTestId("rainfall-insights")).toBeInTheDocument();
    expect(screen.getByText(/Has rainfall decreased recently\?/i)).toBeInTheDocument();
    expect(screen.getByText(/How long has the dry period lasted\?/i)).toBeInTheDocument();
    expect(screen.getByTestId("recent-rainfall-chart")).toBeInTheDocument();
    expect(screen.getByText(/Latest 1-Day Rain \(r1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/7-Day Total \(sum7\)/i)).toBeInTheDocument();
  });

  it("renders error state when API fails", async () => {
    mockFetch(() => ({
      status: 500,
      body: { detail: "Internal Server Error" },
    }));
    render(<RainfallAnalysis locationId={1} locationName="Pune" />);

    expect(await screen.findByTestId("rainfall-error")).toBeInTheDocument();
    expect(screen.getByText(/Rainfall analysis unavailable/i)).toBeInTheDocument();
  });
});
