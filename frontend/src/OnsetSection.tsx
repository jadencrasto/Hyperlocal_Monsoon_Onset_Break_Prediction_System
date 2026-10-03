import React, { useEffect, useState } from "react";
import { FiAlertTriangle, FiCheck, FiClock, FiInfo } from "react-icons/fi";
import {
  errorText,
  fetchOnset,
  fetchOnsetPrediction,
  type OnsetPredictionResponse,
  type OnsetResponse,
} from "./api";

interface OnsetSectionProps {
  locationId: number;
  locationName: string;
}

export default function OnsetSection({ locationId, locationName }: OnsetSectionProps) {
  const currentYear = new Date().getFullYear();
  // Default to 2023 or current year for historical data query
  const [year, setYear] = useState<number>(2023);
  const [observedOnset, setObservedOnset] = useState<OnsetResponse | null>(null);
  const [futurePrediction, setFuturePrediction] = useState<OnsetPredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      fetchOnset(locationId, year).catch(() => null),
      fetchOnsetPrediction(locationId).catch(() => null),
    ])
      .then(([obs, fut]) => {
        if (cancelled) return;
        setObservedOnset(obs);
        setFuturePrediction(fut);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [locationId, year]);

  return (
    <div className="onset-section" data-testid="onset-section">
      {/* Retrospective Observed Onset Panel */}
      <div className="card onset-card" data-testid="observed-onset-card">
        <div className="card-header-flex">
          <div>
            <h3>Observed Monsoon Onset (Retrospective Detection)</h3>
            <p className="muted small">
              Retrospective historical analysis of stored rainfall data for {locationName}
            </p>
          </div>
          <div className="year-selector-wrap">
            <label htmlFor="onset-year-select" className="muted small">
              Analysis Year:{" "}
              <select
                id="onset-year-select"
                data-testid="onset-year-select"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
              >
                {[2026, 2025, 2024, 2023, 2022, 2021, 2020].map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {loading ? (
          <div className="loading-line" data-testid="onset-loading">
            <span className="spinner" /> Analyzing monsoon onset for {year}…
          </div>
        ) : error ? (
          <div className="card error">
            <span>{error}</span>
          </div>
        ) : observedOnset ? (
          <div className="onset-details-grid">
            <div className="onset-stat-box">
              <span className="stat-label">Onset Detection Status</span>
              <span className={`stat-value ${observedOnset.status === "detected" ? "detected" : "not-detected"}`} data-testid="onset-status">
                {observedOnset.status === "detected" ? (
                  <>
                    <FiCheck aria-hidden="true" style={{ marginRight: "4px" }} />
                    Onset Detected
                  </>
                ) : (
                  "Onset Not Detected"
                )}
              </span>
              <span className="stat-note">Type: Retrospective analysis</span>
            </div>

            <div className="onset-stat-box">
              <span className="stat-label">Observed Historical Onset Date</span>
              <span className="stat-value highlight" data-testid="observed-onset-date">
                {observedOnset.observed_onset ?? observedOnset.onset_date ?? "Not detected in period"}
              </span>
              <span className="stat-note">Jun 1 - Jul 31 analysis window</span>
            </div>

            <div className="onset-stat-box">
              <span className="stat-label">Scientific Detection Criteria</span>
              <span className="stat-value small-text">
                IMD Local Criteria: 2 consecutive days ≥ 2.5 mm rainfall
              </span>
              <span className="stat-note">Config: min 2.5 mm/day</span>
            </div>
          </div>
        ) : (
          <div className="state">No onset data available for year {year}.</div>
        )}

        <div className="truthfulness-callout" data-testid="onset-truthfulness-note">
          <span className="callout-icon"><FiInfo aria-hidden="true" /></span>
          <span>
            <strong>Scientific Note:</strong> This is <strong>retrospective onset detection</strong> from
            historical rainfall data, identifying when monsoon rains arrived in {year}. It is <strong>NOT</strong> a future onset prediction.
          </span>
        </div>
      </div>

      {/* Future Onset Prediction (Professional Unavailable State) */}
      <div className="card onset-card prediction-status-card" data-testid="future-onset-card">
        <div className="card-header-flex">
          <div>
            <h3>Future Monsoon Onset Prediction</h3>
            <p className="muted small">Forward-looking seasonal onset timing forecast</p>
          </div>
          <span className="badge warning" data-testid="future-onset-badge">
            Not Available Yet
          </span>
        </div>

        <div className="unavailable-state-container" data-testid="future-onset-unavailable-state">
          <div className="unavailable-header">
            <span className="unavailable-icon"><FiClock aria-hidden="true" /></span>
            <div>
              <h4>Future monsoon onset prediction is not yet available.</h4>
              <p className="muted">
                A validated future-onset prediction model has not yet been deployed.
              </p>
            </div>
          </div>

          <div className="onset-availability-summary">
            <div className="availability-item available">
              <span className="avail-icon"><FiCheck aria-hidden="true" /></span>
              <div>
                <strong>Observed onset detection</strong>
                <span className="muted small"> — Retrospective analysis of historical rainfall is available above.</span>
              </div>
            </div>
            <div className="availability-item available">
              <span className="avail-icon"><FiCheck aria-hidden="true" /></span>
              <div>
                <strong>7-day weather forecast</strong>
                <span className="muted small"> — Available separately in the forecast section. This is a weather forecast, not a monsoon onset prediction.</span>
              </div>
            </div>
            <div className="availability-item unavailable">
              <span className="avail-icon"><FiAlertTriangle aria-hidden="true" /></span>
              <div>
                <strong>Future onset prediction</strong>
                <span className="muted small"> — Requires a validated predictive model trained on sub-seasonal forecast data.</span>
              </div>
            </div>
          </div>

          <details className="prerequisites-details">
            <summary>Technical prerequisites for future onset prediction</summary>
            <ul>
              <li>
                <strong>Forecast-driven model:</strong> ECMWF Sub-seasonal to Seasonal (S2S) reforecast archive
              </li>
              <li>
                <strong>Calibrated probability estimates:</strong> Quantile / ensemble probability distribution for onset dates
              </li>
              <li>
                <strong>Independent validation:</strong> Multi-year validation against historical observed onsets with skill benchmarks
              </li>
            </ul>
          </details>
        </div>
      </div>
    </div>
  );
}
