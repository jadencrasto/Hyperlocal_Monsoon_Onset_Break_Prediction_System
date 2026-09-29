import type { LocaleCode, LocalizedCropTemplate } from "./types";

/** Localized crop templates, keyed by the unchanged Step 20 crop IDs.
 * English mirrors Step 20's texts; mr/hi are farmer-appropriate translations.
 * Terminology: flowering = फुल येणे / फूल आना, pod filling = शेंगा भरणे / फली भरने,
 * pegging (groundnut) = बिड़वणी / गांठ जकड़न. Agronomy stays informational — no doses,
 * no dates, no chemical schedules (same rule as Step 20, enforced by tests). */

const en: Record<string, LocalizedCropTemplate> = {
  soybean: {
    id: "soybean", name: "Soybean",
    context: "Kharif pulse/oilseed; sensitive to moisture stress during flowering and pod filling.",
    elevatedBody: "A dry spell during flowering or pod fill can stress the crop; review soil moisture and prepare contingency irrigation arrangements where available.",
    lowerBody: "With a lower break-risk indication, routine monitoring of crop stage and soil moisture is reasonable.",
    monitoring: [
      "Monitor soil moisture at pod-setting depth where practical.",
      "Watch for moisture stress signs during flowering and pod filling.",
      "Review local rainfall observations against this indication.",
    ],
    caveat: "Crop water needs vary by soil type and sowing time; local extension guidance should confirm any field action.",
  },
  cotton: {
    id: "cotton", name: "Cotton",
    context: "Long-duration kharif fiber crop; deep-rooted but squaring/boll stages are moisture-sensitive.",
    elevatedBody: "A break phase during squaring or boll development can add stress; monitoring and having contingency irrigation ready is a reasonable precaution.",
    lowerBody: "With a lower break-risk indication, continue routine crop monitoring through squaring and boll stages.",
    monitoring: [
      "Monitor soil moisture during squaring and boll development.",
      "Track local rainfall observations for the coming weeks.",
      "Review field conditions before committing to any intervention.",
    ],
    caveat: "Cotton's deep roots can buffer short dry spells; agronomist/extension input should guide any decision.",
  },
  maize: {
    id: "maize", name: "Maize",
    context: "Kharif cereal; tasseling/silking is the most moisture-sensitive stage.",
    elevatedBody: "A dry spell around tasseling or silking can affect grain set; review soil moisture and local observations during those stages.",
    lowerBody: "With a lower break-risk indication, routine monitoring through vegetative and reproductive stages is reasonable.",
    monitoring: [
      "Watch tasseling/silking stages closely if they coincide with the indication window.",
      "Monitor soil moisture and local rainfall observations.",
      "Keep contingency options reviewed with local extension guidance.",
    ],
    caveat: "Water needs vary strongly by growth stage and hybrid; confirm actions locally.",
  },
  groundnut: {
    id: "groundnut", name: "Groundnut",
    context: "Kharif oilseed; pod development needs consistent moisture.",
    elevatedBody: "A dry spell during pod development can affect yields; monitoring soil moisture and preparing contingency irrigation where available is a reasonable precaution.",
    lowerBody: "With a lower break-risk indication, continue routine monitoring through pegging and pod development.",
    monitoring: [
      "Monitor soil moisture during pegging and pod development.",
      "Review local rainfall observations for the indication window.",
      "Discuss contingency options with local extension guidance.",
    ],
    caveat: "Pod-zone moisture differs from surface readings; local verification is important.",
  },
  pigeon_pea: {
    id: "pigeon_pea", name: "Pigeon pea (Tur)",
    context: "Long-duration kharif pulse; deep-rooted, but flowering/pod fill benefit from steady moisture.",
    elevatedBody: "An extended break during flowering or pod fill can stress the crop; monitoring and contingency planning are reasonable precautions.",
    lowerBody: "With a lower break-risk indication, routine monitoring through flowering and pod fill is reasonable.",
    monitoring: [
      "Monitor crop stage relative to the indication window.",
      "Review local rainfall observations and soil moisture.",
      "Consider extension guidance before any field intervention.",
    ],
    caveat: "Deep rooting provides some drought buffering; local agronomic judgment should lead.",
  },
  generic: {
    id: "generic", name: "General cropping",
    context: "General kharif cropping guidance (no specific crop selected).",
    elevatedBody: "A dry spell or break phase may stress standing kharif crops; review soil moisture and local rainfall observations, and prepare contingency irrigation arrangements where available.",
    lowerBody: "With a lower break-risk indication, routine monitoring of crop stage and soil moisture is reasonable.",
    monitoring: [
      "Monitor soil moisture and local rainfall observations.",
      "Review field conditions before any intervention.",
    ],
    caveat: "Crop-specific needs vary widely; local agricultural-extension guidance should confirm any action.",
  },
};

