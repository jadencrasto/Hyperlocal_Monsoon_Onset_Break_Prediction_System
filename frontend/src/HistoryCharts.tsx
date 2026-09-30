import { useEffect, useMemo, useState } from "react";
import {
  errorText, fetchCoverage, fetchDrySpells, fetchHistory,
  type Coverage, type DrySpell, type HistoryRecord,
} from "./api";

/** Step 18 historical view for one location. Shows OBSERVED data only:
 *  - daily rainfall bars (from GET /history, reanalysis with provenance note),
 *  - dry-spell events (from GET /monsoon/dry-spells - the backend's scientific label),
 *  - a season selector bounded by the location's real coverage.
 * There is deliberately NO historical probability timeline: the backend computes
 * predictions on demand and stores none, so none is shown or invented. */

const SEASONS = [
  { yearsBack: 0, label: "Latest season" },
  { yearsBack: 1, label: "Previous season" },
  { yearsBack: 5, label: "5 seasons back" },
  { yearsBack: 10, label: "10 seasons back" },
];

function seasonRange(today: Date, yearsBack: number): { start: string; end: string; year: number } {
  const y = today.getFullYear() - yearsBack;
  // The model's season window: Jun 15 - Sep 30 (monsoon analysis domain).
  const start = new Date(Date.UTC(y, 5, 15));
  const end = new Date(Date.UTC(y, 8, 30));
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
    year: y,
  };
}

function RainfallChart({
  records, spells,
}: {
  records: HistoryRecord[];
  spells: DrySpell[];
}) {
  const max = Math.max(1, ...records.map((r) => r.precip_mm ?? 0));
  const spellStarts = new Map<string, DrySpell>(spells.map((s) => [s.start, s]));
  const wet = records.filter((r) => (r.precip_mm ?? 0) >= 2.5).length;
  return (
    <div data-testid="rainfall-chart">
      <div className="rain-strip" role="img" aria-label="Daily rainfall bars">
        {records.map((r) => {
          const v = r.precip_mm ?? 0;
          const spell = spellStarts.get(r.date);
          return (
            <div
              key={r.date}
              className={`rain-bar ${v >= 2.5 ? "wet" : "dry"} ${spell ? "spell-start" : ""}`}
              style={{ height: `${Math.max(2, (v / max) * 100)}%` }}
              title={`${r.date}: ${v.toFixed(1)} mm${spell ? ` · dry spell ${spell.start}..${spell.end} (${spell.length_days}d)` : ""}`}
              data-date={r.date}
            />
          );
        })}
      </div>
      <div className="chart-legend muted small">
        <span><span className="legend-chip wet" /> rain ≥ 2.5 mm/day</span>
        <span><span className="legend-chip dry" /> dry (&lt; 2.5 mm)</span>
        <span><span className="legend-chip spell" /> dry-spell event start</span>
        <span>wet-day share: {records.length ? pct0(wet / records.length) : "n/a"}</span>
      </div>
    </div>
  );
}

const pct0 = (v: number) => `${(v * 100).toFixed(0)}%`;

export default function HistoryCharts({ locationId }: { locationId: number }) {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [seasonIdx, setSeasonIdx] = useState(0);
  const [records, setRecords] = useState<HistoryRecord[] | null>(null);
  const [spells, setSpells] = useState<DrySpell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchCoverage(locationId)
      .then((c) => {
        if (!cancelled) setCoverage(c);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [locationId]);

  const range = useMemo(() => seasonRange(new Date(), SEASONS[seasonIdx].yearsBack), [seasonIdx]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchHistory(locationId, range.start, range.end),
      fetchDrySpells(locationId, range.year, false),
    ])
      .then(([h, s]) => {
        if (cancelled) return;
        setRecords(h.records);
        setSpells(s.spells);
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
  }, [locationId, range]);

  if (error) {
    return (
      <div className="card error" data-testid="history-error" role="alert">
        <strong>Historical view unavailable.</strong>
        <span>{error}</span>
      </div>
    );
  }

  const inSeason =
    coverage?.first_date && range.start >= coverage.first_date && range.start <= (coverage.last_date ?? "");
  const n = records?.length ?? 0;
  const hasEvents = (spells?.length ?? 0) > 0;

  return (
    <div className="card" data-testid="history-panel">
      <div className="history-head">
        <h4>Observed history — {range.year} monsoon season (Jun 15 – Sep 30)</h4>
        <select
          aria-label="Season"
          value={seasonIdx}
          onChange={(e) => setSeasonIdx(Number(e.target.value))}
          data-testid="season-select"
        >
          {SEASONS.map((s, i) => (
            <option key={s.label} value={i}>{s.label}</option>
          ))}
        </select>
      </div>
      <p className="muted small">
        Bars: <strong>observed daily rainfall</strong> (mm/day, reanalysis). Markers:{" "}
        <strong>dry-spell events</strong> per the model's scientific label (≥5 consecutive days
        under 2.5 mm within a 7-day window). This is observation history, not a prediction
        timeline — the model computes probabilities on demand and stores none.
      </p>
      {loading && (
        <div className="loading-line" data-testid="history-loading">
          <span className="spinner" /> Loading history…
        </div>
      )}
      {!loading && n === 0 && (
        <div className="state" data-testid="history-empty">
          No stored rainfall for this season
          {inSeason === false && coverage
            ? ` (stored coverage starts ${coverage.first_date}${coverage.last_date ? `, ends ${coverage.last_date}` : ""}).`
            : "."}
          {coverage?.last_date && range.end > coverage.last_date
            ? " Note: seasons after the last stored date are incomplete in the database."
            : ""}
        </div>
      )}
      {!loading && records != null && n > 0 && (
        <>
          <RainfallChart records={records} spells={spells ?? []} />
          <div className="muted small" data-testid="spell-count">
            {hasEvents
              ? `${spells!.length} dry-spell event${spells!.length === 1 ? "" : "s"} in this season (after-onset window included).`
              : "No dry-spell events met the scientific definition in this season."}
          </div>
        </>
      )}
    </div>
  );
}
