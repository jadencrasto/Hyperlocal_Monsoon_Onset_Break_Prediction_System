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
    cache_status?: "cached" | "offline"; // Step 23: never "live" - the prediction always reads the local store
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

export const fetchMode = () => getJson<ModeInfo>("/api/mode");
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
