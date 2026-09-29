import type { Prediction } from "../../api";
import type { AdvisoryCore, AdvisoryStatus } from "../engine";
import type { AdvisoryValues, LocaleCode, LocalePack } from "./types";
import en from "./en";
import mr from "./mr";
import hi from "./hi";

export type { LocaleCode, LocalePack, AdvisoryValues, LocalizedCropTemplate } from "./types";

/** Locale registry. Adding a language = one new LocalePack file + one entry here.
 * The advisory engine, rules, and crop IDs never change. */
export const LOCALES: Record<LocaleCode, LocalePack> = { en, mr, hi };
export const LOCALE_ORDER: LocaleCode[] = ["en", "mr", "hi"];

export function isLocale(x: string): x is LocaleCode {
  return x in LOCALES;
}

/** Per-key English fallback: try the selected locale, else English for that exact key. */
export function getPack(locale: LocaleCode): LocalePack {
  return LOCALES[locale] ?? en;
}

/** Build the structured values snapshot (raw numbers; formatting at render time). */
export function advisoryValues(pred: Prediction, cropName: string): AdvisoryValues {
  const u = (pred.uncertainty ?? {}) as Record<string, any>;
  const stab = (u.per_year_stability ?? {}) as Record<string, any>;
  const cal = (u.calibration ?? {}) as Record<string, any>;
  return {
    probability: pred.probability,
    risk_category: pred.risk_category,
    horizon_days: pred.horizon_days,
    location_name: pred.location.name,
    data_age_days: pred.data_status.data_age_days,
    input_completeness: pred.data_status.input_completeness,
    freshness: pred.data_status.freshness,
    mean_predicted: cal.mean_predicted ?? null,
    observed_rate: cal.observed_rate ?? null,
    mean_diff: cal.mean_diff ?? null,
    evidence_level: String(u.evidence_level ?? "no_evaluation_available"),
    crop_name: cropName,
    n_stability_years: stab.n_years ?? null,
    bss_min: stab.bss_min ?? null,
    bss_max: stab.bss_max ?? null,
  };
}

/** Resolve a rule trigger into a localized {label, detail}. Falls back to English per key,
 * then to a safe generic line — never `undefined`, never a bare internal rule ID. */
export function localizedRule(locale: LocaleCode, rule: string, v: AdvisoryValues): { label: string; detail: string } {
  const pack = getPack(locale);
  const entry = pack.rules[rule] ?? en.rules[rule];
  if (!entry) return { label: rule, detail: "" };
  return { label: entry.label, detail: entry.detail(v) };
}

export function localizedStatus(locale: LocaleCode, status: AdvisoryStatus): string {
  return getPack(locale).status[status] ?? en.status[status] ?? status;
}

export function localizedRiskCategory(locale: LocaleCode, cat: "low" | "moderate" | "high"): string {
  return getPack(locale).risk_category[cat] ?? en.risk_category[cat] ?? cat;
}

export function localizedFreshness(locale: LocaleCode, f: "current" | "recent" | "stale"): string {
  return getPack(locale).freshness[f] ?? en.freshness[f] ?? f;
}

export function localizedEvidence(locale: LocaleCode, evidence: string, v: AdvisoryValues): string {
  return (getPack(locale).evidence_level ?? en.evidence_level)(evidence, v);
}

export function localizedCalibration(locale: LocaleCode, v: AdvisoryValues): string {
  return (getPack(locale).calibration_interpretation ?? en.calibration_interpretation)(v);
}

// ---- locale-aware formatting (presentation layer only; values stay raw) -------------

export function fmtPercent(v: number, locale: LocaleCode = "en"): string {
  return new Intl.NumberFormat(localeTag(locale), { style: "percent", maximumFractionDigits: 1 }).format(v);
}

export function fmtNumber(v: number, locale: LocaleCode = "en", digits = 3): string {
  return new Intl.NumberFormat(localeTag(locale), { maximumFractionDigits: digits }).format(v);
}

export function fmtDate(iso: string, locale: LocaleCode = "en"): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : new Intl.DateTimeFormat(localeTag(locale), { dateStyle: "medium" }).format(d);
}

function localeTag(locale: LocaleCode): string {
  return locale === "mr" ? "mr-IN" : locale === "hi" ? "hi-IN" : "en-IN";
}
