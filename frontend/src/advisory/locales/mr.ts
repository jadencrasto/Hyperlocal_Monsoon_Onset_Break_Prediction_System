import type { AdvisoryValues, LocalePack } from "./types";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** मराठी पॅक. Terminology follows common Maharashtra agricultural usage:
 * dry spell = "कोरडा पट्टा / पाऊस थांबणे", monsoon break = "मान्सून स्थगित", soil moisture
 * = "मातीतील ओलावा", contingency irrigation = "आवश्यक तेथे पाणी पुरवठ्याची तयारी",
 * extension guidance = "कृषी विभागाचे / तालुका कृषी अधिकाऱ्यांचे मार्गदर्शन". Uncertainty
 * wording is preserved: "शक्यता" (possibility), never a guarantee ("हमी"). */
const mr: LocalePack = {
  code: "mr",
  label: "मराठी",
  status: {
    informational: "माहितीपर सल्ला",
    caution: "सावधानता",
    limited_data: "मर्यादित विश्वसनीय डेटा — हा अंदाज सध्याच्या परिस्थितीदर्शक असू शकत नाही",
  },
  headline: {
    elevated: (v) => `कोरड्या हवामानाची (लगेच पाऊस थांबण्याची) जास्त शक्यता — मॉडेलचा अंदाज (${v.risk_category === "high" ? "जास्त" : v.risk_category === "moderate" ? "मध्यम" : "कमी"})`,
    lower: () => "लगेच पाऊस थांबण्याची कमी शक्यता — मॉडेलचा अंदाज",
  },
  message: {
    elevated: (v) =>
      `मॉडेलनुसार ${v.location_name} परिसरात येत्या ${v.horizon_days} दिवसांत कोरडा काळ (पाऊस थांबण्याची शक्यता) जास्त आहे. मातीतील ओलावा आणि स्थानिक पावसाच्या नोंदी नियमित पाहा. ही फक्त शक्यता आहे; पाऊस नक्की थांबेल असे हमीखोरपणे म्हणता येत नाही.`,
    lower: (v) =>
      `मॉडेलनुसार ${v.location_name} परिसरात लगेच पाऊस थांबण्याची शक्यता सध्या कमी आहे. मात्र स्थानिक पाऊस वेगळा असू शकतो; नियमित पाहणी सुरू ठेवा. हे अनुकूल हवामानाचे हमीखोर अंदाज नाही.`,
  },
  rules: {
    stale_data: {
      label: "जुना (स्थगित) डेटा",
      detail: (v) => `पावसाची डेटा ${v.data_age_days} दिवस जुना आहे (स्थगित).`,
    },
    recent_data: {
      label: "अलीकडील डेटा",
      detail: (v) => `पावसाचा डेटा ${v.data_age_days} दिवसाचा आहे (अलीकडील).`,
    },
    current_data: {
      label: "अद्ययावत डेटा",
      detail: () => "पावसाचा डेटा अद्ययावत आहे (0–2 दिवस).",
    },
    incomplete_input: {
      label: "अपूर्ण पावसाची माहिती",
      detail: (v) => `माहिती पूर्णता ${(v.input_completeness * 100).toFixed(0)}% आहे (अलीकडील पावसाच्या नोंदींमध्ये तूट आहे).`,
    },
    limited_evidence: {
      label: "मर्यादित मूल्यांकन पुरावा",
      detail: (v) => `पुराव्याची पातळी: ${v.evidence_level}.`,
    },
    elevated_break_risk: {
      label: "जास्त कोरड्या काळाची शक्यता",
      detail: (v) => `श्रेणी: ${v.risk_category === "high" ? "जास्त" : v.risk_category === "moderate" ? "मध्यम" : "कमी"}; पुढील ${v.horizon_days} दिवसांसाठी मॉडेलची शक्यता ${pct(v.probability)}.`,
    },
    lower_break_risk: {
      label: "कमी कोरड्या काळाची शक्यता",
      detail: (v) => `श्रेणी: कमी; पुढील ${v.horizon_days} दिवसांसाठी मॉडेलची शक्यता ${pct(v.probability)}.`,
    },
    calibration_overprediction: {
      label: "ऐतिहासिक जास्त अंदाज",
      detail: (v) =>
        v.mean_predicted != null && v.observed_rate != null
          ? `कॅलिब्रेशन निरीक्षण: सरासरी अंदाज ${pct(v.mean_predicted)} विरुद्ध प्रत्यक्ष ${pct(v.observed_rate)} (जास्त अंदाज ${pct(v.mean_diff ?? 0)}).`
          : "कॅलिब्रेशन निरीक्षणानुसार ऐतिहासिकदृष्ट्या जास्त अंदाज होतात.",
    },
    no_individual_interval: {
      label: "वैयक्तिक अंदाज-अंतराल उपलब्ध नाही",
      detail: () => "वैयक्तिक अंदाज-अंतराल उपलब्ध नाही (मॉडेल फक्त एक शक्यता देते).",
    },
  },
  ui: {
    advisory_title: "कृषी सल्ला",
    language_label: "भाषा",
    crop_label: "पीक",
    monitoring_title: "निरीक्षण सूचना",
    cautions_title: "डेटा व पुराव्यासंबंधी सावधानता",
    why_toggle: "हा सल्ला का?",
    why_model_context: (v) =>
      `मॉडेल: logistic_regression, अंदाजाची तारीख, शक्यता ${pct(v.probability)}, श्रेणी ${v.risk_category === "high" ? "जास्त" : v.risk_category === "moderate" ? "मध्यम" : "कमी"}. नियम इंजिन शक्यता बदलत नाही आणि अंतराल तयार करत नाही.`,
    disclaimer:
      "हा फक्त माहितीपर सल्ला आहे. मोठ्या खर्चाचे निर्णय घेण्यापूर्वी स्थानिक कृषी मार्गदर्शन नक्की करा; स्थानिक शेतपरिस्थिती व कृषी विभागाचे मार्गदर्शन आवश्यक आहे.",
  },
  freshness: { current: "अद्ययावत", recent: "अलीकडील", stale: "जुना" },
  evidence_level: (e) =>
    e === "positive_skill_vs_climatology_and_heuristic"
      ? "सरासरीपेक्षा व सोप्या नियमापेक्षा चांगली कामगिरी"
      : e === "modest_positive_skill_vs_climatology_only"
        ? "सरासरी (क्लायमेटॉलॉजी) पेक्षा थोडी चांगली कामगिरी — सोपा ओलावा-नियम पेक्षा चांगला नाही"
        : e === "no_skill_demonstrated"
          ? "सरासरीपेक्षा विशेष कौशल्य दिसत नाही"
          : "मूल्यांकन उपलब्ध नाही",
  calibration_interpretation: (v) =>
    v.mean_diff == null
      ? "कॅलिब्रेशन माहिती उपलब्ध नाही"
      : v.mean_diff > 0
        ? `मॉडेल सरासरी जास्त अंदाज देते (अंदाज ${pct(v.mean_predicted ?? NaN)} विरुद्ध प्रत्यक्ष ${pct(v.observed_rate ?? NaN)})`
        : `मॉडेल सरासरी कमी अंदाज देते (अंदाज ${pct(v.mean_predicted ?? NaN)} विरुद्ध प्रत्यक्ष ${pct(v.observed_rate ?? NaN)})`,
  risk_category: { low: "कमी", moderate: "मध्यम", high: "जास्त" },
};

export default mr;
