import type { AdvisoryStatus } from "../engine";

/** Step 21 — localization types. Structured values are the source of truth for rendering;
 * locale packs map rule IDs / crop IDs + these values to localized text. English (`en`)
 * is the fallback for every locale and every key. */

export type LocaleCode = "en" | "mr" | "hi";

/** Structured snapshot of everything advisory text may reference. Numbers stay raw;
 * formatting happens at render time via Intl (locale-aware). */
export interface AdvisoryValues {
  probability: number;
  risk_category: "low" | "moderate" | "high";
  horizon_days: number;
  location_name: string;
  data_age_days: number;
  input_completeness: number;
  freshness: "current" | "recent" | "stale";
  mean_predicted: number | null;
  observed_rate: number | null;
  mean_diff: number | null;
  evidence_level: string;
  crop_name: string; // resolved localized crop display name
  n_stability_years: number | null;
  bss_min: number | null;
  bss_max: number | null;
}

/** Every translatable string is a function of the structured values — no preformatted
 * English strings are stored. Keys are grouped by what they translate. */
export interface LocalePack {
  code: LocaleCode;
  label: string; // native endonym, e.g. "मराठी"
  status: Record<AdvisoryStatus, string>;
  headline: {
    elevated: (v: AdvisoryValues) => string;
    lower: (v: AdvisoryValues) => string;
  };
  message: {
    elevated: (v: AdvisoryValues) => string;
    lower: (v: AdvisoryValues) => string;
  };
  rules: Record<string, {
    label: string;                    // localized rule name for the why-panel
    detail: (v: AdvisoryValues) => string;
  }>;
  ui: {
    advisory_title: string;
    language_label: string;
    crop_label: string;
    monitoring_title: string;
    cautions_title: string;
    why_toggle: string;
    why_model_context: (v: AdvisoryValues) => string;
    disclaimer: string;
  };
  freshness: Record<"current" | "recent" | "stale", string>;
  evidence_level: (evidence: string, v: AdvisoryValues) => string;
  calibration_interpretation: (v: AdvisoryValues) => string;
  risk_category: Record<"low" | "moderate" | "high", string>;
}

/** Crop templates localized per locale; IDs unchanged across locales (Step 20 contract). */
export interface LocalizedCropTemplate {
  id: string;
  name: string;
  context: string;
  elevatedBody: string;
  lowerBody: string;
  monitoring: string[];
  caveat: string;
}
