// Plain-English translators — take the structured PatientCase and produce
// short human sentences a layman can understand.

import type { PatientCase, RailwayStep, TrialMatch } from "./types";

export interface PatientFriendly {
  diagnosisHeadline: string;
  diagnosisDetails: string;
  recommendedAction: string;
  recommendedActionDetail: string;
  ctaLabel: string;
  aboutYou: Array<{ label: string; value: string }>;
  nextSteps: string[];
  trialsCta: string;
}

const SUBTYPE_EN: Record<string, string> = {
  superficial_spreading: "superficial-spreading melanoma",
  nodular: "nodular melanoma",
  lentigo_maligna: "lentigo-maligna melanoma",
  acral_lentiginous: "acral-lentiginous melanoma",
  desmoplastic: "desmoplastic melanoma",
  other: "melanoma",
  unknown: "melanoma",
};

function tStageEnglish(tStage: string): string {
  if (tStage === "Tx") return "stage not yet determined";
  if (tStage.startsWith("T1")) return "thin (early stage)";
  if (tStage.startsWith("T2")) return "intermediate thickness";
  if (tStage.startsWith("T3")) return "thick";
  if (tStage.startsWith("T4")) return "very thick (advanced)";
  return tStage;
}

function cleanOptionLabel(s: string): string {
  // Strip parenthetical drug lists and arrows.
  return s
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/→.*/g, "")
    .trim();
}

function finalStepEnglish(step: RailwayStep | undefined): string {
  if (!step) return "Speak with a melanoma specialist about next steps.";
  const chosen = cleanOptionLabel(step.chosen_option_label);
  const mapping: Record<string, string> = {
    "Anti-PD-1 monotherapy":
      "Start immunotherapy with a PD-1 blocker (nivolumab or pembrolizumab).",
    "Ipilimumab + nivolumab combo IO":
      "Start combination immunotherapy (ipilimumab + nivolumab).",
    "Nivolumab + relatlimab":
      "Start nivolumab + relatlimab combination immunotherapy.",
    "BRAF + MEK inhibitor": "Start targeted therapy (BRAF + MEK inhibitors).",
    "Wide local excision + observation":
      "Have the tumor fully removed, then follow up with regular skin checks.",
    "Wide local excision + adjuvant immunotherapy":
      "Have the tumor fully removed, then start preventive immunotherapy.",
    "Adjuvant anti-PD-1":
      "Start preventive immunotherapy (PD-1 blocker) after surgery.",
    "Adjuvant BRAF/MEK":
      "Start preventive targeted therapy (BRAF + MEK inhibitors).",
    "Clinical trial": "Consider enrolling in a clinical trial.",
  };
  for (const [key, sentence] of Object.entries(mapping)) {
    if (chosen.toLowerCase().includes(key.toLowerCase())) return sentence;
  }
  return chosen;
}

function nextStepsFromRailway(steps: RailwayStep[] | undefined): string[] {
  if (!steps?.length) return [];
  const meaningful = steps.filter((s) => !s.is_terminal);
  const tail = meaningful.slice(-3);
  return tail.map((s) => {
    const option = cleanOptionLabel(s.chosen_option_label);
    return `${s.title}: ${option}`;
  });
}

function trialsSentence(matches: TrialMatch[]): string {
  if (!matches.length) return "No trial matching is available yet.";
  const elig = matches.filter((m) => m.status === "eligible");
  const maybe = matches.filter((m) => m.status === "needs_more_data");
  if (elig.length)
    return `${elig.length} trial${elig.length > 1 ? "s" : ""} you may qualify for — ask your oncologist to screen you.`;
  if (maybe.length)
    return `${maybe.length} trial${maybe.length > 1 ? "s" : ""} might fit — your oncologist needs a few more data points to confirm.`;
  return "No matching trials today — your oncologist can re-check after more testing.";
}

