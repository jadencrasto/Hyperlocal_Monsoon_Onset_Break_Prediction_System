import { useEffect, useMemo, useState } from "react";
import RiskMap from "./RiskMap";
import Dashboard from "./Dashboard";
import HistoryCharts from "./HistoryCharts";
import AdvisoryPanel from "./AdvisoryPanel";
import LocationSelector from "./LocationSelector";
import RainfallAnalysis from "./RainfallAnalysis";
import OnsetSection from "./OnsetSection";
import ForecastSection from "./ForecastSection";
import TechnicalDiagnostics from "./TechnicalDiagnostics";
import SystemStatusBar from "./SystemStatusBar";
import {
  errorText,
  fetchPrediction,
  fetchTree,
  pilotDistricts,
  type LocationNode,
  type LocationTree,
  type Prediction,
} from "./api";

export type AppTab =
  | "dashboard"
  | "rainfall"
  | "onset_forecast"
  | "advisory"
  | "map"
  | "history"
  | "technical";

function initialState(): { tab: AppTab; loc: number | null } {
  const p = new URLSearchParams(window.location.search);
  const rawTab = p.get("tab");
  const tab: AppTab =
    rawTab === "map" ||
    rawTab === "rainfall" ||
    rawTab === "onset_forecast" ||
    rawTab === "advisory" ||
    rawTab === "history" ||
    rawTab === "technical"
      ? rawTab
      : "dashboard";
  const loc = p.get("loc") ? Number(p.get("loc")) : null;
  return { tab, loc: Number.isFinite(loc) ? loc : null };
}

function BrandMark() {
  return (
    <span className="header-mark" aria-hidden="true">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path
          d="M7 15a4.5 4.5 0 0 1-.36-8.99A5.5 5.5 0 0 1 17.29 7.6 3.75 3.75 0 0 1 16.75 15H7Z"
          fill="rgba(255,255,255,0.92)"
        />
        <path
          d="M8.5 17.5l-1 3M12 17.5l-1 3M15.5 17.5l-1 3"
          stroke="#7fd0ff"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export default function App() {
  const [tree, setTree] = useState<LocationTree | null>(null);
  const [districts, setDistricts] = useState<LocationNode[] | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(() => initialState().loc);
  const [tab, setTab] = useState<AppTab>(() => initialState().tab);
  const [pred, setPred] = useState<Prediction | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTree()
      .then((t) => {
        if (cancelled) return;
        setTree(t);
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
    () => districts?.find((d) => d.id === selectedId) ?? districts?.[0] ?? null,
    [districts, selectedId]
  );

  const [isDemoMode, setIsDemoMode] = useState<boolean>(false);
  const [demoDate, setDemoDate] = useState<string>("2026-09-25");

  // Keep URL in sync
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    p.set("tab", tab);
    if (selectedId != null) p.set("loc", String(selectedId));
    window.history.replaceState(null, "", `${window.location.pathname}?${p.toString()}`);
  }, [tab, selectedId]);

  // Fetch prediction whenever selected location or demo mode changes
  useEffect(() => {
    if (selectedId == null) return;
    let cancelled = false;
    setPred(null);
    const asOf = isDemoMode ? demoDate : undefined;
    fetchPrediction(selectedId, asOf)
      .then((p) => {
        if (!cancelled) setPred(p);
      })
      .catch(() => {
        /* Handled inside Dashboard component */
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, isDemoMode, demoDate]);

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

      <SystemStatusBar />

      {treeError && (
        <div className="card error" data-testid="app-error" role="alert" style={{ marginTop: 16 }}>
          <strong>Backend unavailable.</strong> <span>{treeError}</span>
          <span className="muted small">Is the API server running on port 8000?</span>
        </div>
      )}

      {!districts && !treeError && (
        <div className="card" data-testid="app-loading" style={{ marginTop: 16 }}>
          <span className="loading-line">
            <span className="spinner" /> Loading pilot locations…
          </span>
        </div>
      )}

      {districts && (
        <>
          <div className="toolbar main-nav-toolbar">
            <LocationSelector
              districts={districts}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
              }}
              tree={tree}
            />

            <div className="tabs primary-nav-tabs" role="tablist">
              <button
                role="tab"
                aria-selected={tab === "dashboard"}
                className={tab === "dashboard" ? "on" : ""}
                onClick={() => setTab("dashboard")}
                data-testid="tab-dashboard"
              >
                Overview
              </button>
              <button
                role="tab"
                aria-selected={tab === "rainfall"}
                className={tab === "rainfall" ? "on" : ""}
                onClick={() => setTab("rainfall")}
                data-testid="tab-rainfall"
              >
                Rainfall Analysis
              </button>
              <button
                role="tab"
                aria-selected={tab === "onset_forecast"}
                className={tab === "onset_forecast" ? "on" : ""}
                onClick={() => setTab("onset_forecast")}
                data-testid="tab-onset"
              >
                Onset &amp; Forecast
              </button>
              <button
                role="tab"
                aria-selected={tab === "advisory"}
                className={tab === "advisory" ? "on" : ""}
                onClick={() => setTab("advisory")}
                data-testid="tab-advisory"
              >
                Advisory
              </button>
              <button
                role="tab"
                aria-selected={tab === "map"}
                className={tab === "map" ? "on" : ""}
                onClick={() => setTab("map")}
                data-testid="tab-map"
              >
                Risk Map
              </button>
              <button
                role="tab"
                aria-selected={tab === "history"}
                className={tab === "history" ? "on" : ""}
                onClick={() => setTab("history")}
                data-testid="tab-history"
              >
                Historical
              </button>
              <button
                role="tab"
                aria-selected={tab === "technical"}
                className={tab === "technical" ? "on" : ""}
                onClick={() => setTab("technical")}
                data-testid="tab-technical"
              >
                Model &amp; Data
              </button>
            </div>
          </div>

          <main className="app-main-content">
            {tab === "map" && (
              <RiskMap
                selectedId={selectedId}
                onSelect={(id) => {
                  setSelectedId(id);
                  setTab("dashboard");
                }}
                asOf={isDemoMode ? demoDate : undefined}
              />
            )}

            {tab === "dashboard" && selected && (
              <>
                <Dashboard
                  locationId={selected.id}
                  locationName={selected.name}
                  isDemoMode={isDemoMode}
                  onToggleDemoMode={setIsDemoMode}
                  demoDate={demoDate}
                  onDemoDateChange={setDemoDate}
                />
                {pred && <AdvisoryPanel pred={pred} />}
                <HistoryCharts locationId={selected.id} />
              </>
            )}

            {tab === "rainfall" && selected && (
              <RainfallAnalysis locationId={selected.id} locationName={selected.name} />
            )}

            {tab === "onset_forecast" && selected && (
              <>
                <OnsetSection locationId={selected.id} locationName={selected.name} />
                <ForecastSection locationId={selected.id} locationName={selected.name} />
              </>
            )}

            {tab === "advisory" && (
              selected && pred ? (
                <AdvisoryPanel pred={pred} />
              ) : (
                selected && (
                  <Dashboard
                    locationId={selected.id}
                    locationName={selected.name}
                    isDemoMode={isDemoMode}
                    onToggleDemoMode={setIsDemoMode}
                    demoDate={demoDate}
                    onDemoDateChange={setDemoDate}
                  />
                )
              )
            )}

            {tab === "history" && selected && (
              <HistoryCharts locationId={selected.id} />
            )}

            {tab === "technical" && selected && (
              <TechnicalDiagnostics locationId={selected.id} locationName={selected.name} />
            )}
          </main>
        </>
      )}
    </div>
  );
}
