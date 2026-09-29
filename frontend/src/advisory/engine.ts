import type { Prediction } from "../api";

/** Step 19 — advisory/rule engine.
 *
 * Deterministic, transparent rules over the Step 14 prediction response. This is NOT a
 * model: it never alters the probability, never recalibrates, and never invents intervals.
 * It decides WHAT situation the system detects and how cautious the wording must be;
 * Step 20 crop templates decide HOW that is phrased per crop.
 *
 * Every rule records why it fired, so the UI can show an auditable
 * "Why this advisory?" section built only from real prediction fields. */

export type AdvisoryStatus = "informational" | "caution" | "limited_data";

export interface RuleTrigger {
  rule: string;      // stable rule id, e.g. "stale_data"
  detail: string;    // human-readable, built from actual prediction fields
}

export interface AdvisoryCore {
  status: AdvisoryStatus;
  /** Situation detected by the rules, crop-neutral (Step 19 owns this wording). */
  headline: string;
  /** Informational body text; conservative when data/evidence/calibration warrant it. */
  message: string;
  /** Caution lines that must stay visible regardless of crop template. */
  cautions: string[];
  /** Ordered trigger log = the "Why this advisory?" payload. */
  triggers: RuleTrigger[];
  /** Step 21 (additive): structured situation + raw values for locale-aware rendering.
   * The English strings above remain the source of truth for en; locale packs key off
   * situation/rule IDs and format these values at render time. */
  situation: "elevated" | "lower";
  fired_rules: string[];
  values: {
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
  };
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

const CALIBRATION_OVERPREDICTION_THRESHOLD = 0.03;
/** Step 9/11 documented |mean_diff| of 0.028-0.061; ~0.03 keeps the caution meaningful
 * without firing on negligible diagnostic noise. Not a probability correction. */

export function generateAdvisoryCore(pred: Prediction): AdvisoryCore {
  const u = (pred.uncertainty ?? {}) as Record<string, any>;
  const ds = pred.data_status;
  const triggers: RuleTrigger[] = [];
  const cautions: string[] = [];
  let status: AdvisoryStatus = "informational";

  const bump = (to: AdvisoryStatus) => {
    const rank = { informational: 0, caution: 1, limited_data: 2 } as const;
    if (rank[to] > rank[status]) status = to;
  };

  // ---- Rule A — stale data (takes precedence in wording strength) -------------------
  if (ds.freshness === "stale") {
    bump("limited_data");
    triggers.push({ rule: "stale_data", detail: `Rainfall data is ${ds.data_age_days} days old (freshness: stale).` });
    cautions.push(
      "The indication may not reflect current field conditions because the stored rainfall is stale; check updated local observations."
    );
  } else if (ds.freshness === "recent") {
    triggers.push({ rule: "recent_data", detail: `Rainfall data is ${ds.data_age_days} day(s) old (freshness: recent).` });
  } else {
    triggers.push({ rule: "current_data", detail: "Rainfall data is current (age 0-2 days)." });
  }

  // ---- Rule B — incomplete input ----------------------------------------------------
  if (ds.input_completeness < 1) {
    bump("caution");
    triggers.push({
      rule: "incomplete_input",
      detail: `Input completeness is ${(ds.input_completeness * 100).toFixed(0)}% (recent rainfall contains gaps).`,
    });
    cautions.push("Recent rainfall inputs contain gaps, which lowers confidence in the indication.");
  }

  // ---- Rule C — limited evidence ----------------------------------------------------
  const evidence = String(u.evidence_level ?? "no_evaluation_available");
  const limitedEvidence = evidence !== "positive_skill_vs_climatology_and_heuristic";
  if (limitedEvidence) {
    bump("caution");
    triggers.push({ rule: "limited_evidence", detail: `Evidence level: ${evidence}.` });
    cautions.push(
      "Historical evaluation shows modest skill over climatology only; treat this as a model-based indication, not a dependable forecast."
    );
  }

  // ---- Rule F — calibration over-prediction (checked before D/E wording) ------------
  const meanDiff = u.calibration?.mean_diff;
  const overPredicts = typeof meanDiff === "number" && meanDiff > CALIBRATION_OVERPREDICTION_THRESHOLD;
  if (overPredicts) {
    bump("caution");
    triggers.push({
      rule: "calibration_overprediction",
      detail:
        typeof u.calibration?.mean_predicted === "number" && typeof u.calibration?.observed_rate === "number"
          ? `Calibration diagnostic: mean predicted ${pct(u.calibration.mean_predicted)} vs observed ${pct(u.calibration.observed_rate)} (over-prediction of ${pct(meanDiff)}).`
          : `Calibration diagnostic indicates historical over-prediction (${pct(meanDiff)}).`,
    });
    cautions.push(
      "Historical evaluation shows the model tends to predict higher probabilities than the observed event frequency; the stated probability may be on the high side. It has not been adjusted."
    );
  }

  // ---- Rules D / E — the break-risk indication itself --------------------------------
  const elevated = pred.risk_category !== "low";
  if (elevated) {
    triggers.push({
      rule: "elevated_break_risk",
      detail: `Break-risk category: ${pred.risk_category}; model probability ${pct(pred.probability)} over the next ${pred.horizon_days} days.`,
    });
  } else {
    triggers.push({
      rule: "lower_break_risk",
      detail: `Break-risk category: low; model probability ${pct(pred.probability)} over the next ${pred.horizon_days} days.`,
    });
  }

  // ---- Rule G — individual prediction interval (never presented as one) -------------
  const ipi = u.individual_prediction_interval;
  if (!ipi?.available) {
    triggers.push({
      rule: "no_individual_interval",
      detail: "No individual-prediction interval is available (point-probability pipeline).",
    });
  }

  const headline = elevated
    ? `Model-based indication of elevated dry-spell risk (${pred.risk_category})`
    : "Model-based indication of lower dry-spell risk";

  const message = elevated
    ? `The model indicates an elevated possibility of a dry spell or break phase around ${pred.location.name} in the coming ${pred.horizon_days} days. Consider monitoring soil moisture and local rainfall observations. This indication is not a guarantee that a break will occur.`
    : `The model currently shows a lower break-risk indication around ${pred.location.name}. Local rainfall can still differ from the model's input data; continue routine monitoring. This indication is not a guarantee of favorable conditions.`;

  return {
    status, headline, message, cautions, triggers,
    situation: elevated ? "elevated" : "lower",
    fired_rules: triggers.map((t) => t.rule),
    values: {
      probability: pred.probability,
      risk_category: pred.risk_category,
      horizon_days: pred.horizon_days,
      location_name: pred.location.name,
      data_age_days: ds.data_age_days,
      input_completeness: ds.input_completeness,
      freshness: ds.freshness,
      mean_predicted: typeof u.calibration?.mean_predicted === "number" ? u.calibration.mean_predicted : null,
      observed_rate: typeof u.calibration?.observed_rate === "number" ? u.calibration.observed_rate : null,
      mean_diff: typeof meanDiff === "number" ? meanDiff : null,
      evidence_level: evidence,
    },
  };
}

/** Shared closing caution rendered with every advisory (crop templates may add more). */
export const ADVISORY_DISCLAIMER =
  "Informational advisory only. Confirm with local agricultural guidance before making high-cost decisions; local field conditions and extension advice remain essential.";