export function toPatientFriendly(c: PatientCase): PatientFriendly {
  const subtypeLabel = SUBTYPE_EN[c.pathology.melanoma_subtype] ?? "melanoma";
  const tS = deriveTStage(
    c.pathology.breslow_thickness_mm,
    c.pathology.ulceration,
  );
  const tEnglish = tStageEnglish(tS);

  const brafMut = c.mutations.find(
    (m) => m.gene.toUpperCase() === "BRAF" && m.position === 600,
  );
  const brafSentence = brafMut
    ? `BRAF mutation detected (${brafMut.ref_aa}${brafMut.position}${brafMut.alt_aa}) — both targeted therapy and immunotherapy are options.`
    : "No common BRAF mutation — immunotherapy is usually the first choice.";

  const meaningful = (c.railway?.steps ?? []).filter((s) => !s.is_terminal);
  const lastStep = meaningful[meaningful.length - 1];

  const recommendedAction = finalStepEnglish(lastStep);

  // Reason pulled from the chosen_rationale of the last meaningful step.
  const reason =
    (lastStep?.chosen_rationale || "").split(/[.!?]/)[0].trim() ||
    "Based on the extracted pathology and current NCCN guidelines.";

  const aboutYou: Array<{ label: string; value: string }> = [];
  aboutYou.push({
    label: "What we see",
    value: `${capitalize(subtypeLabel)} — ${tEnglish}`,
  });
  if (c.pathology.breslow_thickness_mm != null) {
    aboutYou.push({
      label: "Tumor thickness",
      value: `${c.pathology.breslow_thickness_mm} mm (Breslow)`,
    });
  }
  if (c.pathology.ulceration !== null) {
    aboutYou.push({
      label: "Ulceration",
      value: c.pathology.ulceration ? "Present" : "Not present",
    });
  }
  aboutYou.push({
    label: "BRAF gene",
    value: brafSentence,
  });
  if (c.intake.ajcc_stage) {
    aboutYou.push({ label: "Overall stage", value: c.intake.ajcc_stage });
  }
  if (c.intake.ecog != null) {
    aboutYou.push({
      label: "Performance status",
      value: `ECOG ${c.intake.ecog} — ${ecogEnglish(c.intake.ecog)}`,
    });
  }
  if (c.mutations.length) {
    const top = c.mutations
      .slice(0, 4)
      .map((m) => `${m.gene} ${m.ref_aa}${m.position}${m.alt_aa}`)
      .join(", ");
    aboutYou.push({ label: "Mutations found", value: top });
  }

  return {
    diagnosisHeadline: `${capitalize(subtypeLabel)} · ${tEnglish}`,
    diagnosisDetails:
      c.pathology.notes?.slice(0, 220) ||
      (c.documents.length > 0
        ? `Based on ${c.documents.length} document${c.documents.length === 1 ? "" : "s"} you uploaded.`
        : "Extracting your uploaded documents…"),
    recommendedAction,
    recommendedActionDetail: reason,
    ctaLabel: "Book an appointment with a medical oncologist",
    aboutYou,
    nextSteps: nextStepsFromRailway(c.railway?.steps),
    trialsCta: trialsSentence(c.trial_matches),
  };
}

export function deriveTStage(
  breslow: number | null,
  ulceration: boolean | null,
): string {
  if (breslow === null) return "Tx";
  const u = !!ulceration;
  if (breslow < 0.8 && !u) return "T1a";
  if (breslow < 1.0) return "T1b";
  if (breslow < 2.0) return u ? "T2b" : "T2a";
  if (breslow < 4.0) return u ? "T3b" : "T3a";
  return u ? "T4b" : "T4a";
}

function capitalize(s: string): string {
  if (!s) return s;
  return s[0].toUpperCase() + s.slice(1);
}

function ecogEnglish(ecog: number): string {
  switch (ecog) {
    case 0:
      return "fully active";
    case 1:
      return "able to do light work";
    case 2:
      return "up and about, but limited";
    case 3:
      return "limited self-care";
    case 4:
      return "bedbound";
    default:
      return "";
  }
}
