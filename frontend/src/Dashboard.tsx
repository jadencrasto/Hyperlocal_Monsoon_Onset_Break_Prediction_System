import { useEffect, useState } from "react";
import { errorText, fetchPrediction, type Prediction } from "./api";

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

function ErrorPanel({ error }: { error: string }) {
  const unavailable = /no_stored_history|model_unavailable|insufficient_or_gappy_history|out_of_season|future_date/.test(
    error
  );
  return (
    <div className="card error" data-testid="dash-error" role="alert">
      <strong>{unavailable ? "Prediction unavailable for this location." : "Dashboard error."}</strong>
      <span>{error}</span>
      <span className="muted small">
        Other locations remain available on the map and in the location selector.
      </span>
    </div>
  );
}

export default function Dashboard({
  locationId,
  locationName,
}: {
  locationId: number;
  locationName: string;
}) {
  const [pred, setPred] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPred(null);
    fetchPrediction(locationId)
      .then((p) => {
        if (!cancelled) setPred(p);
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
      <div className="card" data-testid="dash-loading">
        Loading prediction for {locationName}…
      </div>
    );
  }
  if (error || !pred) return <ErrorPanel error={error ?? "unknown error"} />;

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

  return (
    <div data-testid="dashboard">
      {/* ---- main prediction summary ---- */}
      <div className="card dash-summary" data-testid="dash-summary">
        <div className="summary-head">
          <h3>
            {pred.location.name}
            <span className="muted small"> · {pred.location.state}</span>
          </h3>
          <span className="badge" style={{ background: color }} data-testid="risk-category">
            {pred.risk_category}
          </span>
        </div>
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
          <dt>Model</dt>
          <dd>
            {pred.model.name} · trained through {pred.model.trained_through ?? "n/a"}
          </dd>
          <dt>Evidence level</dt>
          <dd data-testid="evidence-level">{u.evidence_level ?? "n/a"}</dd>
        </dl>
        <p className="muted small bands-note" data-testid="risk-bands-note">
          Risk bands {pred.risk_bands?.low ? `(${pred.risk_bands.low} low, ${pred.risk_bands.moderate} moderate, ${pred.risk_bands.high} high)` : ""}{" "}
          are presentation bands only — {pred.risk_bands?.note ?? "not calibrated decision thresholds"}.
        </p>
      </div>

      {/* ---- evidence / uncertainty (population-level) ---- */}
      <div className="card" data-testid="dash-uncertainty">
        <h4>Evidence &amp; uncertainty</h4>
        <p className="muted small">
          These are <strong>population-level evaluation results over historical test years</strong>.
          They describe how the model performed overall — they are{" "}
          <strong>not an uncertainty interval around this individual prediction</strong>
          {ipi?.available ? "" : ", which is not available (see below)"}.
        </p>
        <dl className="summary-grid">
          <dt>Evaluation BSS vs climatology</dt>
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
              : `Not available — the pipeline fits a point-probability model only; no statistically justified per-prediction interval exists.`}
          </dd>
        </dl>
      </div>

      {/* ---- data quality panel (with Step 23 cache/offline indicators) ---- */}
      <div className="card" data-testid="dash-data-quality">
        <h4>Data quality</h4>
        {/* Step 23: factual data-situation line — never claims live weather; the model reads
            the local rainfall store, so the wording stays "cached" even when online. */}
        <p className="muted small" data-testid="cache-indicator">
          {ds.cache_status === "offline" ? (
            <strong data-testid="offline-indicator">Offline mode</strong>
          ) : (
            <strong data-testid="cached-indicator">Cached rainfall data</strong>
          )}{" — "}
          {ds.cache_status === "offline" ? "using locally stored data" : "from the local rainfall store"}{" · "}
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
            ⚠ {ds.freshness === "stale" && `Rainfall data is ${ds.data_age_days} days old. `}
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
      </div>

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
    </div>
  );
}
