import type { AdvisoryValues, LocalePack } from "./types";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** हिन्दी पैक. Terminology follows common Indian agricultural usage:
 * dry spell = "शुष्क दौर / बारिश रुकना", monsoon break = "मानसून विराम", soil moisture =
 * "मिट्टी की नमी", contingency irrigation = "जहाँ संभव हो सिंचाई की तैयारी",
 * extension guidance = "कृषि विभाग / कृषि सलाहकार की मार्गदर्शन". Uncertainty is preserved:
 * "संभावना" (possibility), never "गारंटी" (guarantee). */
const hi: LocalePack = {
  code: "hi",
  label: "हिन्दी",
  status: {
    informational: "सूचनात्मक सलाह",
    caution: "सावधानी",
    limited_data: "सीमित विश्वसनीय डेटा — यह अनुमान मौजूदा स्थिति को दर्शाता असू शकता नहीं",
  },
  headline: {
    elevated: (v) => `लंबे शुष्क दौर (बारिश रुकने) की अधिक संभावना — मॉडल का अनुमान (${v.risk_category === "high" ? "अधिक" : v.risk_category === "moderate" ? "मध्यम" : "कम"})`,
    lower: () => "बारिश रुकने की कम संभावना — मॉडल का अनुमान",
  },
  message: {
    elevated: (v) =>
      `मॉडल के अनुसार ${v.location_name} क्षेत्र में आने वाले ${v.horizon_days} दिनों में शुष्क दौर (बारिश रुकने) की संभावना अधिक है। मिट्टी की नमी और स्थानीय वर्षा के आँकड़ों पर नियमित नज़र रखें। यह केवल एक संभावना है; बारिश रुकेगी ही ऐसी कोई गारंटी नहीं है।`,
    lower: (v) =>
      `मॉडल के अनुसार ${v.location_name} क्षेत्र में अभी बारिश रुकने की संभावना कम है। फिर भी स्थानीय बारिश अलग हो सकती है; नियमित निगरानी जारी रखें। यह अनुकूल मौसम की गारंटी नहीं है।`,
  },
  rules: {
    stale_data: {
      label: "पुराना डेटा",
      detail: (v) => `वर्षा का डेटा ${v.data_age_days} दिन पुराना है (पुराना/स्थगित)।`,
    },
    recent_data: {
      label: "हालिया डेटा",
      detail: (v) => `वर्षा का डेटा ${v.data_age_days} दिन का है (हालिया)।`,
    },
    current_data: {
      label: "अद्यतन डेटा",
      detail: () => "वर्षा का डेटा अद्यतन है (0–2 दिन)।",
    },
    incomplete_input: {
      label: "अपूर्ण वर्षा आँकड़े",
      detail: (v) => `आँकड़ों की पूर्णता ${(v.input_completeness * 100).toFixed(0)}% है (हालिया वर्षा के रिकॉर्ड में कमी है)।`,
    },
    limited_evidence: {
      label: "सीमित मूल्यांकन प्रमाण",
      detail: (v) => `प्रमाण का स्तर: ${v.evidence_level}.`,
    },
    elevated_break_risk: {
      label: "अधिक शुष्क दौर की संभावना",
      detail: (v) => `श्रेणी: ${v.risk_category === "high" ? "अधिक" : v.risk_category === "moderate" ? "मध्यम" : "कम"}; अगले ${v.horizon_days} दिनों के लिए मॉडल की संभावना ${pct(v.probability)}।`,
    },
    lower_break_risk: {
      label: "कम शुष्क दौर की संभावना",
      detail: (v) => `श्रेणी: कम; अगले ${v.horizon_days} दिनों के लिए मॉडल की संभावना ${pct(v.probability)}।`,
    },
    calibration_overprediction: {
      label: "ऐतिहासिक अधिक अनुमान",
      detail: (v) =>
        v.mean_predicted != null && v.observed_rate != null
          ? `कैलिब्रेशन निरीक्षण: औसत अनुमान ${pct(v.mean_predicted)} बनाम वास्तविक ${pct(v.observed_rate)} (अधिक अनुमान ${pct(v.mean_diff ?? 0)})।`
          : "कैलिब्रेशन निरीक्षण के अनुसार ऐतिहासिक रूप से अधिक अनुमान लगाए गए हैं।",
    },
    no_individual_interval: {
      label: "व्यक्तिगत अनुमान-अंतराल उपलब्ध नहीं",
      detail: () => "व्यक्तिगत अनुमान-अंतराल उपलब्ध नहीं (मॉडल केवल एक संभावना देता है)।",
    },
  },
  ui: {
    advisory_title: "कृषि सलाह",
    language_label: "भाषा",
    crop_label: "फसल",
    monitoring_title: "निगरानी सुझाव",
    cautions_title: "डेटा व प्रमाण संबंधी सावधानियाँ",
    why_toggle: "यह सलाह क्यों?",
    why_model_context: (v) =>
      `मॉडल: logistic_regression, अनुमान की तिथि, संभावना ${pct(v.probability)}, श्रेणी ${v.risk_category === "high" ? "अधिक" : v.risk_category === "moderate" ? "मध्यम" : "कम"}। नियम-इंजन संभावना को बदलता नहीं और अंतराल नहीं बनाता।`,
    disclaimer:
      "यह केवल सूचनात्मक सलाह है। बड़े खर्च वाले निर्णय लेने से पहले स्थानीय कृषि मार्गदर्शन अवश्य जाँचें; स्थानीय खेत की स्थिति और कृषि विभाग की सलाह आवश्यक है।",
  },
  freshness: { current: "अद्यतन", recent: "हालिया", stale: "पुराना" },
  evidence_level: (e) =>
    e === "positive_skill_vs_climatology_and_heuristic"
      ? "सामान्य (क्लाइमेटोलॉजी) और सरल नियम दोनों से बेहतर प्रदर्शन"
      : e === "modest_positive_skill_vs_climatology_only"
        ? "सामान्य (क्लाइमेटोलॉजी) से केवल थोड़ा बेहतर — सरल नमी-नियम से बेहतर नहीं"
        : e === "no_skill_demonstrated"
          ? "सामान्य से विशेष कौशल नहीं दिखा"
          : "मूल्यांकन उपलब्ध नहीं",
  calibration_interpretation: (v) =>
    v.mean_diff == null
      ? "कैलिब्रेशन जानकारी उपलब्ध नहीं"
      : v.mean_diff > 0
        ? `मॉडल औसतन अधिक अनुमान देता है (अनुमान ${pct(v.mean_predicted ?? NaN)} बनाम वास्तविक ${pct(v.observed_rate ?? NaN)})`
        : `मॉडल औसतन कम अनुमान देता है (अनुमान ${pct(v.mean_predicted ?? NaN)} बनाम वास्तविक ${pct(v.observed_rate ?? NaN)})`,
  risk_category: { low: "कम", moderate: "मध्यम", high: "अधिक" },
};

export default hi;
