import { useEffect, useMemo, useState } from "react";
import { FiAlertTriangle } from "react-icons/fi";
import {
  MapContainer, TileLayer, Marker, Popup, CircleMarker, useMap,
} from "react-leaflet";
import L from "leaflet";
import {
  ApiError, extractPredictionError, fetchPrediction, fetchTree, MODEL_SEASON, pilotDistricts,
  type LocationNode, type Prediction, type PredictionErrorKind,
} from "./api";

// Presentation severity colors for the demo bands. The bands come from the API's
// risk_bands metadata; they are NOT calibrated decision thresholds (see Step 14).
export const severityColor: Record<Prediction["risk_category"], string> = {
  low: "#2e7d32",
  moderate: "#f9a825",
  high: "#c62828",
};

/** Off-season marker color — muted gray, explicitly NOT a risk color. */
const OFF_SEASON_COLOR = "#90a4ae";

type MapMarker = {
  loc: LocationNode;
  pred: Prediction | null;
  error: string | null;
  errorKind: PredictionErrorKind | null;
};

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) {
      map.fitBounds(L.latLngBounds(points).pad(0.25));
    }
  }, [map, points]);
  return null;
}

/** Step 22: keep the map correctly sized when its container resizes without a reload —
 * mobile browser URL-bar show/hide (dvh change), rotation, desktop window resize.
 * Presentation-only; markers, popups and predictions are untouched. */
function AutoResize() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const invalidate = () => map.invalidateSize({ animate: false });
    const ro =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(invalidate) : null;
    ro?.observe(el);
    window.addEventListener("orientationchange", invalidate);
    return () => {
      ro?.disconnect();
      window.removeEventListener("orientationchange", invalidate);
    };
  }, [map]);
  return null;
}

function DetailCard({ pred, error, errorKind }: { pred: Prediction | null; error: string | null; errorKind: PredictionErrorKind | null }) {
  if (errorKind === "out_of_season") {
    return (
      <div className="card off-season-card" data-testid="detail-off-season">
        <strong>Break-risk prediction unavailable — off-season</strong>
        <p className="muted small">
          Model operating season: {MODEL_SEASON.start} – {MODEL_SEASON.end}.
          Predictions are intentionally disabled outside this window.
        </p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="card error" data-testid="detail-error">
        <strong>Prediction unavailable.</strong>
        <span>{error}</span>
      </div>
    );
  }
  if (!pred) return null;
  const ds = pred.data_status;
  const bss = pred.model.test_skill.brier_skill_vs_climatology;
  return (
    <div className="card" data-testid="detail-card">
      <h3>
        {pred.location.name}{" "}
        <span className="badge" style={{ background: severityColor[pred.risk_category] }}>
          {pred.risk_category}
        </span>
      </h3>
      <p className="prob">
        Break probability: <strong>{(pred.probability * 100).toFixed(1)}%</strong>{" "}
        <span className="muted">(over the next {pred.horizon_days} days)</span>
      </p>
      <dl>
        <dt>Prediction date</dt>
        <dd>{pred.prediction_date}</dd>
        <dt>Data freshness</dt>
        <dd>
          {ds.freshness}{" "}
          {ds.freshness === "stale" && (
            <span className="warn" data-testid="stale-flag">
              <FiAlertTriangle aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
              rainfall data is {ds.data_age_days} days old — treat with caution
            </span>
          )}
        </dd>
        <dt>Input completeness</dt>
        <dd data-testid="completeness">
          {(ds.input_completeness * 100).toFixed(0)}%
          {ds.input_completeness < 1 && (
            <span className="warn">
              <FiAlertTriangle aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: "3px" }} />
              gaps in recent rainfall
            </span>
          )}
        </dd>
        <dt>Latest rainfall stored</dt>
        <dd>{ds.latest_rainfall_date}</dd>
        <dt>Model</dt>
        <dd>
          Historical-pattern model (trained through {pred.model.trained_through ?? "n/a"})
        </dd>
        <dt>Evaluation</dt>
        <dd>
          {bss == null
            ? "No historical evaluation available"
            : bss > 0
              ? `Modest improvement over the climatology baseline (BSS ${bss.toFixed(3)})`
              : "No improvement over the climatology baseline"}
        </dd>
      </dl>
      <p className="muted small">{pred.basis}</p>
      <p className="muted small">{pred.risk_bands.note ?? ""}</p>
    </div>
  );
}

