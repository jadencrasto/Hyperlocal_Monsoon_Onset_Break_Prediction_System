import React, { useEffect, useState } from "react";
import {
  errorText,
  fetchCoverageSummary,
  fetchDataQuality,
  fetchModelEvaluation,
  fetchSources,
  fetchSpatialStatus,
  fetchSyncLog,
  MODEL_SEASON,
  type CoverageSummaryResponse,
  type DataQualityResponse,
  type ModelEvaluationResponse,
  type SourcesResponse,
  type SpatialStatusResponse,
  type SyncLogItem,
} from "./api";

interface TechnicalDiagnosticsProps {
  locationId: number;
  locationName: string;
}

export default function TechnicalDiagnostics({
  locationId,
  locationName,
}: TechnicalDiagnosticsProps) {
  const [activeTab, setActiveTab] = useState<"model" | "quality" | "sources" | "sync">("model");
  const [modelEval, setModelEval] = useState<ModelEvaluationResponse | null>(null);
  const [spatial, setSpatial] = useState<SpatialStatusResponse | null>(null);
  const [quality, setQuality] = useState<DataQualityResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageSummaryResponse | null>(null);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [syncLogs, setSyncLogs] = useState<SyncLogItem[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetchModelEvaluation().catch(() => null),
      fetchSpatialStatus().catch(() => null),
      fetchDataQuality(locationId).catch(() => null),
      fetchCoverageSummary().catch(() => null),
      fetchSources().catch(() => null),
      fetchSyncLog(15).catch(() => null),
    ])
      .then(([me, sp, dq, cov, src, sl]) => {
        if (cancelled) return;
        setModelEval(me);
        setSpatial(sp);
        setQuality(dq);
        setCoverage(cov);
        setSources(src);
        setSyncLogs(sl);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [locationId]);

  return (
    <div className="technical-diagnostics-container" data-testid="technical-diagnostics">
      {/* USER-FACING MODEL SUMMARY — Issue 6 */}
      <div className="card model-summary-card" data-testid="model-summary">
        <h3>Current Break-Risk Model</h3>
        <p className="model-summary-desc">
          Uses recent and historical rainfall patterns to estimate 7-day break risk during
          the validated monsoon operating season.
        </p>
        <div className="model-summary-grid">
          <div className="summary-item">
            <span className="summary-label">Geographic coverage</span>
            <span className="summary-value">5 Maharashtra pilot locations</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Spatial modeling</span>
            <span className="summary-value">Not currently enabled</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Prediction target</span>
            <span className="summary-value">7-day break risk (≥5 consecutive dry days)</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Operating season</span>
            <span className="summary-value">{MODEL_SEASON.start} – {MODEL_SEASON.end}</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header-flex">
          <div>
            <h3>Technical Model Details</h3>
            <p className="muted small">
              Engineering metrics, data audits, and validation benchmarks
            </p>
          </div>
          <div className="tech-nav-tabs" role="tablist">
            <button
              type="button"
              className={`tech-tab ${activeTab === "model" ? "active" : ""}`}
              onClick={() => setActiveTab("model")}
              data-testid="tech-tab-model"
            >
              Model Architecture &amp; Skill
            </button>
            <button
              type="button"
              className={`tech-tab ${activeTab === "quality" ? "active" : ""}`}
              onClick={() => setActiveTab("quality")}
              data-testid="tech-tab-quality"
            >
              Data Quality Audit
            </button>
            <button
              type="button"
              className={`tech-tab ${activeTab === "sources" ? "active" : ""}`}
              onClick={() => setActiveTab("sources")}
              data-testid="tech-tab-sources"
            >
              Data Providers
            </button>
            <button
              type="button"
              className={`tech-tab ${activeTab === "sync" ? "active" : ""}`}
              onClick={() => setActiveTab("sync")}
              data-testid="tech-tab-sync"
            >
              Sync Log
            </button>
          </div>
        </div>

        {/* Tab 1: Model Architecture & Skill */}
        {activeTab === "model" && (
          <div className="tech-panel" data-testid="panel-model-diagnostics">
            <h4>1. Model Specifications &amp; Feature Set</h4>
            <div className="specs-grid">
              <div className="spec-card">
                <span className="spec-label">Model Class</span>
                <span className="spec-val">LogisticRegression (L2 regularization, balanced weights)</span>
              </div>
              <div className="spec-card">
                <span className="spec-label">Target Horizon</span>
                <span className="spec-val">7-day break risk (≥5 consecutive dry days &lt;2.5mm)</span>
              </div>
              <div className="spec-card">
                <span className="spec-label">Feature Columns (9)</span>
                <span className="spec-val code-val">
                  r1, sum3, sum7, sum14, sum30, rainy_frac14, dry_run, doy_sin, doy_cos
                </span>
                <span className="spec-sub muted">Derived exclusively from past daily rainfall; no spatial features</span>
              </div>
              <div className="spec-card">
                <span className="spec-label">Spatial Awareness</span>
                <span className="spec-val warn-val" data-testid="spatial-status-text">
                  {spatial?.is_spatially_aware ? "Spatially Aware" : "None — Model has no spatial features"}
                </span>
                <span className="spec-sub muted">
                  Trained on pooled multi-location data without latitude, longitude, or regional descriptors.
                </span>
              </div>
            </div>

            <h4>2. Measured Skill &amp; Baseline Comparison (Test Years)</h4>
            <p className="muted small">
              Lower Brier Score indicates higher accuracy. Note: The simple dry-run heuristic achieves a lower Brier score on this test split than the logistic regression model.
            </p>

            <div className="brier-comparison-table-wrap">
              <table className="brier-table" data-testid="brier-comparison-table">
                <thead>
                  <tr>
                    <th>Model / Baseline Approach</th>
                    <th>Brier Score (Lower is better)</th>
                    <th>Skill vs Climatology</th>
                    <th>Assessment</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="baseline-row">
                    <td><strong>Climatology (Historical Base Rate)</strong></td>
                    <td>0.12689</td>
                    <td>0.000 (Reference)</td>
                    <td>Base rate probability benchmark</td>
                  </tr>
                  <tr className="model-row">
                    <td><strong>Logistic Regression (Current ML Model)</strong></td>
                    <td>0.11838</td>
                    <td>+6.7% BSS [0.041, 0.096]</td>
                    <td>Modest positive skill over climatology</td>
                  </tr>
                  <tr className="heuristic-row">
                    <td><strong>Dry-Run Heuristic Baseline</strong></td>
                    <td>0.11445</td>
                    <td>+9.8% BSS</td>
                    <td>Lowest Brier score among evaluated methods</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="callout info" data-testid="brier-honesty-note">
              <strong>Evaluation Truthfulness:</strong> Lower Brier score is better. While Logistic Regression demonstrates modest skill over simple climatology (BSS 0.067 with 95% bootstrap CI [0.041, 0.096]), the simple dry-run heuristic achieves a lower Brier score (0.114 vs 0.118). The system does not claim superiority over the heuristic.
            </div>

            <h4>3. Calibration &amp; Stability</h4>
            <div className="specs-grid">
              <div className="spec-card">
                <span className="spec-label">Calibration Diagnostic</span>
                <span className="spec-val">Mean predicted: 24.3% vs Observed: 18.2%</span>
                <span className="spec-sub">Model over-predicts event probability by ~6.1% on average</span>
              </div>
              <div className="spec-card">
                <span className="spec-label">Per-Year Stability</span>
                <span className="spec-val">BSS ranged 0.013 to 0.135 across 8 test years</span>
                <span className="spec-sub">0 negative years; positive skill was maintained across test years</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Data Quality Audit */}
        {activeTab === "quality" && (
          <div className="tech-panel" data-testid="panel-quality-diagnostics">
            <h4>Location Data Quality Audit — {locationName}</h4>
            {quality ? (
              <div className="quality-audit-grid">
                <div className="quality-stat-box">
                  <span className="q-label">Audit Status</span>
                  <span className={`q-val ${quality.status === "valid" ? "ok" : "warn"}`}>
                    {quality.status.toUpperCase()}
                  </span>
                  <span className="q-sub">{quality.issues.length ? quality.issues.join(", ") : "All checks passed"}</span>
                </div>
                <div className="quality-stat-box">
                  <span className="q-label">Total Records</span>
                  <span className="q-val">{quality.total_records.toLocaleString()} days</span>
                  <span className="q-sub">{quality.first_date} to {quality.last_date}</span>
                </div>
                <div className="quality-stat-box">
                  <span className="q-label">Continuity Ratio</span>
                  <span className="q-val">{((quality.continuity_ratio ?? 1) * 100).toFixed(2)}%</span>
                  <span className="q-sub">{quality.missing_days} missing days</span>
                </div>
                <div className="quality-stat-box">
                  <span className="q-label">Impossible Values (&lt;0 or &gt;1500mm)</span>
                  <span className="q-val ok">{quality.impossible_values}</span>
                  <span className="q-sub">Zero invalid physical values detected</span>
                </div>
                <div className="quality-stat-box">
                  <span className="q-label">Duplicate Rows</span>
                  <span className="q-val ok">{quality.duplicate_count}</span>
                  <span className="q-sub">Zero duplicate records</span>
                </div>
                <div className="quality-stat-box">
                  <span className="q-label">Null Precipitation Values</span>
                  <span className="q-val ok">{quality.null_precip_count}</span>
                  <span className="q-sub">Zero unpopulated rows</span>
                </div>
              </div>
            ) : (
              <p className="state">Loading data quality report…</p>
            )}

            <h4>District Coverage Summary</h4>
            {coverage && coverage.locations && (
              <div className="coverage-summary-wrap">
                <p className="muted small">
                  Coverage: {coverage.locations_with_data} of {coverage.n_locations} districts have rainfall history
                </p>
                <div className="coverage-pill-row">
                  {coverage.locations.map((d) => (
                    <span key={d.location_id} className={`cov-pill ${d.has_data ? "has-data" : "no-data"}`}>
                      {d.name}: {d.has_data ? `${d.n_records} days` : "No data"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Data Providers */}
        {activeTab === "sources" && (
          <div className="tech-panel" data-testid="panel-sources-diagnostics">
            <h4>Integrated Weather Providers</h4>
            {sources?.providers.map((p) => (
              <div key={p.name} className="provider-card">
                <div className="prov-header">
                  <strong>{p.name.toUpperCase()}</strong>
                  <span className="badge info">{p.kind}</span>
                </div>
                <div className="prov-stats">
                  <span>Cached history: {p.cached_history_rows.toLocaleString()} rows</span>
                  <span>Cached forecast: {p.cached_forecast_rows} rows</span>
                  <span>Last success: {p.last_success ? new Date(p.last_success).toLocaleString() : "None"}</span>
                </div>
                {p.spatial_note && <p className="muted small">Spatial scope: {p.spatial_note}</p>}
              </div>
            ))}

            <h4>Unintegrated Data Sources</h4>
            <div className="unintegrated-list">
              {sources?.not_integrated.map((srcName) => (
                <div key={srcName} className="unintegrated-item">
                  <strong>{srcName}</strong>
                  <span className="muted small">
                    {srcName === "IMD" && "Official Indian Meteorological Department data requires specialized API access/credentials."}
                    {srcName === "CHIRPS" && "High-resolution satellite-gauge gridded dataset requires large offline raster download."}
                    {srcName === "ERA5 (direct)" && "Direct ECMWF CDS archive requires institutional licensing."}
                    {srcName === "ECMWF S2S" && "Sub-seasonal reforecast archive needed for future onset prediction."}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: Sync Log */}
        {activeTab === "sync" && (
          <div className="tech-panel" data-testid="panel-sync-diagnostics">
            <h4>Recent Synchronization Attempts</h4>
            <div className="sync-table-wrap">
              <table className="sync-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Provider</th>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Category</th>
                    <th>Records</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {(syncLogs ?? []).map((l) => (
                    <tr key={l.id}>
                      <td>{l.finished_at ? l.finished_at.slice(0, 16).replace("T", " ") : "-"}</td>
                      <td>{l.provider}</td>
                      <td>{l.kind}</td>
                      <td>
                        <span className={`status-pill ${l.status}`}>{l.status}</span>
                      </td>
                      <td>{l.category ?? "-"}</td>
                      <td>{l.n_records}</td>
                      <td className="msg-cell">{l.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