const mr: Record<string, LocalizedCropTemplate> = {
  soybean: {
    id: "soybean", name: "सोयाबीन",
    context: "खरीप भाजीव/तेलबिया; फुल येणे व शेंगा भरण्याच्या काळात ओलाव्याच्या टंचाईला संवेदनशील.",
    elevatedBody: "फुल येणे किंवा शेंगा भरण्याच्या काळात कोरडा काळ आल्यास पीक तणावग्रस्त होऊ शकते; मातीतील ओलावा पाहा आणि जिथे शक्य असेल तेथे पाणी पुरवठ्याची तयारी ठेवा.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना पीक-अवस्था व मातीतील ओलावा नियमित पाहणे योग्य.",
    monitoring: [
      "शेंगा धरण्याच्या खोलीतील ओलावा शक्य असेल तेथे पाहा.",
      "फुल येणे व शेंगा भरण्याच्या काळात ओलाव्याच्या कमतरतेची लक्षणे पाहा.",
      "स्थानिक पावसाच्या नोंदींशी या अंदाजाची तुलना करा.",
    ],
    caveat: "मातीचा प्रकार व पेरणीचा काळ यानुसार पिकाची पाण्याची गरज बदलते; कोणतेही शेत-कृत्य करण्यापूर्वी स्थानिक कृषी मार्गदर्शन घ्या.",
  },
  cotton: {
    id: "cotton", name: "कापूस",
    context: "दीर्घकाळ टिकणारे खरीप तंतुवर्धु पीक; गादी/कोष वाढण्याच्या काळात ओलाव्यासाठी संवेदनशील.",
    elevatedBody: "गादी काढणे किंवा कोष वाढीच्या काळात मान्सून स्थगित गेल्यास ताण वाढू शकतो; निरीक्षण ठेवणे व आवश्यक तेथे सिंचनाची तयारी ठेवणे योग्य खबरदारी.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना गादी व कोष वाढीच्या काळात नियमित पाहणी सुरू ठेवा.",
    monitoring: [
      "गादी व कोष वाढीच्या काळात मातीतील ओलावा पाहा.",
      "येत्या आठवड्यांसाठी स्थानिक पावसाच्या नोंदी बघत रहा.",
      "कोणतेही हस्तक्षेप करण्यापूर्वी शेतातील परिस्थिती तपासा.",
    ],
    caveat: "कापसाची खोल घुशी छोट्या कोरड्या काळाला तोंड देऊ शकते; निर्णयासाठी कृषी तज्ज्ञ/विभागीय मार्गदर्शन घ्या.",
  },
  maize: {
    id: "maize", name: "मका",
    context: "खरीप धान्य; फुलोरा/सिल्क येण्याचा काळ सर्वाधिक ओलावा-संवेदनशील.",
    elevatedBody: "फुलोरा किंवा सिल्क येण्याच्या काळात कोरडा काळ आल्यास धान्य धरणे कमी होऊ शकते; त्या अवस्थेत मातीतील ओलावा व स्थानिक नोंदी पाहा.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना वाढ व प्रजनन अवस्थेत नियमित पाहणी योग्य.",
    monitoring: [
      "अंदाजाच्या कालावधीशी जुळल्यास फुलोरा/सिल्क अवस्था जवळून बघा.",
      "मातीतील ओलावा व स्थानिक पावसाच्या नोंदी पाहत रहा.",
      "तात्पुरत्या पर्यायांचे नियोजन स्थानिक कृषी मार्गदर्शनासह करा.",
    ],
    caveat: "वाढ-अवस्था व जातीनुसार पाण्याची गरज बदलते; कृत्ये स्थानिक पातळीवर खात्री करा.",
  },
  groundnut: {
    id: "groundnut", name: "भुईमूग",
    context: "खरीप तेलबिया; शेंगा वाढीसाठी सातत्याने ओलावा आवश्यक.",
    elevatedBody: "शेंगा वाढीच्या काळात कोरडा काळ आल्यास उत्पादनावर परिणाम होऊ शकतो; मातीतील ओलावा पाहणे व जिथे शक्य असेल तेथे सिंचनाची तयारी योग्य खबरदारी.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना बिड़वणी व शेंगा वाढीच्या काळात नियमित पाहणी सुरू ठेवा.",
    monitoring: [
      "बिड़वणी व शेंगा वाढीच्या काळात मातीतील ओलावा पाहा.",
      "अंदाजाच्या कालावधीसाठी स्थानिक पावसाच्या नोंदी पाहा.",
      "तात्पुरत्या पर्यायांबाबत स्थानिक कृषी मार्गदर्शनाशी चर्चा करा.",
    ],
    caveat: "शेंगा-क्षेत्रातील ओलावा वरवरच्या नोंदीपेक्षा वेगळा असतो; स्थानिक तपासणी महत्त्वाची.",
  },
  pigeon_pea: {
    id: "pigeon_pea", name: "हरभरा (तूर)",
    context: "दीर्घकाळ टिकणारे खरीप भाजीव; खोल घुशी असले तरी फुले/शेंगा भरण्यास सातत्याने ओलावा लाभदायक.",
    elevatedBody: "फुले किंवा शेंगा भरण्याच्या काळात पाऊस बराच वेळ थांबल्यास पीक तणावग्रस्त होऊ शकते; निरीक्षण व नियोजन ही योग्य खबरदारी.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना फुले व शेंगा भरण्याच्या काळात नियमित पाहणी योग्य.",
    monitoring: [
      "अंदाजाच्या कालावधीशी पीक-अवस्था जुळवून पाहा.",
      "स्थानिक पावसाच्या नोंदी व मातीतील ओलावा पाहा.",
      "कोणतेही शेत-कृत्य करण्यापूर्वी कृषी मार्गदर्शन विचारात घ्या.",
    ],
    caveat: "खोल घुशीमुळे काही प्रमाणात दुष्काळ सहन होतो; स्थानिक शेती-निर्णयाला प्राधान्य द्या.",
  },
  generic: {
    id: "generic", name: "सामान्य पीक मार्गदर्शन",
    context: "सामान्य खरीप पीक मार्गदर्शन (विशिष्ट पीक निवडलेले नाही).",
    elevatedBody: "कोरडा काळ किंवा मान्सून स्थगितीमुळे उभ्या खरीप पिकांवर ताण येऊ शकतो; मातीतील ओलावा व स्थानिक पावसाच्या नोंदी पाहा आणि जिथे शक्य असेल तेथे सिंचनाची तयारी ठेवा.",
    lowerBody: "कोरड्या काळाची कमी शक्यता असताना पीक-अवस्था व ओलाव्याचे नियमित निरीक्षण योग्य.",
    monitoring: [
      "मातीतील ओलावा व स्थानिक पावसाच्या नोंदी पाहा.",
      "कोणतेही कृत्य करण्यापूर्वी शेतातील परिस्थिती तपासा.",
    ],
    caveat: "पिकानुसार गरजा बदलतात; कृत्यांची खात्री स्थानिक कृषी विभागाच्या मार्गदर्शनातून करा.",
  },
};

