import React, { useState } from "react";
import { FiAlertTriangle, FiCheck, FiChevronDown, FiChevronUp, FiMapPin } from "react-icons/fi";
import type { LocationNode, LocationTree } from "./api";

interface LocationSelectorProps {
  districts: LocationNode[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  tree?: LocationTree | null;
}

export default function LocationSelector({
  districts,
  selectedId,
  onSelect,
  tree,
}: LocationSelectorProps) {
  const [showHierarchy, setShowHierarchy] = useState(false);

  const selectedDistrict = districts.find((d) => d.id === selectedId) ?? districts[0] ?? null;

  return (
    <div className="location-selector-container" data-testid="location-selector-panel">
      <div className="location-primary-row">
        <div className="location-select-wrap">
          <label className="toolbar-label" htmlFor="loc-select">
            <span className="label-text">Select District</span>
            <select
              id="loc-select"
              data-testid="location-select"
              value={selectedId ?? ""}
              onChange={(e) => onSelect(Number(e.target.value))}
            >
              {districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.district ?? d.name}, {d.state})
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="scope-pill-wrap">
          <span className="scope-pill" data-testid="geographic-scope-pill" title="Predictions use approximate district-headquarter coordinates. Block and village level measurements are not yet in the pipeline.">
            <span className="scope-icon"><FiMapPin aria-hidden="true" /></span>
            <strong>Scope:</strong> Pilot location — district-HQ coordinate
          </span>
          <button
            type="button"
            className="hierarchy-toggle-btn"
            onClick={() => setShowHierarchy(!showHierarchy)}
            aria-expanded={showHierarchy}
            data-testid="toggle-hierarchy-btn"
          >
            {showHierarchy ? (
              <>
                Hide Hierarchy <FiChevronUp aria-hidden="true" style={{ verticalAlign: "-2px" }} />
              </>
            ) : (
              <>
                View Hierarchy <FiChevronDown aria-hidden="true" style={{ verticalAlign: "-2px" }} />
              </>
            )}
          </button>
        </div>
      </div>

      {showHierarchy && (
        <div className="hierarchy-breakdown" data-testid="hierarchy-breakdown">
          <div className="hierarchy-step active">
            <span className="step-level">1. State</span>
            <span className="step-val">{selectedDistrict?.state ?? "Maharashtra"}</span>
            <span className="step-status available">
              <FiCheck aria-hidden="true" style={{ marginRight: "4px" }} />Covered
            </span>
          </div>
          <div className="hierarchy-arrow">→</div>
          <div className="hierarchy-step active">
            <span className="step-level">2. District</span>
            <span className="step-val">{selectedDistrict?.name ?? "District HQ"}</span>
            <span className="step-status available">
              <FiCheck aria-hidden="true" style={{ marginRight: "4px" }} />Pilot data available
            </span>
          </div>
          <div className="hierarchy-arrow">→</div>
          <div className="hierarchy-step disabled">
            <span className="step-level">3. Block / Taluka</span>
            <span className="step-val">Sub-district</span>
            <span className="step-status unavailable" data-testid="block-unavailable-note">
              <FiAlertTriangle aria-hidden="true" style={{ marginRight: "4px" }} />Data not available for this level yet
            </span>
          </div>
          <div className="hierarchy-arrow">→</div>
          <div className="hierarchy-step disabled">
            <span className="step-level">4. Panchayat / Village</span>
            <span className="step-val">Local unit</span>
            <span className="step-status unavailable" data-testid="panchayat-unavailable-note">
              <FiAlertTriangle aria-hidden="true" style={{ marginRight: "4px" }} />Data not available for this level yet
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
