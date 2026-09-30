import { useEffect, useMemo, useState } from "react";
import RiskMap from "./RiskMap";
import Dashboard from "./Dashboard";
import HistoryCharts from "./HistoryCharts";
import AdvisoryPanel from "./AdvisoryPanel";
import { errorText, fetchPrediction, fetchTree, pilotDistricts, type LocationNode, type Prediction } from "./api";

/** Step 17/18 application shell. Loads the location tree ONCE and shares it with the map
 * and the dashboard's selector (no second data layer). Selecting a district on the map or
 * in the selector drives the same dashboard + historical view. View is deep-linkable via
 * ?tab=dashboard&loc=<id> for demos and Step 19+ navigation. */

function initialState(): { tab: "map" | "dashboard"; loc: number | null } {
  const p = new URLSearchParams(window.location.search);
  const tab = p.get("tab") === "dashboard" ? "dashboard" : "map";
  const loc = p.get("loc") ? Number(p.get("loc")) : null;
  return { tab, loc: Number.isFinite(loc) ? loc : null };
}

/** Small inline monsoon/cloud glyph for the masthead (no icon dependency). */
function BrandMark() {
  return (
    <span className="header-mark" aria-hidden="true">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path
          d="M7 15a4.5 4.5 0 0 1-.36-8.99A5.5 5.5 0 0 1 17.29 7.6 3.75 3.75 0 0 1 16.75 15H7Z"
          fill="rgba(255,255,255,0.92)"
        />
        <path d="M8.5 17.5l-1 3M12 17.5l-1 3M15.5 17.5l-1 3" stroke="#7fd0ff" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export default function App() {
  const [districts, setDistricts] = useState<LocationNode[] | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(() => initialState().loc);
  const [tab, setTab] = useState<"map" | "dashboard">(() => initialState().tab);
  const [pred, setPred] = useState<Prediction | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTree()
      .then((t) => {
        if (cancelled) return;
        const ds = pilotDistricts(t);
        setDistricts(ds);
        if (ds.length) setSelectedId((cur) => cur ?? ds[0].id);
      })
      .catch((e) => {
        if (!cancelled) setTreeError(errorText(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () => districts?.find((d) => d.id === selectedId) ?? null,
    [districts, selectedId]
  );

  // keep the URL shareable without reloading
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    p.set("tab", tab);
    if (selectedId != null) p.set("loc", String(selectedId));
    window.history.replaceState(null, '', `${window.location.pathname}?${p.toString()}`);
  }, [tab, selectedId]);

  // Fetch the prediction once here so the Dashboard and the Step 19/20 AdvisoryPanel share
  // the SAME response object (no second data path; no refetch churn between panels).
  useEffect(() => {
    if (tab !== "dashboard" || selectedId == null) return;
    let cancelled = false;
    setPred(null);
    fetchPrediction(selectedId)
      .then((p) => {
        if (!cancelled) setPred(p);
      })
      .catch(() => {
        /* Dashboard renders its own structured error panel; no advisory without a prediction. */
      });
    return () => {
      cancelled = true;
    };
  }, [tab, selectedId]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="header-brand">
            <BrandMark />
            <div className="header-identity">
              <h1>Hyperlocal Monsoon Intelligence</h1>
              <p className="header-sub">
                Probabilistic monsoon break-risk estimates at district scale, from observed
                rainfall patterns — for planning and monitoring, not weather forecasts.
              </p>
            </div>
          </div>
        </div>
      </header>

      {treeError && (
        <div className="card error" data-testid="app-error" role="alert" style={{ marginTop: 16 }}>
          <strong>Backend unavailable.</strong> <span>{treeError}</span>
          <span className="muted small">Is the API server running on port 8000?</span>
        </div>
      )}

      {!districts && !treeError && (
        <div className="card" data-testid="app-loading" style={{ marginTop: 16 }}>
          <span className="loading-line"><span className="spinner" /> Loading pilot locations…</span>
        </div>
      )}

      {districts && (
        <>
          <div className="toolbar">
            <label className="toolbar-label" htmlFor="loc-select">
              Location
              <select
                id="loc-select"
                data-testid="location-select"
                value={selectedId ?? ""}
                onChange={(e) => {
                  setSelectedId(Number(e.target.value));
                  setTab("dashboard");
                }}
              >
                {districts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.district ?? d.name}, {d.state})
                  </option>
                ))}
              </select>
            </label>
            <span className="spacer" />
            <div className="tabs" role="tablist">
              <button
                role="tab"
                aria-selected={tab === "map"}
                className={tab === "map" ? "on" : ""}
                onClick={() => setTab("map")}
                data-testid="tab-map"
              >
                Map
              </button>
              <button
                role="tab"
                aria-selected={tab === "dashboard"}
                className={tab === "dashboard" ? "on" : ""}
                onClick={() => setTab("dashboard")}
                data-testid="tab-dashboard"
              >
                Dashboard
              </button>
            </div>
          </div>

          {/* Location hierarchy is state > district today; blocks/panchayats will appear in
              this selector automatically once real rows exist (Step 15 tree drives it). */}
          {tab === "map" ? (
            <RiskMap
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setTab("dashboard");
              }}
            />
          ) : (
            selected && (
              <>
                <Dashboard locationId={selected.id} locationName={selected.name} />
                {pred && <AdvisoryPanel pred={pred} />}
                <HistoryCharts locationId={selected.id} />
              </>
            )
          )}
        </>
      )}
    </div>
  );
}
