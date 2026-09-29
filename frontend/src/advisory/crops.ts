import type { AdvisoryCore } from "./engine";

/** Step 20 — crop-specific advisory templates.
 *
 * Structured data consumed by the Step 19 engine output; rule logic is NOT duplicated per
 * crop (Step 19 = what situation; Step 20 = how to express it for the crop). Agronomy is
 * kept informational: monitoring/contingency direction only - no invented doses, dates, or
 * chemical schedules. The list below is a practical Maharashtra kharif starter set, not a
 * claim that these are the only suitable crops. */

export interface CropTemplate {
  id: string;
  name: string;
  /** One-line crop context shown next to the advisory. */
  context: string;
  /** Situation-specific informational body for elevated break-risk. */
  elevatedBody: string;
  /** Situation-specific informational body for lower break-risk. */
  lowerBody: string;
  /** Crop-level monitoring suggestions (informational). */
  monitoring: string[];
  /** Crop-level caveat appended after shared cautions. */
  caveat: string;
}

export const CROPS: CropTemplate[] = [
  {
    id: "soybean",
    name: "Soybean",
    context: "Kharif pulse/oilseed; sensitive to moisture stress during flowering and pod filling.",
    elevatedBody:
      "A dry spell during flowering or pod fill can stress the crop; review soil moisture and prepare contingency irrigation arrangements where available.",
    lowerBody:
      "With a lower break-risk indication, routine monitoring of crop stage and soil moisture is reasonable.",
    monitoring: [
      "Monitor soil moisture at pod-setting depth where practical.",
      "Watch for moisture stress signs during flowering and pod filling.",
      "Review local rainfall observations against this indication.",
    ],
    caveat: "Crop water needs vary by soil type and sowing time; local extension guidance should confirm any field action.",
  },
  {
    id: "cotton",
    name: "Cotton",
    context: "Long-duration kharif fiber crop; deep-rooted but squaring/boll stages are moisture-sensitive.",
    elevatedBody:
      "A break phase during squaring or boll development can add stress; monitoring and having contingency irrigation ready is a reasonable precaution.",
    lowerBody:
      "With a lower break-risk indication, continue routine crop monitoring through squaring and boll stages.",
    monitoring: [
      "Monitor soil moisture during squaring and boll development.",
      "Track local rainfall observations for the coming weeks.",
      "Review field conditions before committing to any intervention.",
    ],
    caveat: "Cotton's deep roots can buffer short dry spells; agronomist/extension input should guide any decision.",
  },
  {
    id: "maize",
    name: "Maize",
    context: "Kharif cereal; tasseling/silking is the most moisture-sensitive stage.",
    elevatedBody:
      "A dry spell around tasseling or silking can affect grain set; review soil moisture and local observations during those stages.",
    lowerBody:
      "With a lower break-risk indication, routine monitoring through vegetative and reproductive stages is reasonable.",
    monitoring: [
      "Watch tasseling/silking stages closely if they coincide with the indication window.",
      "Monitor soil moisture and local rainfall observations.",
      "Keep contingency options reviewed with local extension guidance.",
    ],
    caveat: "Water needs vary strongly by growth stage and hybrid; confirm actions locally.",
  },
  {
    id: "groundnut",
    name: "Groundnut",
    context: "Kharif oilseed; pod development needs consistent moisture.",
    elevatedBody:
      "A dry spell during pod development can affect yields; monitoring soil moisture and preparing contingency irrigation where available is a reasonable precaution.",
    lowerBody:
      "With a lower break-risk indication, continue routine monitoring through pegging and pod development.",
    monitoring: [
      "Monitor soil moisture during pegging and pod development.",
      "Review local rainfall observations for the indication window.",
      "Discuss contingency options with local extension guidance.",
    ],
    caveat: "Pod-zone moisture differs from surface readings; local verification is important.",
  },
  {
    id: "pigeon_pea",
    name: "Pigeon pea (Tur)",
    context: "Long-duration kharif pulse; deep-rooted, but flowering/pod fill benefit from steady moisture.",
    elevatedBody:
      "An extended break during flowering or pod fill can stress the crop; monitoring and contingency planning are reasonable precautions.",
    lowerBody:
      "With a lower break-risk indication, routine monitoring through flowering and pod fill is reasonable.",
    monitoring: [
      "Monitor crop stage relative to the indication window.",
      "Review local rainfall observations and soil moisture.",
      "Consider extension guidance before any field intervention.",
    ],
    caveat: "Deep rooting provides some drought buffering; local agronomic judgment should lead.",
  },
];

export const GENERIC_TEMPLATE: CropTemplate = {
  id: "generic",
  name: "General cropping",
  context: "General kharif cropping guidance (no specific crop selected).",
  elevatedBody:
    "A dry spell or break phase may stress standing kharif crops; review soil moisture and local rainfall observations, and prepare contingency irrigation arrangements where available.",
  lowerBody:
    "With a lower break-risk indication, routine monitoring of crop stage and soil moisture is reasonable.",
  monitoring: [
    "Monitor soil moisture and local rainfall observations.",
    "Review field conditions before any intervention.",
  ],
  caveat: "Crop-specific needs vary widely; local agricultural-extension guidance should confirm any action.",
};

export function cropById(id: string | null | undefined): CropTemplate {
  return CROPS.find((c) => c.id === id) ?? GENERIC_TEMPLATE;
}

/** Compose the final advisory: Step 19 situation + Step 20 crop expression. Deterministic. */
export function composeAdvisory(core: AdvisoryCore, crop: CropTemplate) {
  const elevated = core.triggers.some((t) => t.rule === "elevated_break_risk");
  return {
    cropId: crop.id,
    cropName: crop.name,
    status: core.status,
    headline: core.headline,
    message: `${core.message} ${elevated ? crop.elevatedBody : crop.lowerBody}`,
    monitoring: crop.monitoring,
    cautions: [...core.cautions, crop.caveat],
    disclaimer: true as const,
    triggers: core.triggers,
  };
}