const hi: Record<string, LocalizedCropTemplate> = {
  soybean: {
    id: "soybean", name: "सोयाबीन",
    context: "खरीफ दालहन/तिलहन; फूल आने और फली भरने के दौरान नमी की कमी के प्रति संवेदनशील.",
    elevatedBody: "फूल आने या फली भरने के दौरान शुष्क दौर आने पर फसल पर तनाव बढ़ सकता है; मिट्टी की नमी देखें और जहाँ संभव हो सिंचाई की तैयारी रखें.",
    lowerBody: "शुष्क दौर की कम संभावना के समय फसल अवस्था और मिट्टी की नमी की नियमित निगरानी उचित है.",
    monitoring: [
      "जहाँ संभव हो, फली बनने की गहराई पर मिट्टी की नमी देखें।",
      "फूल आने और फली भरने के दौरान नमी की कमी के लक्षण देखें।",
      "स्थानीय वर्षा के आँकड़ों से इस अनुमान की तुलना करें।",
    ],
    caveat: "मिट्टी के प्रकार और बुवाई के समय के अनुसार पानी की ज़रूरत बदलती है; कोई भी खेत-क्रिया करने से पहले स्थानीय कृषि मार्गदर्शन लें.",
  },
  cotton: {
    id: "cotton", name: "कपास",
    context: "लंबी अवधि की खरीफ रेशा फसल; गांठें/गोले बनने के दौर में नमी के प्रति संवेदनशील.",
    elevatedBody: "गांठें या गोले बनने के दौर में मानसून विराम आने पर तनाव बढ़ सकता है; निगरानी रखना और जहाँ संभव हो सिंचाई की तैयारी रखना उचित सावधानी है.",
    lowerBody: "शुष्क दौर की कम संभावना के समय गांठ और गोला अवस्था में नियमित निगरानी जारी रखें.",
    monitoring: [
      "गांठें और गोले बनने के दौर में मिट्टी की नमी देखें।",
      "आने वाले हफ्तों के लिए स्थानीय वर्षा के आँकड़े देखते रहें।",
      "किसी भी हस्तक्षेप से पहले खेत की स्थिति की समीक्षा करें।",
    ],
    caveat: "कपास की गहरी जड़ें छोटे शुष्क दौर को झेल सकती हैं; निर्णय हेतु कृषि विशेषज्ञ/विभाग की सलाह लें.",
  },
  maize: {
    id: "maize", name: "मक्का",
    context: "खरीफ अनाज; गुट्ठा/रेशेदार धागा (silking) अवस्था सबसे नमी-संवेदनशील है.",
    elevatedBody: "गुट्ठा निकलने या रेशेदार धागे के समय शुष्क दौर आने पर दाना बनना प्रभावित हो सकता है; उन अवस्थाओं में मिट्टी की नमी और स्थानीय आँकड़े देखें.",
    lowerBody: "शुष्क दौर की कम संभावना के समय वाढ और उत्पादन अवस्थाओं में नियमित निगरानी उचित है.",
    monitoring: [
      "अनुमान की अवधि से मेल खाए तो गुट्ठा/रेशा अवस्था पर विशेष ध्यान दें।",
      "मिट्टी की नमी और स्थानीय वर्षा के आँकड़े देखते रहें।",
      "आकस्मिक विकल्पों की समीक्षा स्थानीय कृषि मार्गदर्शन के साथ करें।",
    ],
    caveat: "वाढ़ अवस्था और किस्म के अनुसार पानी की ज़रूरत बदलती है; कार्य स्थानीय स्तर पर पुष्ट करें।",
  },
  groundnut: {
    id: "groundnut", name: "मूंगफली",
    context: "खरीफ तिलहन; फली विकास के लिए लगातार नमी आवश्यक.",
    elevatedBody: "फली विकास के दौरान शुष्क दौर उपज को प्रभावित कर सकता है; मिट्टी की नमी पर निगरानी और जहाँ संभव हो सिंचाई की तैयारी उचित सावधानी है.",
    lowerBody: "शुष्क दौर की कम संभावना के समय गांठ जकड़न और फली विकास के दौरान नियमित निगरानी जारी रखें.",
    monitoring: [
      "गांठ जकड़न और फली विकास के दौरान मिट्टी की नमी देखें।",
      "अनुमान की अवधि के लिए स्थानीय वर्षा के आँकड़े देखें।",
      "आकस्मिक विकल्पों पर स्थानीय कृषि मार्गदर्शन से चर्चा करें।",
    ],
    caveat: "फली-क्षेत्र की नमी सतह से अलग होती है; स्थानीय जाँच महत्वपूर्ण है.",
  },
  pigeon_pea: {
    id: "pigeon_pea", name: "अरहर (तूर)",
    context: "लंबी अवधि की खरीफ दालहन; गहरी जड़ें, पर फूल/फली भरने के समय लगातार नमी लाभदायक.",
    elevatedBody: "फूल या फली भरने के दौरान लंबा शुष्क दौर आने पर फसल पर तनाव बढ़ सकता है; निगरानी और आकस्मिक योजना उचित सावधानी है.",
    lowerBody: "शुष्क दौर की कम संभावना के समय फूल और फली भरने के दौरान नियमित निगरानी उचित है.",
    monitoring: [
      "अनुमान की अवधि से फसल अवस्था मिलाकर देखें।",
      "स्थानीय वर्षा के आँकड़े और मिट्टी की नमी देखें।",
      "किसी भी खेत-क्रिया से पहले कृषि मार्गदर्शन पर विचार करें।",
    ],
    caveat: "गहरी जड़ें कुछ सूखा सहन कर लेती हैं; स्थानीय कृषि विवेक को प्राथमिकता दें।",
  },
  generic: {
    id: "generic", name: "सामान्य फसल मार्गदर्शन",
    context: "सामान्य खरीफ फसल मार्गदर्शन (कोई विशिष्ट फसल चयनित नहीं)।",
    elevatedBody: "शुष्क दौर या मानसून विराम से खड़ी खरीफ फसलों पर तनाव आ सकता है; मिट्टी की नमी और स्थानीय वर्षा के आँकड़े देखें, और जहाँ संभव हो सिंचाई की तैयारी रखें.",
    lowerBody: "शुष्क दौर की कम संभावना के समय फसल अवस्था और नमी की नियमित निगरानी उचित है.",
    monitoring: [
      "मिट्टी की नमी और स्थानीय वर्षा के आँकड़े देखें।",
      "किसी भी क्रिया से पहले खेत की स्थिति की समीक्षा करें।",
    ],
    caveat: "फसल के अनुसार ज़रूरतें बदलती हैं; कार्यों की पुष्टि स्थानीय कृषि विभाग के मार्गदर्शन से करें।",
  },
};

export const LOCALIZED_CROPS: Record<LocaleCode, Record<string, LocalizedCropTemplate>> = { en, mr, hi };

export function localizedCrop(locale: LocaleCode, id: string): LocalizedCropTemplate {
  const pack = LOCALIZED_CROPS[locale] ?? LOCALIZED_CROPS.en;
  // per-key fallback: locale pack -> English pack -> generic
  return pack[id] ?? LOCALIZED_CROPS.en[id] ?? LOCALIZED_CROPS.en.generic;
}
