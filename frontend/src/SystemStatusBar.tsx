import React, { useEffect, useState } from "react";
import { FiCalendar, FiInfo, FiX } from "react-icons/fi";
import { fetchHealth, fetchMode, MODEL_SEASON, type HealthResponse, type ModeInfo } from "./api";

interface SystemStatusBarProps {
  onRefresh?: () => void;
}

/** Determine if current date is within model operating season (Jun 15 - Sep 30). */
function isInSeason(): boolean {
  const now = new Date();
  const m = now.getMonth(); // 0-indexed
  const d = now.getDate();
  // Jun (5) 15 through Sep (8) 30
  if (m < 5 || m > 8) return false;
  if (m === 5 && d < 15) return false;
  return true;
}

export default function SystemStatusBar({ onRefresh }: SystemStatusBarProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mode, setMode] = useState<ModeInfo | null>(null);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchHealth().catch(() => null), fetchMode().catch(() => null)]).then(
      ([h, m]) => {
        if (!cancelled) {
          setHealth(h);
          setMode(m);
        }
      }
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const actualState = health?.actual_operating_state ?? mode?.effective ?? "online";
  const isOnline = actualState === "online";
  const isDegraded = actualState === "degraded_offline";
  const inSeason = isInSeason();

  return (
    <div className="system-status-bar" data-testid="system-status-bar">
      <div className="status-bar-inner">
        <div className="status-badge-group">
          <span
            className={`status-chip ${isOnline ? "online" : isDegraded ? "degraded" : "offline"}`}
            data-testid="sys-status-chip"
          >
            <span className="dot" />
            {isOnline ? "ONLINE — Live Data" : isDegraded ? "DEGRADED — Offline Fallback" : "OFFLINE — Local Cache"}
          </span>

          <span className="status-chip secondary" data-testid="sys-db-status">
            DB: {health?.database === "ok" ? "Connected" : "Unknown"}
          </span>

          <span className="status-chip secondary" data-testid="sys-model-status">
            Model: {health?.model_available ? "Loaded" : "Not Trained"}
          </span>

          {!inSeason && (
            <span className="status-chip off-season-chip" data-testid="sys-season-chip">
              <FiCalendar aria-hidden="true" style={{ marginRight: "4px" }} />
              Off-Season
            </span>
          )}
        </div>

        <div className="status-actions">
          <button
            type="button"
            className="status-details-btn"
            onClick={() => setShowModal(!showModal)}
            data-testid="sys-info-btn"
          >
            System Status <FiInfo aria-hidden="true" style={{ marginLeft: "4px", verticalAlign: "-2px" }} />
          </button>
        </div>
      </div>

      {showModal && (
        <div className="system-status-modal" data-testid="system-status-modal">
          <div className="modal-header">
            <h4>System Operating Environment</h4>
            <button type="button" className="close-btn" onClick={() => setShowModal(false)} aria-label="Close">
              <FiX aria-hidden="true" />
            </button>
          </div>
          <div className="modal-body">
            <dl className="system-dl">
              <dt>Operating State</dt>
              <dd>
                <strong>{actualState.toUpperCase()}</strong> —{" "}
                {isOnline
                  ? "Live weather provider reachable"
                  : isDegraded
                  ? "Configured for online but internet is unreachable; operating safely in offline mode with cached data"
                  : "Operating strictly from locally stored database"}
              </dd>
              <dt>Configured Mode Preference</dt>
              <dd>{health?.mode_preference ?? mode?.preference ?? "auto"}</dd>
              <dt>Internet Reachable</dt>
              <dd>{health?.internet_reachable ? "Yes (active connection)" : "No (offline or blocked)"}</dd>
              <dt>Model Status</dt>
              <dd>{health?.model_available ? "Logistic Regression model artifact ready" : "Model artifact missing"}</dd>
              <dt>Geographic Scope</dt>
              <dd>
                Current: <strong>District-HQ coordinate points</strong>
                <br />
                <span className="muted small">Target future: Block / village target coordinates</span>
              </dd>
              <dt>Spatial Modeling</dt>
              <dd>{health?.spatial_awareness ? "Active" : "Not enabled (current model uses pooled non-spatial features)"}</dd>
              <dt>Prediction Season</dt>
              <dd>{MODEL_SEASON.start} – {MODEL_SEASON.end}</dd>
              <dt>Current Seasonal State</dt>
              <dd>
                <strong data-testid="sys-seasonal-state">{inSeason ? "IN-SEASON" : "OFF-SEASON"}</strong>
                {!inSeason && (
                  <span className="muted small"> — Break-risk predictions are intentionally disabled outside the validated operating window</span>
                )}
              </dd>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