export default function RiskMap({
  selectedId = null,
  onSelect,
}: {
  /** Shared selection from the app shell (Step 17); null keeps Step 16 internal state. */
  selectedId?: number | null;
  onSelect?: (locationId: number) => void;
}) {
  const [markers, setMarkers] = useState<MapMarker[] | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [internalSel, setInternalSel] = useState<MapMarker | null>(null);
  const [predictionsDone, setPredictionsDone] = useState(false);

  // When the parent controls selection, derive the selected marker from it.
  const selected =
    selectedId != null ? (markers ?? []).find((m) => m.loc.id === selectedId) ?? null : internalSel;
  const setSelected = (m: MapMarker | null) => {
    setInternalSel(m);
    if (m && onSelect) onSelect(m.loc.id);
  };

  // Derived: are ALL loaded markers in out_of_season state?
  const allOffSeason = predictionsDone && markers != null && markers.length > 0 &&
    markers.every((m) => m.errorKind === "out_of_season");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const tree = await fetchTree();
        const districts = pilotDistricts(tree);
        if (cancelled) return;
        if (!districts.length) {
          setMarkers([]);
          setPredictionsDone(true);
          return;
        }
        setMarkers(districts.map((loc) => ({ loc, pred: null, error: null, errorKind: null })));
        // Predictions load per location; one failure must not blank the map.
        await Promise.all(
          districts.map(async (loc) => {
            let pred: Prediction | null = null;
            let error: string | null = null;
            let errorKind: PredictionErrorKind | null = null;
            try {
              pred = await fetchPrediction(loc.id);
            } catch (e) {
              const parsed = extractPredictionError(e);
              error = parsed.label;
              errorKind = parsed.kind;
            }
            if (cancelled) return;
            setMarkers((prev) =>
              (prev ?? []).map((m) => (m.loc.id === loc.id ? { loc, pred, error, errorKind } : m))
            );
          })
        );
        if (!cancelled) setPredictionsDone(true);
      } catch (e) {
        if (!cancelled) setTreeError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const points = useMemo(
    () =>
      (markers ?? [])
        .filter((m) => m.loc.latitude != null && m.loc.longitude != null)
        .map((m) => [m.loc.latitude!, m.loc.longitude!] as [number, number]),
    [markers]
  );

  if (treeError) {
    return (
      <div className="state error-state" data-testid="map-error">
        <h2>Map unavailable</h2>
        <p>Could not load locations: {treeError}</p>
        <p className="muted">Is the backend running on port 8000?</p>
      </div>
    );
  }
  if (markers === null) {
    return (
      <div className="state" data-testid="map-loading">
        <span className="loading-line"><span className="spinner" /> Loading locations…</span>
      </div>
    );
  }
  if (!markers.length) {
    return (
      <div className="state" data-testid="map-empty">
        No pilot districts with stored rainfall data were found. Run scripts/download_history.py
        first.
      </div>
    );
  }

  return (
    <div className="map-wrap">
      <div className="map-side">
        <h2>Maharashtra pilot districts</h2>
        <p className="muted small">
          Historical-pattern-based break-risk estimate from stored rainfall only — NOT a weather
          forecast.
        </p>
        {!predictionsDone && <p className="muted" data-testid="pred-loading">Loading predictions…</p>}

        {/* Map-level off-season banner */}
        {allOffSeason && (
          <div className="off-season-card map-off-season-banner" data-testid="map-off-season-banner">
            <strong>Break-risk prediction is currently off-season</strong>
            <p className="muted small">
              Model operating season: {MODEL_SEASON.start} – {MODEL_SEASON.end}
            </p>
            <p className="muted small">
              Pilot locations remain available for rainfall, historical analysis, forecast and other supported views.
            </p>
          </div>
        )}

        <ul className="loc-list">
          {markers.map((m) => (
            <li key={m.loc.id}>
              <button
                className={selected?.loc.id === m.loc.id ? "sel" : ""}
                onClick={() => setSelected(m)}
              >
                {m.pred && (
                  <span className="dot" style={{ background: severityColor[m.pred.risk_category] }} />
                )}
                {m.errorKind === "out_of_season" && !m.pred && (
                  <span className="dot" style={{ background: OFF_SEASON_COLOR }} />
                )}
                {m.loc.name}
                {m.pred && <span className="pct"> {(m.pred.probability * 100).toFixed(0)}%</span>}
                {m.pred?.data_status.freshness === "stale" && (
                  <span className="warn" title="Stale data">
                    <FiAlertTriangle aria-hidden="true" style={{ verticalAlign: "-1px", marginLeft: "4px" }} />
                  </span>
                )}
                {m.errorKind === "out_of_season" && <span className="muted"> (off-season)</span>}
                {m.error && m.errorKind !== "out_of_season" && <span className="muted"> (n/a)</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="map-legend" aria-label="Risk color legend">
          <span className="map-legend-title">Break-risk</span>
          <span className="legend-item"><span className="legend-swatch" style={{ background: severityColor.low }} /> Low</span>
          <span className="legend-item"><span className="legend-swatch" style={{ background: severityColor.moderate }} /> Moderate</span>
          <span className="legend-item"><span className="legend-swatch" style={{ background: severityColor.high }} /> High</span>
          {allOffSeason && (
            <span className="legend-item"><span className="legend-swatch" style={{ background: OFF_SEASON_COLOR }} /> Off-season</span>
          )}
        </div>
        <DetailCard pred={selected?.pred ?? null} error={selected?.error ?? null} errorKind={selected?.errorKind ?? null} />
      </div>
      <MapContainer
        center={[19.5, 75.5]}
        zoom={6}
        className="leaflet-container"
        scrollWheelZoom
        data-testid="leaflet-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={points} />
        <AutoResize />
        {markers.map((m) =>
          m.pred ? (
            <CircleMarker
              key={m.loc.id}
              center={[m.loc.latitude!, m.loc.longitude!]}
              radius={m.loc.id === selected?.loc.id ? 16 : 13}
              pathOptions={{
                color: m.loc.id === selected?.loc.id ? "#0b2239" : severityColor[m.pred.risk_category],
                weight: m.loc.id === selected?.loc.id ? 3 : 1.5,
                fillColor: severityColor[m.pred.risk_category],
                fillOpacity: 0.72,
              }}
              eventHandlers={{ click: () => setSelected(m) }}
            >
              <Popup>
                <strong>{m.loc.name}</strong>
                <br />
                {(m.pred.probability * 100).toFixed(1)}% · {m.pred.risk_category} break-risk
                <br />
                as of {m.pred.prediction_date} · data {m.pred.data_status.freshness}
              </Popup>
            </CircleMarker>
          ) : m.errorKind === "out_of_season" ? (
            <CircleMarker
              key={m.loc.id}
              center={[m.loc.latitude!, m.loc.longitude!]}
              radius={m.loc.id === selected?.loc.id ? 16 : 11}
              pathOptions={{
                color: m.loc.id === selected?.loc.id ? "#0b2239" : OFF_SEASON_COLOR,
                weight: m.loc.id === selected?.loc.id ? 3 : 1.5,
                fillColor: OFF_SEASON_COLOR,
                fillOpacity: 0.45,
              }}
              eventHandlers={{ click: () => setSelected(m) }}
            >
              <Popup>
                <strong>{m.loc.name}</strong>
                <br />
                Off-season — predictions available {MODEL_SEASON.start} – {MODEL_SEASON.end}
              </Popup>
            </CircleMarker>
          ) : (
            <Marker key={m.loc.id} position={[m.loc.latitude!, m.loc.longitude!]}>
              <Popup>
                {m.loc.name}
                <br />
                {m.error ? "Prediction unavailable" : "Loading prediction…"}
              </Popup>
            </Marker>
          )
        )}
      </MapContainer>
    </div>
  );
}
