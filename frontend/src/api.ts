// Typed client for the Step 15 location APIs, the Step 13/14 prediction API, and the
// historical observation APIs used by Step 18. Mirrors docs/STEP14_RESPONSE_SCHEMA.md.

export type Level = "state" | "district" | "block" | "panchayat";

export interface LocationNode {
  id: number;
  name: string;
  level: Level;
  parent_id: number | null;
  state: string;
  district: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinate_note: string | null;
  n_children?: number;
  has_data?: boolean;
  children?: LocationNode[];
}

export interface LocationTree {
  levels: Level[];
  levels_present: Level[];
  levels_with_data: string[];
  roots: LocationNode[];
}

export interface Prediction {
  type: string;
  schema_version: string;
  location: {
    id: number;
    name: string;
    level: string;
    parent_id: number | null;
    state: string;
    district: string | null;
    latitude: number | null;
    longitude: number | null;
  };
  prediction_date: string;
  probability: number;
  risk_category: "low" | "moderate" | "high";
  risk_bands: Record<string, string> & { note?: string };
  horizon_days: number;
  event: string;
  basis: string;
  model: {
    name: string;
    trained_on_locations: number[] | null;
    trained_through: string | null;
    test_skill: { brier_skill_vs_climatology: number | null; brier_skill_ci: unknown };
    baselines: Record<string, number | null>;
    caveats?: string[];
  };
  uncertainty: Record<string, unknown>;
  data_status: {
    source: string;
    provider?: string | null;          // Step 23: provenance of the most recent stored row
    latest_rainfall_date: string;
    data_age_days: number;
    freshness: "current" | "recent" | "stale";
    input_days_used: number;
    input_completeness: number;
    cache_status?: "cached" | "offline" | "live";
    data_source?: "live" | "cache";
    is_live?: boolean;
    last_updated?: string | null;
    update_age_seconds?: number | null;
  };
  /** Step 25: most recent failed refresh (24h window); null when healthy/old. */
  last_sync_failure?: {
    kind: string;
    provider: string;
    category: string | null;
    message: string | null;
    finished_at: string;
  } | null;
  limitations: string[];
}

export interface HistoryRecord {
  date: string;
  precip_mm: number | null;
  kind: string;
  provider: string;
  fetched_at: string | null;
}

export interface HistoryResponse {
  location_id: number;
  unit: string;
  note: string;
  records: HistoryRecord[];
}

export interface DrySpell {
  start: string;
  end: string;
  length_days: number;
  total_mm: number;
  ended_by: string;
  scope: string;
  resumption_date: string | null;
}

export interface DrySpellsResponse {
  location_id: number;
  year: number;
  type: string;
  note: string;
  onset_date: string | null;
  spells: DrySpell[];
}

export interface Coverage {
  location_id: number;
  level: string;
  n_locations_with_data: number;
  rows: number;
  first_date: string | null;
  last_date: string | null;
  note?: string;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`API ${status}`);
  }
}

/** Canonical prediction error kinds — maps backend error codes to frontend states. */
export type PredictionErrorKind =
  | "out_of_season"
  | "insufficient_data"
  | "model_not_trained"
  | "cached_data_too_old"
  | "no_stored_history"
  | "location_not_found"
  | "future_date"
  | "network_error"
  | "server_error"
  | "unknown";

/** User-facing labels for each prediction error kind. */
export const PREDICTION_ERROR_LABELS: Record<PredictionErrorKind, string> = {
  out_of_season: "Prediction unavailable — outside model operating season.",
  insufficient_data: "Prediction unavailable — insufficient rainfall history.",
  model_not_trained: "Prediction unavailable — model is not trained.",
  cached_data_too_old: "Prediction unavailable — cached data is too old.",
  no_stored_history: "Prediction unavailable — no stored rainfall history.",
  location_not_found: "Prediction unavailable — location not found.",
  future_date: "Prediction unavailable — future date requested.",
  network_error: "Prediction service could not be reached.",
  server_error: "Prediction service returned an error.",
  unknown: "Prediction unavailable.",
};

/** Model operating season bounds. */
export const MODEL_SEASON = { start: "Jun 15", end: "Sep 30" } as const;

/** Extract a structured prediction error from a caught exception. */
export function extractPredictionError(e: unknown): {
  kind: PredictionErrorKind;
  label: string;
  hint: string | null;
  raw: string;
} {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: { error?: string; hint?: string } } | null;
    const inner = d?.detail ?? {};
    const backendError = inner.error ?? "";
    const hint = inner.hint ?? null;

    const kindMap: Record<string, PredictionErrorKind> = {
      out_of_season: "out_of_season",
      insufficient_or_gappy_history: "insufficient_data",
      model_unavailable: "model_not_trained",
      cached_data_too_old: "cached_data_too_old",
      no_stored_history: "no_stored_history",
      future_date: "future_date",
    };

    if (e.status === 404 && backendError.includes("not found")) {
      return { kind: "location_not_found", label: PREDICTION_ERROR_LABELS.location_not_found, hint, raw: errorText(e) };
    }
    const kind = kindMap[backendError] ?? (e.status >= 500 ? "server_error" : "unknown");
    return { kind, label: PREDICTION_ERROR_LABELS[kind], hint, raw: errorText(e) };
  }
  if (e instanceof TypeError && (e.message.includes("fetch") || e.message.includes("network") || e.message.includes("Failed"))) {
    return { kind: "network_error", label: PREDICTION_ERROR_LABELS.network_error, hint: null, raw: e.message };
  }
  return { kind: "unknown", label: PREDICTION_ERROR_LABELS.unknown, hint: null, raw: e instanceof Error ? e.message : String(e) };
}

