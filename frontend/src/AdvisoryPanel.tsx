import { useEffect, useMemo, useState } from "react";
import type { Prediction } from "./api";
import { generateAdvisoryCore, ADVISORY_DISCLAIMER } from "./advisory/engine";
import { composeAdvisory, cropById } from "./advisory/crops";
import {
  LOCALE_ORDER, advisoryValues, fmtDate, fmtPercent, getPack, isLocale,
  localizedCalibration, localizedEvidence, localizedFreshness, localizedRiskCategory,
  localizedRule, localizedStatus, type LocaleCode,
} from "./advisory/locales";
import { localizedCrop } from "./advisory/locales/crops";

/** Step 19/20/21 UI: agricultural advisory for the selected location, crop, and language.
 * Presentation over the deterministic engine; no data fetching of its own. The language
 * selector re-renders localized text immediately — same prediction object, same crop ID,
 * same rule IDs; no refetch. English is the per-key fallback (never `undefined`). */

const STATUS_COLOR: Record<string, string> = {
  informational: "#2e7d32",
  caution: "#f9a825",
  limited_data: "#c62828",
};

function initialLocale(): LocaleCode {
  // deep-linkable locale (?lang=mr) for demos; then per-browser persistence; then English
  const param = new URLSearchParams(window.location.search).get("lang") ?? "";
  if (isLocale(param)) return param;
  const stored = window.localStorage?.getItem("advisory_locale") ?? "";
  return isLocale(stored) ? stored : "en";
}

