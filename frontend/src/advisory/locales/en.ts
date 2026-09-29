import type { AdvisoryValues, LocalePack } from "./types";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** English reference pack. Every other locale mirrors this key structure exactly;
 * the loader falls back to English per key, so gaps in other packs are safe. */
const en: LocalePack = {
  code: "en",
  label: "English",
  status: {
    informational: "Informational advisory",
    caution: "Caution",
    limited_data: "Limited data — indication may not reflect current conditions",
  },
  headline: {
    elevated: (v) => `Model-based indication of elevated dry-spell risk (${v.risk_category})`,
    lower: () => "Model-based indication of lower dry-spell risk",
  },
  message: {
    elevated: (v) =>
      `The model indicates an elevated possibility of a dry spell or break phase around ${v.location_name} in the coming ${v.horizon_days} days. Consider monitoring soil moisture and local rainfall observations. This indication is not a guarantee that a break will occur.`,
    lower: (v) =>
      `The model currently shows a lower break-risk indication around ${v.location_name}. Local rainfall can still differ from the model's input data; continue routine monitoring. This indication is not a guarantee of favorable conditions.`,
  },
  rules: {
    stale_data: {
      label: "Stale data",
      detail: (v) => `Rainfall data is ${v.data_age_days} days old (freshness: stale).`,
    },
    recent_data: {
      label: "Recent data",
      detail: (v) => `Rainfall data is ${v.data_age_days} day(s) old (freshness: recent).`,
    },
    current_data: {
      label: "Current data",
      detail: () => "Rainfall data is current (age 0–2 days).",
    },
    incomplete_input: {
      label: "Incomplete rainfall input",
      detail: (v) => `Input completeness is ${(v.input_completeness * 100).toFixed(0)}% (recent rainfall contains gaps).`,
    },
    limited_evidence: {
      label: "Limited evaluation evidence",
      detail: (v) => `Evidence level: ${v.evidence_level}.`,
    },
    elevated_break_risk: {
      label: "Elevated break-risk indication",
      detail: (v) => `Break-risk category: ${v.risk_category}; model probability ${pct(v.probability)} over the next ${v.horizon_days} days.`,
    },
    lower_break_risk: {
      label: "Lower break-risk indication",
      detail: (v) => `Break-risk category: low; model probability ${pct(v.probability)} over the next ${v.horizon_days} days.`,
    },
    calibration_overprediction: {
      label: "Historical over-prediction",
      detail: (v) =>
        v.mean_predicted != null && v.observed_rate != null
          ? `Calibration diagnostic: mean predicted ${pct(v.mean_predicted)} vs observed ${pct(v.observed_rate)} (over-prediction of ${pct(v.mean_diff ?? 0)}).`
          : "Calibration diagnostic indicates historical over-prediction.",
    },
    no_individual_interval: {
      label: "No individual prediction interval",
      detail: () => "No individual-prediction interval is available (point-probability pipeline).",
    },
  },
  ui: {
    advisory_title: "Agricultural advisory",
    language_label: "Language",
    crop_label: "Crop",
    monitoring_title: "Monitoring suggestions",
    cautions_title: "Data & evidence cautions",
    why_toggle: "Why this advisory?",
    why_model_context: (v) =>
      `Model context: logistic_regression model, prediction as-of date, probability ${pct(v.probability)}, category ${v.risk_category}. The rule engine does not modify the probability or generate intervals.`,
    disclaimer:
      "Informational advisory only. Confirm with local agricultural guidance before making high-cost decisions; local field conditions and extension advice remain essential.",
  },
  freshness: { current: "current", recent: "recent", stale: "stale" },
  evidence_level: (e) =>
    e === "positive_skill_vs_climatology_and_heuristic"
      ? "positive skill vs climatology and the dry-run heuristic"
      : e === "modest_positive_skill_vs_climatology_only"
        ? "modest positive skill vs climatology only (does not beat the simple dry-run baseline)"
        : e === "no_skill_demonstrated"
          ? "no skill demonstrated over climatology"
          : "no evaluation available",
  calibration_interpretation: (v) =>
    v.mean_diff == null
      ? "no calibration diagnostic available"
      : v.mean_diff > 0
        ? `model over-predicts event probability on average (mean predicted ${pct(v.mean_predicted ?? NaN)} vs observed ${pct(v.observed_rate ?? NaN)})`
        : `model under-predicts event probability on average (mean predicted ${pct(v.mean_predicted ?? NaN)} vs observed ${pct(v.observed_rate ?? NaN)})`,
  risk_category: { low: "low", moderate: "moderate", high: "high" },
};

export default en;