/** Step 23: backend connectivity/mode state (existing Step-2 mode API, now consumed). */
export interface ModeInfo {
  preference: "auto" | "online" | "offline";
  effective: "online" | "offline";
  internet_reachable: boolean;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: { error?: string; hint?: string } } | null;
    const inner = d?.detail ?? {};
    return inner.hint ? `${inner.error ?? `HTTP ${e.status}`}: ${inner.hint}` : `HTTP ${e.status}`;
  }
  return e instanceof Error ? e.message : String(e);
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** Pilot districts = level 'district' nodes that actually carry rainfall data. */
export function pilotDistricts(tree: LocationTree): LocationNode[] {
  const out: LocationNode[] = [];
  const walk = (nodes: LocationNode[]) => {
    for (const n of nodes) {
      if (n.level === "district" && n.has_data && n.latitude != null && n.longitude != null) {
        out.push(n);
      }
      if (n.children) walk(n.children);
    }
  };
  walk(tree.roots);
  return out;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  mode_preference: "auto" | "online" | "offline";
  effective_mode: "online" | "offline";
  actual_operating_state: "online" | "offline" | "degraded_offline";
  internet_reachable: boolean;
  model_available: boolean;
  spatial_awareness: boolean;
  geographic_scope: {
    current: string;
    target: string;
    note: string;
  };
  time_utc: string;
}

export interface OnsetResponse {
  location_id: number;
  year: number;
  type: "observed_onset_detection";
  analysis_kind: "retrospective";
  status: "detected" | "not_detected" | string;
  observed_onset: string | null;
  onset_date: string | null;
  detail: Record<string, unknown> | null;
  config: Record<string, unknown>;
  note: string;
}

export interface OnsetPredictionResponse {
  location_id: number;
  type: "onset_prediction";
  prediction_status: "not_implemented" | string;
  predicted_onset: string | null;
  confidence: number | null;
  observed_onset: string | null;
  note: string;
  requirements: string[];
}

export interface ForecastRecord {
  date: string;
  precip_mm: number;
}

export interface ForecastResponse {
  location_id: number;
  type: string;
  provider: string;
  retrieved_at: string;
  age_hours: number;
  freshness: "fresh" | "stale";
  stale_after_hours: number;
  spatial_note: string | null;
  label: string;
  records: ForecastRecord[];
}

export interface ForecastStatusResponse {
  location_id: number;
  forecast_available: boolean;
  freshness: {
    status: string;                    // "valid" | "stale" | "no_data"
    age_hours: number | null;
    stale: boolean | null;
    provider: string | null;
    stale_after_hours?: number;        // present when data exists
    message?: string;                  // present when status is "no_data"
  };
  n_forecast_days: number;
  prediction_integration: {
    integrated: boolean;
    reason: string;
    required_for_integration: string[];
  };
  provider_info: {
    name: string | null;
    retrieved_at: string | null;
    age_hours: number | null;
    stale: boolean | null;
  };
  offline_usable: boolean;
  offline_note: string;
}

/** Backend statuses from data_quality.validate_location_data(). */
export type DataQualityStatus =
  | "valid"
  | "incomplete"
  | "stale"
  | "insufficient_data"
  | "no_data";

export interface DataQualityResponse {
  location_id: number;
  status: DataQualityStatus;
  issues: string[];
  total_records: number;
  first_date: string | null;
  last_date: string | null;
  expected_days: number;
  actual_days: number;
  missing_days: number;
  duplicate_count: number;
  null_precip_count: number;
  impossible_values: number;
  continuity_ratio: number | null;
  providers: string[];
  kinds: string[];
}

/** Per-location entry from /data-quality/coverage (backend coverage_summary). */
export interface CoverageSummaryLocation {
  location_id: number;
  name: string;
  n_records: number;
  first_date: string | null;
  last_date: string | null;
  has_data: boolean;
}

/** Backend response from /data-quality/coverage (coverage_summary()). */
export interface CoverageSummaryResponse {
  n_locations: number;
  locations_with_data: number;
  locations: CoverageSummaryLocation[];
}