export default function AdvisoryPanel({ pred }: { pred: Prediction }) {
  const [cropId, setCropId] = useState<string>("soybean");
  const [locale, setLocale] = useState<LocaleCode>(initialLocale);
  const [showWhy, setShowWhy] = useState(false);

  useEffect(() => {
    try { window.localStorage?.setItem("advisory_locale", locale); } catch { /* private mode */ }
  }, [locale]);

  const pack = getPack(locale);

  const view = useMemo(() => {
    const core = generateAdvisoryCore(pred);
    const crop = localizedCrop(locale, cropId);
    const composed = composeAdvisory(core, cropById(cropId));
    const v = advisoryValues(pred, crop.name);
    return { core, crop, composed, v };
  }, [pred, cropId, locale]);

  const { core, crop, composed, v } = view;
  const style = STATUS_COLOR[core.status];
  const riskLabel = localizedRiskCategory(locale, pred.risk_category);
  const disclaimer = locale === "en" ? ADVISORY_DISCLAIMER : pack.ui.disclaimer;

  return (
    <div className="card" data-testid="advisory-panel" lang={locale}>
      <div className="history-head">
        <h4>{pack.ui.advisory_title}</h4>
        <div className="advisory-selectors">
          <label className="muted small" htmlFor="lang-select">
            {pack.ui.language_label}:{" "}
            <select
              id="lang-select"
              data-testid="lang-select"
              value={locale}
              onChange={(e) => isLocale(e.target.value) && setLocale(e.target.value)}
            >
              {LOCALE_ORDER.map((code) => (
                <option key={code} value={code}>{getPack(code).label}</option>
              ))}
            </select>
          </label>
          <label className="muted small" htmlFor="crop-select">
            {pack.ui.crop_label}:{" "}
            <select
              id="crop-select"
              data-testid="crop-select"
              value={cropId}
              onChange={(e) => setCropId(e.target.value)}
            >
              {["soybean", "cotton", "maize", "groundnut", "pigeon_pea"].map((id) => (
                <option key={id} value={id}>{localizedCrop(locale, id).name}</option>
              ))}
              <option value="generic">{localizedCrop(locale, "generic").name}</option>
            </select>
          </label>
        </div>
      </div>

      <p className="advisory-status">
        <span className="badge" style={{ background: style }} data-testid="advisory-status">
          {localizedStatus(locale, core.status)}
        </span>
        <span className="muted small"> · {crop.name}</span>
      </p>
      <p className="advisory-headline" data-testid="advisory-headline">
        {locale === "en" ? core.headline : pack.headline[core.situation](v)}
      </p>
      <p data-testid="advisory-message">
        {locale === "en" ? composed.message : `${pack.message[core.situation](v)} ${core.situation === "elevated" ? crop.elevatedBody : crop.lowerBody}`}
      </p>

      <p className="muted small"><strong>{pack.ui.monitoring_title}:</strong></p>
      <ul className="advisory-list" data-testid="advisory-monitoring">
        {crop.monitoring.map((m, i) => <li key={i}>{m}</li>)}
      </ul>

      {composed.cautions.length > 0 && (
        <>
          <p className="muted small"><strong>{pack.ui.cautions_title}:</strong></p>
          <ul className="advisory-list warn" data-testid="advisory-cautions">
            {locale === "en"
              ? composed.cautions.map((c, i) => <li key={i}>{c}</li>)
              : cautionsFor(locale, core, v, crop.caveat).map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </>
      )}

      <p className="muted small" data-testid="advisory-disclaimer">{disclaimer}</p>

      <button className="why-toggle" data-testid="why-toggle" onClick={() => setShowWhy((s) => !s)}>
        {showWhy ? (locale === "en" ? "Hide" : pack.ui.why_toggle) : pack.ui.why_toggle}
      </button>
      {showWhy && (
        <div data-testid="why-panel">
          <ul className="advisory-list muted small">
            {core.triggers.map((t, i) => {
              const r = localizedRule(locale, t.rule, v);
              return <li key={i}><strong>{r.label}:</strong> {locale === "en" ? t.detail : r.detail}</li>;
            })}
          </ul>
          <p className="muted small">
            {locale === "en"
              ? `Model context: ${pred.model.name}, prediction as-of ${pred.prediction_date}, probability ${fmtPercent(pred.probability, locale)}, category ${pred.risk_category}. The rule engine does not modify the probability or generate intervals.`
              : `${pack.ui.why_model_context(v)} (${fmtDate(pred.prediction_date, locale)})`}
          </p>
        </div>
      )}
    </div>
  );
}

/** Localized caution lines mirror the engine's English cautions, built from the same
 * structured conditions (order preserved: data → evidence → calibration → crop caveat). */
function cautionsFor(locale: LocaleCode, core: ReturnType<typeof generateAdvisoryCore>, v: ReturnType<typeof advisoryValues>, cropCaveat: string): string[] {
  const pack = getPack(locale);
  const out: string[] = [];
  if (core.fired_rules.includes("stale_data")) {
    out.push(locale === "mr"
      ? "साठवलेला पाऊस जुना असल्याने हा अंदाज सध्याच्या शेतपरिस्थितीदर्शक असू शकत नाही; अद्ययावत स्थानिक नोंदी पाहा."
      : "चूंकि संग्रहीत वर्षा डेटा पुराना है, यह अनुमान मौजूदा खेत की स्थिति को दर्शाता असू शकता नहीं; अद्यतन स्थानीय आँकड़े देखें.");
  }
  if (core.fired_rules.includes("incomplete_input")) {
    out.push(locale === "mr"
      ? `अलीकडील पावसाच्या नोंदींमध्ये तूट असल्याने या अंदाजावरील विश्वास कमी होतो (${(v.input_completeness * 100).toFixed(0)}%).`
      : `हालिया वर्षा रिकॉर्ड में कमी होने से इस अनुमान पर विश्वास कम होता है (${(v.input_completeness * 100).toFixed(0)}%).`);
  }
  if (core.fired_rules.includes("limited_evidence")) {
    out.push(locale === "mr"
      ? "ऐतिहासिक मूल्यांकनात केवळ सरासरीपेक्षा थोडी चांगली कामगिरी दिसते; हा मॉडेल-आधारित अंदाज आहे, अवलंबिण्यायोग्य अंदाज नाही."
      : "ऐतिहासिक मूल्यांकन में केवल सामान्य से थोड़ा बेहतर प्रदर्शन दिखता है; यह मॉडल-आधारित संकेत है, भरोसेमंद पूर्वानुमान नहीं.");
  }
  if (core.fired_rules.includes("calibration_overprediction")) {
    out.push(locale === "mr"
      ? "ऐतिहासिक मूल्यांकनात मॉडेल प्रत्यक्ष घटनांपेक्षा जास्त शक्यता सांगत असल्याचे दिसते; सांगितलेली शक्यता जास्त असू शकते. ती बदललेली नाही."
      : "ऐतिहासिक मूल्यांकन में मॉडल वास्तविक घटनाओं से अधिक संभावना बताता है; दी गई संभावना अधिक हो सकती है। इसे बदला नहीं गया है.");
  }
  out.push(cropCaveat);
  return out;
}
