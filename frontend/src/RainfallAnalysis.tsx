import React, { useEffect, useState, useMemo } from "react";
import { FiMinus, FiTrendingDown, FiTrendingUp } from "react-icons/fi";
import { errorText, fetchHistory, type HistoryRecord } from "./api";

interface RainfallAnalysisProps {
  locationId: number;
  locationName: string;
}

export default function RainfallAnalysis({ locationId, locationName }: RainfallAnalysisProps) {
  const [records, setRecords] = useState<HistoryRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // Fetch the last 45 days up to today or a recent date window
    // For historical stability in demo, query current year's monsoon or last 60 days
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 45);

    const startStr = start.toISOString().slice(0, 10);
    const endStr = end.toISOString().slice(0, 10);

    fetchHistory(locationId, startStr, endStr)
      .then((h) => {
        if (!cancelled) setRecords(h.records);
      })
      .catch((e) => {
        // Fallback: if today's range has no data (e.g. historical database up to 2026-09-29 or earlier),
        // try fetching from Jun 15 to Sep 30 of the current year or 2026
        const fallbackYear = end.getFullYear();
        fetchHistory(locationId, `${fallbackYear}-06-15`, `${fallbackYear}-09-30`)
          .then((h2) => {
            if (!cancelled) setRecords(h2.records);
          })
          .catch((e2) => {
            if (!cancelled) setError(errorText(e2 || e));
          });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [locationId]);

  // Compute rolling sums and statistics
  const stats = useMemo(() => {
    if (!records || records.length === 0) return null;

    const validRecords = records.filter((r) => r.precip_mm != null);
    if (!validRecords.length) return null;

    const n = validRecords.length;
    const latest = validRecords[n - 1];
    const r1 = latest?.precip_mm ?? 0;

    const sumN = (days: number) => {
      const slice = validRecords.slice(-days);
      return slice.reduce((acc, cur) => acc + (cur.precip_mm ?? 0), 0);
    };

    const sum3 = sumN(3);
    const sum7 = sumN(7);
    const sum14 = sumN(14);
    const sum30 = sumN(30);

    // Calculate current dry run (consecutive days < 2.5 mm from end backwards)
    let dryRun = 0;
    for (let i = n - 1; i >= 0; i--) {
      if ((validRecords[i].precip_mm ?? 0) < 2.5) {
        dryRun++;
      } else {
        break;
      }
    }

    // Wet days in last 14 days
    const last14 = validRecords.slice(-14);
    const wetDays14 = last14.filter((r) => (r.precip_mm ?? 0) >= 2.5).length;
    const rainyFrac14 = last14.length > 0 ? wetDays14 / last14.length : 0;

    // Trend assessment
    const first7Of14 = last14.slice(0, Math.max(0, last14.length - 7));
    const last7Of14 = last14.slice(-7);
    const sumFirst7 = first7Of14.reduce((acc, c) => acc + (c.precip_mm ?? 0), 0);
    const sumLast7 = last7Of14.reduce((acc, c) => acc + (c.precip_mm ?? 0), 0);

    let trend = "stable";
    if (sumLast7 < sumFirst7 - 5) {
      trend = "decreasing";
    } else if (sumLast7 > sumFirst7 + 5) {
      trend = "increasing";
    }

    return {
      r1,
      sum3,
      sum7,
      sum14,
      sum30,
      dryRun,
      wetDays14,
      rainyFrac14,
      trend,
      latestDate: latest?.date,
      count: n,
    };
  }, [records]);

  if (loading) {
    return (
      <div className="card" data-testid="rainfall-loading">
        <span className="loading-line">
          <span className="spinner" /> Loading rainfall analysis for {locationName}…
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card error" data-testid="rainfall-error" role="alert">
        <strong>Rainfall analysis unavailable.</strong>
        <span>{error}</span>
      </div>
    );
  }

  if (!records || records.length === 0 || !stats) {
    return (
      <div className="card" data-testid="rainfall-empty">
        <h4>Rainfall Analysis — {locationName}</h4>
        <p className="state">No recent daily rainfall records found for this location.</p>
      </div>
    );
  }

  const maxVal = Math.max(5, ...records.slice(-30).map((r) => r.precip_mm ?? 0));

  return (
    <div className="rainfall-analysis-container" data-testid="rainfall-analysis">
      <div className="card">
        <div className="card-header-flex">
          <div>
            <h3>Recent Rainfall Analysis</h3>
            <p className="muted small">
              Observed daily rainfall for <strong>{locationName}</strong> up to {stats.latestDate} (unit: mm/day)
            </p>
          </div>
          <span className="badge info">Reanalysis store</span>
        </div>

        {/* Practical Questions Answers */}
        <div className="practical-qa-grid" data-testid="rainfall-insights">
          <div className="qa-card">
            <span className="qa-label">Has rainfall decreased recently?</span>
            <span className={`qa-answer ${stats.trend}`}>
              {stats.trend === "decreasing" && (
                <>
                  <FiTrendingDown aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
                  Yes, rainfall has declined compared to the prior week
                </>
              )}
              {stats.trend === "increasing" && (
                <>
                  <FiTrendingUp aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
                  No, rainfall has increased recently
                </>
              )}
              {stats.trend === "stable" && (
                <>
                  <FiMinus aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
                  Rainfall has remained relatively steady
                </>
              )}
            </span>
            <span className="qa-sub">
              7-day total: {stats.sum7.toFixed(1)} mm vs previous 7-day window
            </span>
          </div>

          <div className="qa-card">
            <span className="qa-label">How long has the dry period lasted?</span>
            <span className={`qa-answer ${stats.dryRun >= 5 ? "warn" : "normal"}`}>
              {stats.dryRun === 0
                ? "Rainfall recorded on the most recent day"
                : `${stats.dryRun} consecutive dry day${stats.dryRun === 1 ? "" : "s"} (<2.5 mm)`}
            </span>
            <span className="qa-sub">
              {stats.dryRun >= 5
                ? "Meets the scientific threshold for dry-spell run"
                : "Below the 5-day continuous break criterion"}
            </span>
          </div>

          <div className="qa-card">
            <span className="qa-label">14-Day wet day frequency</span>
            <span className="qa-answer normal">
              {stats.wetDays14} of 14 days ({(stats.rainyFrac14 * 100).toFixed(0)}%)
            </span>
            <span className="qa-sub">Days with ≥ 2.5 mm rainfall</span>
          </div>
        </div>

        {/* Feature-Aligned Metrics Grid */}
        <div className="metrics-grid">
          <div className="metric-box">
            <span className="metric-title">Latest 1-Day Rain (r1)</span>
            <span className="metric-value">{stats.r1.toFixed(1)} <small>mm</small></span>
            <span className="metric-caption">{stats.r1 >= 2.5 ? "Wet day (≥2.5mm)" : "Dry day (<2.5mm)"}</span>
          </div>
          <div className="metric-box">
            <span className="metric-title">3-Day Total (sum3)</span>
            <span className="metric-value">{stats.sum3.toFixed(1)} <small>mm</small></span>
            <span className="metric-caption">Rolling 3-day sum</span>
          </div>
          <div className="metric-box">
            <span className="metric-title">7-Day Total (sum7)</span>
            <span className="metric-value">{stats.sum7.toFixed(1)} <small>mm</small></span>
            <span className="metric-caption">Rolling weekly sum</span>
          </div>
          <div className="metric-box">
            <span className="metric-title">14-Day Total (sum14)</span>
            <span className="metric-value">{stats.sum14.toFixed(1)} <small>mm</small></span>
            <span className="metric-caption">Rolling 2-week sum</span>
          </div>
          <div className="metric-box">
            <span className="metric-title">30-Day Total (sum30)</span>
            <span className="metric-value">{stats.sum30.toFixed(1)} <small>mm</small></span>
            <span className="metric-caption">Monthly accumulated</span>
          </div>
          <div className="metric-box">
            <span className="metric-title">Current Dry Run</span>
            <span className="metric-value">{stats.dryRun} <small>days</small></span>
            <span className="metric-caption">Days with rain &lt; 2.5mm</span>
          </div>
        </div>

        {/* Recent Daily Bars */}
        <div className="recent-bars-container" data-testid="recent-rainfall-chart">
          <h4>Daily Rainfall Trend (Last 30 Days)</h4>
          <div className="rain-strip large" role="img" aria-label="Recent daily rainfall bars">
            {records.slice(-30).map((r) => {
              const v = r.precip_mm ?? 0;
              const isWet = v >= 2.5;
              return (
                <div
                  key={r.date}
                  className={`rain-bar ${isWet ? "wet" : "dry"}`}
                  style={{ height: `${Math.max(3, (v / maxVal) * 100)}%` }}
                  title={`${r.date}: ${v.toFixed(1)} mm/day (${isWet ? "Wet Day ≥2.5mm" : "Dry <2.5mm"})`}
                  data-date={r.date}
                />
              );
            })}
          </div>
          <div className="chart-legend muted small">
            <span><span className="legend-chip wet" /> Rain ≥ 2.5 mm/day (wet day)</span>
            <span><span className="legend-chip dry" /> Rain &lt; 2.5 mm/day (dry day)</span>
            <span>Units: mm/day (model-derived reanalysis, not direct gauge)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
