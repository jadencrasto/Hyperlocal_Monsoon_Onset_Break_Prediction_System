import { useEffect, useState } from "react";
import { FiAlertTriangle, FiCalendar, FiCheck } from "react-icons/fi";
import {
  extractPredictionError,
  fetchPrediction,
  MODEL_SEASON,
  type Prediction,
  type PredictionErrorKind,
} from "./api";
import DataStatusBadge from "./DataStatusBadge";

/** Step 17 prediction dashboard for one location. Pure function of `locationId`:
 * fetches the Step 14 prediction and renders the summary, evidence/uncertainty, and
 * data-quality panels. All values come verbatim from the API; nothing is invented.
 * Evidence/uncertainty shown here is POPULATION-LEVEL (evaluation over test years);
 * the individual-prediction interval is explicitly declared unavailable by the API. */

interface Uncertainty {
  individual_prediction_interval?: { available: boolean; reason?: string };
  evaluation_skill?: {
    brier_skill_vs_climatology?: number | null;
    brier_skill_ci?: { low?: number; high?: number } | null;
    ci_interpretation?: string;
    n_test_years?: number | null;
  };
  calibration?: {
    mean_predicted?: number | null;
    observed_rate?: number | null;
    mean_diff?: number | null;
    interpretation?: string | null;
    note?: string | null;
  };
  per_year_stability?: {
    n_years?: number | null;
    bss_min?: number | null;
    bss_max?: number | null;
    negative_years?: number | null;
    note?: string | null;
  };
  evidence_level?: string;
  data_caveats?: { freshness?: string; data_age_days?: number; note?: string };
}

const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "n/a" : `${(v * 100).toFixed(digits)}%`;

/** Off-season informational card — NOT an error. */
function OffSeasonPanel() {
  return (
    <div className="card off-season-card" data-testid="dash-off-season" role="status">
      <div className="off-season-header">
        <span className="off-season-icon"><FiCalendar aria-hidden="true" /></span>
        <div>
          <strong>Break-risk prediction unavailable — off-season</strong>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            Model operating season: {MODEL_SEASON.start} – {MODEL_SEASON.end}
          </p>
        </div>
      </div>
      <p className="muted small" style={{ margin: "8px 0 0" }}>
        Predictions are intentionally disabled outside the validated monsoon-season window.
        Rainfall history, forecasts, and other views remain available.
      </p>
    </div>
  );
}

function ErrorPanel({ errorKind, errorLabel, errorHint, errorRaw }: {
  errorKind: PredictionErrorKind;
  errorLabel: string;
  errorHint: string | null;
  errorRaw: string;
}) {
  const isTooOld = errorKind === "cached_data_too_old";
  return (
    <div className="card error" data-testid="dash-error" role="alert">
      {isTooOld && <DataStatusBadge error={errorRaw} />}
      <strong>{errorLabel}</strong>
      {errorHint && <span className="muted small">{errorHint}</span>}
      <details className="muted small" style={{ marginTop: 4 }}>
        <summary>Technical details</summary>
        <span>{errorRaw}</span>
      </details>
      <span className="muted small">
        Other locations remain available on the map and in the location selector.
      </span>
    </div>
  );
}

