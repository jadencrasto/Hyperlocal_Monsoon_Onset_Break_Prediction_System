import { formatUpdateAge, type Prediction } from "./api";

interface DataStatusBadgeProps {
  pred?: Prediction | null;
  error?: string | null;
}

export default function DataStatusBadge({ pred, error }: DataStatusBadgeProps) {
  if (error && /cached_data_too_old/.test(error)) {
    return (
      <div className="status-strip offline" data-testid="status-indicator">
        <span className="badge-chip offline" data-testid="status-connectivity">
          <span className="status-dot offline"></span>
          OFFLINE
        </span>
        <span className="badge-chip warn" data-testid="status-data-type">
          Cached data too old
        </span>
        <span className="status-text warn" data-testid="status-update-time">
          Prediction unavailable
        </span>
      </div>
    );
  }

  if (!pred) return null;

  const ds = pred.data_status;
  const isOffline = ds.cache_status === "offline";
  const isLive = ds.cache_status === "live" || Boolean(ds.is_live);
  const updateText = formatUpdateAge(ds.last_updated, ds.update_age_seconds, ds.latest_rainfall_date);

  return (
    <div className={`status-strip ${isOffline ? "offline" : "online"}`} data-testid="status-indicator">
      <span className={`badge-chip ${isOffline ? "offline" : "online"}`} data-testid="status-connectivity">
        <span className={`status-dot ${isOffline ? "offline" : "online"}`}></span>
        {isOffline ? "OFFLINE" : "ONLINE"}
      </span>
      {pred.evaluation_mode === "historical_demo" ? (
        <span className="badge-chip demo" data-testid="status-demo-mode" style={{ background: "#fef3c7", color: "#92400e", border: "1px solid #f59e0b" }}>
          Historical Demo ({pred.prediction_date})
        </span>
      ) : (
        <span className={`badge-chip ${isLive ? "live" : "cached"}`} data-testid="status-data-type">
          {isLive ? "Live data" : "Using cached data"}
        </span>
      )}
      <span className="status-text" data-testid="status-update-time">
        {updateText}
      </span>
      <span className="status-text muted" data-testid="status-source">
        source: {ds.provider ?? "unknown"}
      </span>
      {ds.freshness === "stale" && (
        <span className="badge-chip warn" data-testid="status-freshness">
          stale
        </span>
      )}
    </div>
  );
}