export interface ModelEvaluationResponse {
  model_name?: string;
  model_class?: string;
  intended_use?: string;
  caveats?: string[];
  dataset?: {
    first_date?: string;
    last_date?: string;
    n_years?: number;
    n_days?: number;
  };
  data_provenance?: {
    source?: string;
    provider?: string;
    location_selection?: {
      selected_location_ids?: number[];
    };
  };
  test?: {
    brier_skill_vs_climatology?: number;
    brier_skill_ci?: { low?: number; high?: number; n_years?: number };
    model?: { brier?: number };
    baseline_climatology?: { brier?: number };
    baseline_dry_run_conditioned?: { brier?: number };
    calibration?: {
      mean_predicted?: number;
      observed_rate?: number;
      mean_diff?: number;
      note?: string;
    };
    per_year?: Array<{
      year: number;
      brier_skill_vs_climatology?: number;
    }>;
  };
}

/** Backend response from /model/spatial-status (spatial_awareness_status()). */
export interface SpatialStatusResponse {
  is_spatially_aware: boolean;
  spatial_features_in_model: boolean;
  current_features: string[];
  n_features: number;
  location_treatment: string;
  location_treatment_note: string;
  candidate_approaches: Array<{
    name: string;
    status: string;
    description: string;
  }>;
}

export interface SourceProvider {
  name: string;
  kind: string;
  spatial_note?: string;
  last_success?: string | null;
  last_error?: { at: string; message: string; category?: string } | null;
  cached_history_rows: number;
  cached_forecast_rows: number;
}

export interface SourcesResponse {
  providers: SourceProvider[];
  not_integrated: string[];
  note: string;
}

export interface SyncLogItem {
  id: number;
  location_id: number;
  provider: string;
  kind: string;
  status: string;
  n_records: number;
  message: string;
  category: string | null;
  finished_at: string;
}

export const fetchMode = () => getJson<ModeInfo>("/api/mode");
export const fetchHealth = () => getJson<HealthResponse>("/api/health");
export const fetchTree = () => getJson<LocationTree>("/api/locations/tree");
export const fetchPrediction = (locationId: number) =>
  getJson<Prediction>(`/api/locations/${locationId}/prediction/break-risk`);
export const fetchHistory = (locationId: number, start: string, end: string) =>
  getJson<HistoryResponse>(
    `/api/locations/${locationId}/history?start=${start}&end=${end}`
  );
export const fetchDrySpells = (locationId: number, year: number, afterOnset = true) =>
  getJson<DrySpellsResponse>(
    `/api/locations/${locationId}/monsoon/dry-spells?year=${year}&after_onset=${afterOnset}`
  );
export const fetchCoverage = (locationId: number) =>
  getJson<Coverage>(`/api/locations/${locationId}/coverage`);
export const fetchOnset = (locationId: number, year: number) =>
  getJson<OnsetResponse>(`/api/locations/${locationId}/monsoon/onset?year=${year}`);
export const fetchOnsetPrediction = (locationId: number) =>
  getJson<OnsetPredictionResponse>(`/api/locations/${locationId}/monsoon/onset-prediction`);
export const fetchForecast = (locationId: number) =>
  getJson<ForecastResponse>(`/api/locations/${locationId}/forecast`);
export const fetchForecastStatus = (locationId: number) =>
  getJson<ForecastStatusResponse>(`/api/locations/${locationId}/forecast/status`);
export const fetchModelEvaluation = () =>
  getJson<ModelEvaluationResponse>("/api/model/evaluation");
export const fetchSpatialStatus = () =>
  getJson<SpatialStatusResponse>("/api/model/spatial-status");
export const fetchDataQuality = (locationId: number) =>
  getJson<DataQualityResponse>(`/api/locations/${locationId}/data-quality`);
export const fetchCoverageSummary = () =>
  getJson<CoverageSummaryResponse>("/api/data-quality/coverage");
export const fetchSources = () => getJson<SourcesResponse>("/api/sources");
export const fetchSyncLog = (limit = 20) =>
  getJson<SyncLogItem[]>(`/api/sync-log?limit=${limit}`);

export function formatUpdateAge(
  lastUpdated?: string | null,
  updateAgeSeconds?: number | null,
  observationDate?: string
): string {
  if (updateAgeSeconds != null && !isNaN(updateAgeSeconds)) {
    const mins = Math.floor(updateAgeSeconds / 60);
    if (mins < 1) return "Updated just now";
    if (mins < 60) return `Updated ${mins} min ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Last updated ${hours} hr ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return "Last updated yesterday";
    return `Last updated ${days} days ago`;
  }
  if (lastUpdated) {
    try {
      const dt = new Date(lastUpdated);
      const diffMs = Date.now() - dt.getTime();
      if (!isNaN(diffMs) && diffMs >= 0) {
        const mins = Math.floor(diffMs / 60000);
        if (mins < 1) return "Updated just now";
        if (mins < 60) return `Updated ${mins} min ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `Last updated ${hours} hr ago`;
        const days = Math.floor(hours / 24);
        if (days === 1) return "Last updated yesterday";
        return `Last updated ${days} days ago`;
      }
    } catch {
      // fallback
    }
  }
  if (observationDate) {
    return `Observation ${observationDate}`;
  }
  return "Data up to date";
}
