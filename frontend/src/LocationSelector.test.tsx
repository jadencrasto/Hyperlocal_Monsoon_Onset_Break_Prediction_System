import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LocationSelector from "./LocationSelector";
import type { LocationNode } from "./api";

const mockDistricts: LocationNode[] = [
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
];

describe("LocationSelector", () => {
  it("renders district selector with pilot locations and geographic scope pill", () => {
    const onSelect = vi.fn();
    render(<LocationSelector districts={mockDistricts} selectedId={1} onSelect={onSelect} />);

    expect(screen.getByTestId("location-select")).toBeInTheDocument();
    expect(screen.getByTestId("geographic-scope-pill")).toHaveTextContent(
      /Pilot location — district-HQ coordinate/i
    );
    expect(screen.getByText(/Pune \(Pune, Maharashtra\)/)).toBeInTheDocument();
    expect(screen.getByText(/Nashik \(Nashik, Maharashtra\)/)).toBeInTheDocument();
  });

  it("calls onSelect when changing district", () => {
    const onSelect = vi.fn();
    render(<LocationSelector districts={mockDistricts} selectedId={1} onSelect={onSelect} />);

    fireEvent.change(screen.getByTestId("location-select"), { target: { value: "2" } });
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("toggles the hierarchy breakdown and shows unavailable notes for block/panchayat", () => {
    render(<LocationSelector districts={mockDistricts} selectedId={1} onSelect={vi.fn()} />);

    expect(screen.queryByTestId("hierarchy-breakdown")).not.toBeInTheDocument();

    // Toggle open
    fireEvent.click(screen.getByTestId("toggle-hierarchy-btn"));
    expect(screen.getByTestId("hierarchy-breakdown")).toBeInTheDocument();

    // Honest representation of levels
    expect(screen.getByText(/1\. State/)).toBeInTheDocument();
    expect(screen.getByText(/2\. District/)).toBeInTheDocument();
    expect(screen.getByTestId("block-unavailable-note")).toHaveTextContent(
      /Data not available for this level yet/i
    );
    expect(screen.getByTestId("panchayat-unavailable-note")).toHaveTextContent(
      /Data not available for this level yet/i
    );
  });
});