function ModeSelectorBar({
  isDemoMode,
  onToggleDemoMode,
  demoDate,
  onDemoDateChange,
}: {
  isDemoMode: boolean;
  onToggleDemoMode?: (enabled: boolean) => void;
  demoDate: string;
  onDemoDateChange?: (date: string) => void;
}) {
  return (
    <div className="card mode-selector-card" data-testid="prediction-mode-selector" style={{ marginBottom: 16, padding: "10px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Prediction Mode:</span>
          <div className="tabs" style={{ margin: 0, display: "inline-flex" }}>
            <button
              type="button"
              className={!isDemoMode ? "on" : ""}
              onClick={() => onToggleDemoMode?.(false)}
              data-testid="mode-current-btn"
              style={{ padding: "4px 12px", fontSize: "0.85rem" }}
            >
              Current Date
            </button>
            <button
              type="button"
              className={isDemoMode ? "on" : ""}
              onClick={() => onToggleDemoMode?.(true)}
              data-testid="mode-demo-btn"
              style={{ padding: "4px 12px", fontSize: "0.85rem" }}
            >
              Historical Demo
            </button>
          </div>
        </div>
        {isDemoMode && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <label htmlFor="demo-date-select" style={{ fontSize: "0.85rem", fontWeight: 500 }}>
              Demo Reference Date:
            </label>
            <select
              id="demo-date-select"
              data-testid="demo-date-select"
              value={demoDate}
              onChange={(e) => onDemoDateChange?.(e.target.value)}
              style={{ padding: "4px 8px", borderRadius: 4, fontSize: "0.85rem" }}
            >
              <option value="2026-09-25">25 Sep 2026 (In-Season)</option>
              <option value="2026-09-20">20 Sep 2026 (In-Season)</option>
              <option value="2026-09-15">15 Sep 2026 (In-Season)</option>
              <option value="2026-10-05">05 Oct 2026 (Out-of-Season Test)</option>
            </select>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Dashboard({
  locationId,
  locationName,
  isDemoMode: propIsDemoMode,
  onToggleDemoMode,
  demoDate: propDemoDate,
  onDemoDateChange,
}: {
  locationId: number;
  locationName: string;
  isDemoMode?: boolean;
  onToggleDemoMode?: (enabled: boolean) => void;
  demoDate?: string;
  onDemoDateChange?: (date: string) => void;
}) {
  const [internalIsDemoMode, setInternalIsDemoMode] = useState<boolean>(false);
  const [internalDemoDate, setInternalDemoDate] = useState<string>("2026-09-25");

  const isDemoMode = propIsDemoMode !== undefined ? propIsDemoMode : internalIsDemoMode;
  const demoDate = propDemoDate !== undefined ? propDemoDate : internalDemoDate;

  const handleToggleDemoMode = (enabled: boolean) => {
    if (onToggleDemoMode) {
      onToggleDemoMode(enabled);
    } else {
      setInternalIsDemoMode(enabled);
    }
  };

  const handleDemoDateChange = (date: string) => {
    if (onDemoDateChange) {
      onDemoDateChange(date);
    } else {
      setInternalDemoDate(date);
    }
  };

  const [pred, setPred] = useState<Prediction | null>(null);
  const [predError, setPredError] = useState<{
    kind: PredictionErrorKind;
    label: string;
    hint: string | null;
    raw: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPredError(null);
    setPred(null);
    const asOf = isDemoMode ? demoDate : undefined;
    fetchPrediction(locationId, asOf)
      .then((p) => {
        if (!cancelled) setPred(p);
      })
      .catch((e) => {
        if (!cancelled) setPredError(extractPredictionError(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [locationId, isDemoMode, demoDate]);

  if (loading) {
    return (
      <div data-testid="dashboard" className="dashboard-content-wrap">
        <ModeSelectorBar
          isDemoMode={isDemoMode}
          onToggleDemoMode={handleToggleDemoMode}
          demoDate={demoDate}
          onDemoDateChange={handleDemoDateChange}
        />
        <div className="card" data-testid="dash-loading">
          <span className="loading-line">
            <span className="spinner" /> Loading prediction for {locationName}…
          </span>
        </div>
      </div>
    );
  }
  if (predError) {
    return (
      <div data-testid="dashboard" className="dashboard-content-wrap">
        <ModeSelectorBar
          isDemoMode={isDemoMode}
          onToggleDemoMode={handleToggleDemoMode}
          demoDate={demoDate}
          onDemoDateChange={handleDemoDateChange}
        />
        {predError.kind === "out_of_season" ? (
          <OffSeasonPanel />
        ) : (
          <ErrorPanel
            errorKind={predError.kind}
            errorLabel={predError.label}
            errorHint={predError.hint}
            errorRaw={predError.raw}
          />
        )}
      </div>
    );
  }
  if (!pred) {
    return (
      <div data-testid="dashboard" className="dashboard-content-wrap">
        <ModeSelectorBar
          isDemoMode={isDemoMode}
          onToggleDemoMode={handleToggleDemoMode}
          demoDate={demoDate}
          onDemoDateChange={handleDemoDateChange}
        />
        <ErrorPanel errorKind="unknown" errorLabel="Prediction unavailable." errorHint={null} errorRaw="unknown error" />
      </div>
    );
  }

  const u: Uncertainty = (pred.uncertainty ?? {}) as Uncertainty;
  const ev = u.evaluation_skill ?? {};
  const cal = u.calibration ?? {};
  const stab = u.per_year_stability ?? {};
  const ipi = u.individual_prediction_interval;
  const ds = pred.data_status;
  const color = pred.risk_category === "low" ? "#2e7d32" : pred.risk_category === "moderate" ? "#f9a825" : "#c62828";
  // Step 25: most recent failed refresh for this location (any kind) — shown as a factual
  // "online failed, cached data in use" line. Absent/old failures render nothing.
  const lastFailure = pred.last_sync_failure ?? null;

  // Human-readable framing of the SAME API numbers (population-level evaluation).
  const bss = ev.brier_skill_vs_climatology;
  const evidenceSummary =
    bss == null
      ? "No historical evaluation is available for this model yet."
      : bss > 0
        ? "On evaluated historical test years, the model performed modestly better than a simple historical-average (climatology) baseline."
        : "On evaluated historical test years, the model did not perform better than a simple historical-average (climatology) baseline.";

  const isDemo = isDemoMode || pred.evaluation_mode === "historical_demo";

  return (
    <div data-testid="dashboard" className="dashboard-content-wrap">
      <ModeSelectorBar
        isDemoMode={isDemoMode}
        onToggleDemoMode={handleToggleDemoMode}
        demoDate={demoDate}
        onDemoDateChange={handleDemoDateChange}
      />

      {isDemo && (
        <div
          className="card demo-mode-indicator"
          data-testid="historical-demo-banner"
          style={{
            background: "#fef3c7",
            border: "1px solid #f59e0b",
            padding: "12px 16px",
            marginBottom: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="badge" style={{ background: "#d97706", color: "#fff", fontWeight: "bold" }}>
              HISTORICAL DEMO
            </span>
            <strong style={{ color: "#92400e" }}>In-Season Evaluation Mode</strong>
          </div>
          <p className="muted small" style={{ margin: "4px 0 0", color: "#78350f" }}>
            Prediction reference date: <strong>{pred.prediction_date}</strong>. Evaluating existing ML model using historical rainfall data up to this reference date.
          </p>
        </div>
      )}

      {/* ---- 10-Second Executive Decision Briefing ---- */}
      <section className="card executive-briefing-card" data-testid="executive-briefing">
        <div className="briefing-header">
          <div className="briefing-badge-row">
            <span className="executive-badge">
              {isDemo ? `Historical In-Season Briefing · ${pred.prediction_date}` : "Executive Monsoon Briefing"}
            </span>
            <span className="scope-tag" data-testid="briefing-scope">Scope: District-HQ Coordinate</span>
          </div>
          <h3>
            {isDemo
              ? `Historical In-Season Demonstration for ${pred.location.name} (as of ${pred.prediction_date})`
              : `What is happening in ${pred.location.name} right now?`}
          </h3>
        </div>

        <div className="briefing-grid">
          <div className="briefing-item">
            <span className="item-label">1. Break / Dry-Spell Risk</span>
            <span className={`item-value ${pred.risk_category}`}>
              {pred.risk_category.toUpperCase()} ({pct(pred.probability)})
            </span>
            <span className="item-desc">
              Chance of ≥5 consecutive dry days within next {pred.horizon_days} days
            </span>
          </div>

          <div className="briefing-item">
            <span className="item-label">2. Observed Monsoon Onset</span>
            <span className="item-value">Retrospectively Detected</span>
            <span className="item-desc">
              Historical onset analysis available; future onset prediction is not available yet
            </span>
          </div>

          <div className="briefing-item">
            <span className="item-label">3. Data Freshness &amp; Source</span>
            <span className="item-value">
              {isDemo
                ? `HISTORICAL DEMO (${pred.prediction_date})`
                : `${ds.freshness.toUpperCase()} (${ds.data_age_days}d old)`}
            </span>
            <span className="item-desc">
              Provider: {ds.provider ?? "unknown"} (
              {isDemo ? "Historical reanalysis" : ds.cache_status === "offline" ? "Offline cache" : "Stored reanalysis"})
            </span>
          </div>

          <div className="briefing-item">
            <span className="item-label">4. Weather Forecast vs ML</span>
            <span className="item-value info">Separately Displayed</span>
            <span className="item-desc">
              Weather forecast informs the weather view; not used as input to break-risk model
            </span>
          </div>
        </div>
      </section>

      {/* ---- main prediction summary: the visual focal point ---- */}
      <section className="card dash-summary" data-testid="dash-summary">
        <div className="summary-head">
          <div>
            <h3>
              {pred.location.name}
              <span className="muted small"> · {pred.location.state}</span>
            </h3>
            <p className="muted small" style={{ margin: "2px 0 0" }}>
              Break-risk outlook for {pred.location.district ?? pred.location.name} district
            </p>
          </div>
          <span className="risk-badge" style={{ background: color }} data-testid="risk-category">
            {pred.risk_category} break-risk
          </span>
        </div>
        <DataStatusBadge pred={pred} />
        <p className="big-prob" data-testid="dash-probability">
          {pct(pred.probability)}
          <span className="muted small">
            {" "}
            chance of {pred.event} within {pred.horizon_days} days
          </span>
        </p>
        <dl className="summary-grid">
          <dt>Prediction date (model as-of)</dt>
          <dd data-testid="dash-date">{pred.prediction_date}</dd>
          <dt>Forecast horizon</dt>
          <dd data-testid="dash-horizon">{pred.horizon_days} days</dd>
          <dt>Evidence level</dt>
          <dd data-testid="evidence-level">{u.evidence_level ?? "n/a"}</dd>
        </dl>
        <p className="muted small bands-note" data-testid="risk-bands-note">
          Risk bands {pred.risk_bands?.low ? `(${pred.risk_bands.low} low, ${pred.risk_bands.moderate} moderate, ${pred.risk_bands.high} high)` : ""}{" "}
          are presentation bands only — {pred.risk_bands?.note ?? "not calibrated decision thresholds"}.
        </p>
      </section>

      {/* ---- Evidence & uncertainty (population-level) ---- */}
      <section className="card" data-testid="dash-uncertainty">
        <h4>Evidence &amp; uncertainty</h4>
        <p className="muted small" data-testid="evidence-summary">
          {evidenceSummary} The figures below are <strong>population-level evaluation results over
          historical test years</strong>. They describe how the model performed overall — they are{" "}
          <strong>not an uncertainty interval around this individual prediction</strong>
          {ipi?.available ? "" : ", which is not available (see below)"}.
        </p>
        <dl className="summary-grid">
          <dt>Historical evaluation (BSS vs climatology)</dt>
          <dd data-testid="eval-bss">{pct(ev.brier_skill_vs_climatology, 3)}</dd>
          <dt>BSS 95% CI (year-block bootstrap)</dt>
          <dd data-testid="eval-ci">
            {ev.brier_skill_ci?.low != null && ev.brier_skill_ci?.high != null
              ? `[${ev.brier_skill_ci.low.toFixed(3)}, ${ev.brier_skill_ci.high.toFixed(3)}]`
              : "n/a"}
          </dd>
          <dt>Test years</dt>
          <dd>{ev.n_test_years ?? "n/a"}</dd>
          <dt>Calibration</dt>
          <dd data-testid="calibration">
            {cal.interpretation ?? "no calibration diagnostic available"}
            {cal.mean_diff != null &&
              ` (mean predicted ${pct(cal.mean_predicted, 1)} vs observed ${pct(cal.observed_rate, 1)})`}
          </dd>
          <dt>Per-year stability</dt>
          <dd data-testid="per-year-stability">
            {stab.n_years
              ? `BSS ranged ${stab.bss_min?.toFixed(3)} to ${stab.bss_max?.toFixed(3)} across ${stab.n_years} test years (${stab.negative_years ?? 0} negative)`
              : "not available"}
          </dd>
          <dt>Individual prediction interval</dt>
          <dd data-testid="ipi">
            {ipi?.available
              ? "available"
              : "Not available — the model produces a single probability estimate only; no statistically justified interval for this individual prediction exists."}
          </dd>
        </dl>
      </section>

      {/* ---- Data quality panel (with Step 23 cache/offline indicators) ---- */}
      <section className="card" data-testid="dash-data-quality">
        <h4>Data quality</h4>
        {/* Step 23: factual data-situation line — never claims live weather; the model reads
            the local rainfall store, so the wording stays "cached" even when online. */}
        <p className="muted small" data-testid="cache-indicator">
          {ds.cache_status === "offline" ? (
            <strong data-testid="offline-indicator">Offline mode</strong>
          ) : ds.cache_status === "live" ? (
            <strong data-testid="live-indicator">Live rainfall data</strong>
          ) : (
            <strong data-testid="cached-indicator">Cached rainfall data</strong>
          )}{" — "}
          {ds.cache_status === "offline"
            ? "using locally stored data"
            : ds.cache_status === "live"
            ? "freshly retrieved live data"
            : "from the local rainfall store"}{" · "}
          <span data-testid="cache-provider">provider: {ds.provider ?? "unknown"}</span>{" · "}
          latest observation {ds.latest_rainfall_date} ({ds.data_age_days} days old)
          {ds.freshness === "stale" && (
            <strong className="warn" data-testid="stale-indicator"> · rainfall data is stale</strong>
          )}
        </p>
        {lastFailure && (
          <p className="muted small" data-testid="fallback-indicator">
            Online data unavailable ({lastFailure.category ?? "provider error"}) — using cached
            rainfall data. Last refresh attempt {lastFailure.finished_at.slice(0, 10)}.
          </p>
        )}
        {(ds.freshness === "stale" || ds.input_completeness < 1) && (
          <p className="warn" data-testid="data-warning">
            <FiAlertTriangle aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
            {ds.freshness === "stale" && `Rainfall data is ${ds.data_age_days} days old. `}
            {ds.input_completeness < 1 && "Recent rainfall has gaps. "}
            Treat this prediction with caution.
          </p>
        )}
        <dl className="summary-grid">
          <dt>Source</dt>
          <dd>{ds.source}</dd>
          <dt>Provider (latest row)</dt>
          <dd data-testid="data-provider">{ds.provider ?? "unknown"}</dd>
          <dt>Latest rainfall date (observed)</dt>
          <dd>{ds.latest_rainfall_date}</dd>
          <dt>Data age</dt>
          <dd>{ds.data_age_days} days</dd>
          <dt>Freshness</dt>
          <dd data-testid="freshness">{ds.freshness}</dd>
          <dt>Input days used</dt>
          <dd>{ds.input_days_used}</dd>
          <dt>Input completeness</dt>
          <dd data-testid="completeness">{pct(ds.input_completeness, 0)}</dd>
        </dl>
      </section>

      <details className="card muted small">
        <summary>Model caveats &amp; limitations</summary>
        <ul>
          {(pred.model.caveats ?? []).map((c, i) => (
            <li key={`c${i}`}>{c}</li>
          ))}
          {pred.limitations.map((l, i) => (
            <li key={`l${i}`}>{l}</li>
          ))}
        </ul>
      </details>

      {/* Explicit declaration of what is currently unavailable */}
      <section className="card unavailable-capabilities-card" data-testid="unavailable-capabilities-panel">
        <h4>System Capability Status (Truthful Scope)</h4>
        <div className="capabilities-grid">
          <div className="cap-item available">
            <span className="cap-icon"><FiCheck aria-hidden="true" /></span>
            <div>
              <strong>Observed Break-Risk Prediction (7-Day Horizon)</strong>
              <p className="muted small">Operational from stored historical rainfall patterns</p>
            </div>
          </div>
          <div className="cap-item available">
            <span className="cap-icon"><FiCheck aria-hidden="true" /></span>
            <div>
              <strong>Retrospective Observed Onset Detection</strong>
              <p className="muted small">Operational detection from historical rainfall series</p>
            </div>
          </div>
          <div className="cap-item available">
            <span className="cap-icon"><FiCheck aria-hidden="true" /></span>
            <div>
              <strong>Contextual Agricultural Advisory</strong>
              <p className="muted small">Rule-based crop advisory in English, Hindi, and Marathi</p>
            </div>
          </div>
          <div className="cap-item unavailable">
            <span className="cap-icon"><FiAlertTriangle aria-hidden="true" /></span>
            <div>
              <strong>Future Monsoon Onset Prediction</strong>
              <p className="muted small">Not implemented — requires forecast-driven S2S models</p>
            </div>
          </div>
          <div className="cap-item unavailable">
            <span className="cap-icon"><FiAlertTriangle aria-hidden="true" /></span>
            <div>
              <strong>Block / Village-Level Hyperlocal Resolution</strong>
              <p className="muted small">Not available — current pilot scope is district-HQ coordinates</p>
            </div>
          </div>
          <div className="cap-item unavailable">
            <span className="cap-icon"><FiAlertTriangle aria-hidden="true" /></span>
            <div>
              <strong>Spatial ML / Regional Feature Modeling</strong>
              <p className="muted small">Not implemented — current model uses non-spatial features</p>
            </div>
          </div>
          <div className="cap-item unavailable">
            <span className="cap-icon"><FiAlertTriangle aria-hidden="true" /></span>
            <div>
              <strong>Forecast → ML Prediction Integration</strong>
              <p className="muted small">Not implemented — forecast displayed separately as weather view</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
