import React, { useEffect, useState } from "react";
import { FiAlertTriangle, FiX } from "react-icons/fi";
import {
  errorText,
  fetchForecast,
  fetchForecastStatus,
  type ForecastResponse,
  type ForecastStatusResponse,
} from "./api";

interface ForecastSectionProps {
  locationId: number;
  locationName: string;
}

/** Forecast availability states — distinct from system ONLINE/OFFLINE. */
type ForecastState =
  | "loading"
  | "available"
  | "stale"
  | "not_loaded"
  | "failed"
  | "unavailable";

function deriveForecastState(
  forecast: ForecastResponse | null,
  status: ForecastStatusResponse | null,
  fetchFailed: boolean,
): ForecastState {
  if (fetchFailed) return "failed";
  if (!forecast && !status) return "not_loaded";
  if (forecast && forecast.records.length > 0) {
    return forecast.freshness === "stale" ? "stale" : "available";
  }
  if (status && !status.forecast_available) return "unavailable";
  return "not_loaded";
}

export default function ForecastSection({ locationId, locationName }: ForecastSectionProps) {
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [status, setStatus] = useState<ForecastStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setForecast(null);
    setStatus(null);
    setFetchFailed(false);

    Promise.all([
      fetchForecast(locationId).catch((e) => {
        if (!cancelled) setFetchFailed(true);
        return null;
      }),
      fetchForecastStatus(locationId).catch(() => null),
    ])
      .then(([fc, st]) => {
        if (cancelled) return;
        // ISSUE 5: Validate forecast response matches selected location
        if (fc && fc.location_id !== locationId) {
          // Discard mismatched forecast response
          setForecast(null);
          setFetchFailed(true);
          setError(`Forecast response location (${fc.location_id}) does not match selected location (${locationId}).`);
        } else {
          setForecast(fc);
        }
        if (st && st.location_id !== locationId) {
          setStatus(null);
        } else {
          setStatus(st);
        }
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
  }, [locationId]);

  if (loading) {
    return (
      <div className="card" data-testid="forecast-loading">
        <span className="loading-line">
          <span className="spinner" /> Loading forecast data for {locationName}…
        </span>
      </div>
    );
  }

  const forecastState = deriveForecastState(forecast, status, fetchFailed && !forecast);

  const maxPrecip = forecast?.records.length
    ? Math.max(5, ...forecast.records.map((r) => r.precip_mm))
    : 10;

  return (
    <div className="forecast-section" data-testid="forecast-section">
      <div className="card">
        <div className="card-header-flex">
          <div>
            <h3>7-Day Weather Forecast</h3>
            <p className="muted small">
              Upcoming rainfall forecast for <strong data-testid="forecast-location-name">{locationName}</strong>
            </p>
          </div>
          {forecast && (
            <div className="forecast-freshness-badges">
              <span className={`badge ${forecast.freshness === "fresh" ? "success" : "warning"}`} data-testid="forecast-freshness-badge">
                {forecast.freshness === "fresh" ? "Fresh forecast" : "Stale cached forecast"}
              </span>
              <span className="badge muted-badge">Provider: {forecast.provider}</span>
            </div>
          )}
        </div>

        {/* CRITICAL TRUTHFULNESS NOTICE: Forecast vs Model Prediction Distinction */}
        <div className="forecast-distinction-banner" data-testid="forecast-model-distinction">
          <div className="distinction-header">
            <span className="distinction-tag weather">WEATHER FORECAST</span>
            <span className="distinction-vs">≠</span>
            <span className="distinction-tag ml">MODEL PREDICTION</span>
          </div>
          <p className="distinction-text">
            <strong>Important distinction:</strong> Forecast currently informs the weather view; it is{" "}
            <strong>not yet an input to the break-risk model</strong>. The break-risk ML model uses
            only historical rainfall patterns.
          </p>
        </div>

        {/* Forecast state rendering */}
        {forecastState === "available" || forecastState === "stale" ? (
          <div className="forecast-content" data-testid="forecast-content">
            {forecastState === "stale" && (
              <div className="forecast-stale-notice" data-testid="forecast-stale-notice">
                <span className="badge warning">
                  <FiAlertTriangle aria-hidden="true" style={{ marginRight: "4px" }} />
                  Stale forecast
                </span>
                <span className="muted small">
                  This forecast data is older than the freshness threshold. Values may not reflect current conditions.
                </span>
              </div>
            )}
            <div className="forecast-days-grid">
              {forecast!.records.map((r) => {
                const dayName = new Date(r.date).toLocaleDateString("en-US", { weekday: "short" });
                const isRainy = r.precip_mm >= 2.5;
                return (
                  <div key={r.date} className={`forecast-day-card ${isRainy ? "rainy" : "dry"}`}>
                    <span className="day-name">{dayName}</span>
                    <span className="day-date">{r.date.slice(5)}</span>
                    <div className="forecast-bar-wrap">
                      <div
                        className={`forecast-bar ${isRainy ? "wet" : "dry"}`}
                        style={{ height: `${Math.max(6, (r.precip_mm / maxPrecip) * 100)}%` }}
                      />
                    </div>
                    <span className="precip-val">{r.precip_mm.toFixed(1)} <small>mm</small></span>
                    <span className="condition-label">{isRainy ? "Rain" : "Dry / Light"}</span>
                  </div>
                );
              })}
            </div>

            <div className="forecast-meta-row">
              <span className="meta-item">
                <strong>Retrieved:</strong> {forecast!.retrieved_at ? new Date(forecast!.retrieved_at).toLocaleString() : "Cached"}
              </span>
              <span className="meta-item">
                <strong>Age:</strong> {forecast!.age_hours} hours old (threshold: {forecast!.stale_after_hours}h)
              </span>
              {forecast!.spatial_note && (
                <span className="meta-item muted">
                  <strong>Spatial note:</strong> {forecast!.spatial_note}
                </span>
              )}
            </div>
          </div>
        ) : forecastState === "failed" ? (
          <div className="state forecast-state-notice" data-testid="forecast-failed">
            <strong>Forecast unavailable</strong>
            <p className="muted small">{error ?? "Could not retrieve forecast data from the provider."}</p>
          </div>
        ) : forecastState === "not_loaded" ? (
          <div className="state forecast-state-notice" data-testid="forecast-not-loaded">
            <strong>Forecast not loaded yet</strong>
            <p className="muted small">
              No forecast records have been retrieved for {locationName}. A weather forecast refresh will be attempted when data is available from the provider.
            </p>
          </div>
        ) : (
          <div className="state forecast-state-notice" data-testid="forecast-unavailable">
            <strong>Forecast unavailable</strong>
            <p className="muted small">
              {status?.freshness?.message ?? `Weather forecast data is not currently available for ${locationName}.`}
            </p>
          </div>
        )}

        {/* Integration Status Panel */}
        {status && (
          <div className="card nested-card forecast-integration-status" data-testid="forecast-integration-panel">
            <h4>Prediction Integration Status</h4>
            <div className="integration-state-row">
              <span className="integration-label">ML Integration:</span>
              <span className="integration-value false" data-testid="forecast-integration-status">
                <FiX aria-hidden="true" style={{ marginRight: "4px" }} />
                Not Integrated
              </span>
            </div>
            <p className="integration-reason muted small">
              {status.prediction_integration.reason}
            </p>
            <div className="requirements-box">
              <span className="req-title">Requirements for integration:</span>
              <ul>
                {status.prediction_integration.required_for_integration.map((req, i) => (
                  <li key={i}>{req}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
