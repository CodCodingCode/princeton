// Plain-English translators - take the structured PatientCase and produce
// short human sentences a layman can understand.
//
// Cancer-agnostic: uses primary_cancer_type when available, falls back to
// melanoma-subtype and Breslow-based T-stage when the case is melanoma.

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

// Normalize AJCC stage strings for display. Strips underscores, drops any
// "stage" prefix, and converts leading Roman numerals to Arabic so "III_C"
// / "stage iii" / "IIIC" all render as "3C" / "3".
export function formatStage(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let s = raw.trim();
  if (!s) return null;
  s = s.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  s = s.replace(/^stage\s*/i, "");
  const m = s.match(/^(IV|III|II|I)\s*([A-Za-z0-9].*)?$/i);
  if (m) {
    const map: Record<string, string> = { I: "1", II: "2", III: "3", IV: "4" };
    const arabic = map[m[1].toUpperCase()];
    const rest = (m[2] ?? "").toUpperCase().replace(/\s+/g, "");
    return arabic + rest;
  }
  return s;
}

// Patient-friendly cancer-type labels. Plain English for laypeople - the
// clinician-side technical name lives on the underlying pathology field.
const CANCER_TYPE_EN: Record<string, string> = {
  cutaneous_melanoma: "melanoma (a skin cancer)",
  lung_adenocarcinoma: "lung cancer",
  lung_squamous: "lung cancer",
  breast_ductal_carcinoma: "breast cancer",
  breast_carcinoma: "breast cancer",
  colorectal_adenocarcinoma: "colon or rectal cancer",
  colorectal_carcinoma: "colon or rectal cancer",
  gastric_carcinoma: "stomach cancer",
  pancreatic_carcinoma: "pancreatic cancer",
  prostate_carcinoma: "prostate cancer",
  ovarian_carcinoma: "ovarian cancer",
  renal_cell_carcinoma: "kidney cancer",
  hepatocellular_carcinoma: "liver cancer",
  bladder_carcinoma: "bladder cancer",
  head_neck_scc: "head and neck cancer",
  glioblastoma: "a type of brain cancer",
  lymphoma_dlbcl: "lymphoma",
  multiple_myeloma: "multiple myeloma (a blood cancer)",
  other: "cancer",
  unknown: "cancer (type being confirmed)",
};

// Turn pathology-report site wording into something a patient can picture.
// Lobe-based phrasing is the most common jargon we see ("right upper lobe
// lung"), so we flip it into "upper part of the right lung". Anything we
// don't recognise falls through unchanged.
function humanPrimarySite(raw: string): string {
  const s = raw.toLowerCase().trim();
  const lobe = s.match(
    /^(right|left)\s+(upper|middle|lower)\s+lobe(?:\s+(?:of\s+(?:the\s+)?)?lung)?$/,
  );
  if (lobe) return `${lobe[2]} part of the ${lobe[1]} lung`;
  return raw;
}

const MELANOMA_SUBTYPE_EN: Record<string, string> = {
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

function cleanOptionLabel(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/→.*/g, "")
    .trim();
}

function finalStepEnglish(step: RailwayStep | undefined): string {
  if (!step) return "Speak with a medical oncologist about next steps.";
  return cleanOptionLabel(step.chosen_option_label) || step.title;
}

function nextStepsFromRailway(steps: RailwayStep[] | undefined): string[] {
  if (!steps?.length) return [];
  // Prefer the systemic-therapy phase when present - that's the decision the
  // patient usually wants spelled out. Fall back to the last 3 steps.
  const systemic = steps.filter((s) => s.phase_id === "systemic");
  const pool = systemic.length ? systemic : steps.filter((s) => !s.is_terminal);
  return pool.slice(0, 3).map((s) => {
    const option = cleanOptionLabel(s.chosen_option_label);
    return `${s.title}: ${option}`;
  });
}

function trialsSentence(matches: TrialMatch[]): string {
  if (!matches.length) return "No trial matching is available yet.";
  const elig = matches.filter((m) => m.status === "eligible");
  const maybe = matches.filter((m) => m.status === "needs_more_data");
  if (elig.length)
    return `${elig.length} trial${elig.length > 1 ? "s" : ""} you may qualify for - ask your oncologist to screen you.`;
  if (maybe.length)
    return `${maybe.length} trial${maybe.length > 1 ? "s" : ""} might fit - your oncologist needs a few more data points to confirm.`;
  return "No matching trials today - your oncologist can re-check after more testing.";
}

function diagnosisHeadline(c: PatientCase): string {
  const cancerType = c.primary_cancer_type || c.pathology.primary_cancer_type;
  const isMelanoma = cancerType === "cutaneous_melanoma";

  if (isMelanoma) {
    const subtypeLabel =
      MELANOMA_SUBTYPE_EN[c.pathology.melanoma_subtype] ?? "melanoma";
    const tS = deriveTStage(
      c.pathology.breslow_thickness_mm,
      c.pathology.ulceration,
    );
    return `${capitalize(subtypeLabel)} · ${tStageEnglish(tS)}`;
  }

  const label =
    CANCER_TYPE_EN[cancerType] || cancerType?.replace(/_/g, " ") || "cancer";
  // Deliberately no primary_site in the headline - it duplicates the
  // "Where it started" row below and makes the heading feel clinical.
  const stageFmt = formatStage(c.intake.ajcc_stage);
  const stage = stageFmt ? ` · Stage ${stageFmt}` : "";
  return `${capitalize(label)}${stage}`;
}

export function toPatientFriendly(c: PatientCase): PatientFriendly {
  const cancerType = c.primary_cancer_type || c.pathology.primary_cancer_type;
  const isMelanoma = cancerType === "cutaneous_melanoma";

  const brafMut = c.mutations.find(
    (m) => m.gene.toUpperCase() === "BRAF" && m.position === 600,
  );
  const egfrMut = c.mutations.find((m) => m.gene.toUpperCase() === "EGFR");

  const meaningful = (c.railway?.steps ?? []).filter((s) => !s.is_terminal);
  const systemic = meaningful.filter((s) => s.phase_id === "systemic");
  const headlineStep = systemic[0] || meaningful[meaningful.length - 1];

  const recommendedAction = finalStepEnglish(headlineStep);
  const reason =
    (headlineStep?.chosen_rationale || "").split(/[.!?]/)[0].trim() ||
    "Based on the clinical findings in your records and current oncology-trial literature.";

  const aboutYou: Array<{ label: string; value: string }> = [];

  aboutYou.push({
    label: "What this is",
    value:
      CANCER_TYPE_EN[cancerType] ??
      (cancerType?.replace(/_/g, " ") || "cancer (type being confirmed)"),
  });

  if (c.pathology.primary_site) {
    aboutYou.push({
      label: "Where it started",
      value: humanPrimarySite(c.pathology.primary_site),
    });
  }

  if (isMelanoma) {
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
    if (brafMut) {
      aboutYou.push({
        label: "BRAF gene",
        value: `BRAF mutation (${brafMut.ref_aa}${brafMut.position}${brafMut.alt_aa}) - both targeted therapy and immunotherapy are options.`,
      });
    } else {
      aboutYou.push({
        label: "BRAF gene",
        value:
          "No common BRAF mutation - immunotherapy is usually the first choice.",
      });
    }
  } else if (egfrMut) {
    aboutYou.push({
      label: "Key genetic finding",
      value:
        "A change in a gene called EGFR was found. This is actually helpful news - there are targeted pills designed for this kind of change, and they're usually the first treatment people try.",
    });
  }

  const stageDisplay = formatStage(c.intake.ajcc_stage);
  if (stageDisplay && !isMelanoma) {
    aboutYou.push({ label: "Stage", value: stageDisplay });
  }
  if (c.intake.ecog != null) {
    const phrase = ecogEnglish(c.intake.ecog);
    if (phrase) {
      aboutYou.push({
        label: "Day-to-day activity",
        value: capitalize(phrase),
      });
    }
  }
  // Deliberately omit a raw "Mutations found" row - the HGVS notation
  // (p.R175H, CDKN2A/B loss, etc.) is exactly the vocabulary this view
  // promises to strip. The key actionable change is already surfaced above.

  return {
    diagnosisHeadline: diagnosisHeadline(c),
    diagnosisDetails: patientDiagnosisDetails(c, cancerType),
    recommendedAction,
    recommendedActionDetail: reason,
    ctaLabel: "Book an appointment with a medical oncologist",
    aboutYou,
    nextSteps: nextStepsFromRailway(c.railway?.steps),
    trialsCta: trialsSentence(c.trial_matches),
  };
}

// Build a plain-English paragraph from structured fields. The pathology
// notes are full of clinical shorthand (1L / 2L, drug names, mutation
// notation, ECOG) so we deliberately *don't* use them on the patient side.
function patientDiagnosisDetails(c: PatientCase, cancerType: string): string {
  const plainCancer = CANCER_TYPE_EN[cancerType] || "cancer";
  const sitePhrase = c.pathology.primary_site
    ? ` that started in the ${humanPrimarySite(c.pathology.primary_site)}`
    : "";
  const stage = formatStage(c.intake.ajcc_stage);
  const parts: string[] = [];
  parts.push(
    `Based on your records, this looks like ${plainCancer}${sitePhrase}.`,
  );
  if (stage) parts.push(`It's at stage ${stage}.`);
  parts.push(
    "The tabs below walk through what this means and what the guidelines suggest as next steps.",
  );
  return parts.join(" ");
}

// Friendly label for a document_kind value emitted by the backend extractor.
// Maps the machine enums (pathology_report, molecular_report, …) to the kind
// of document a clinician would describe in conversation.
const DOCUMENT_KIND_LABEL: Record<string, string> = {
  pathology_report: "Pathology report",
  molecular_report: "Molecular / NGS report",
  imaging_report: "Imaging report",
  clinical_note: "Clinical note",
  unknown: "Clinical document",
};

export function documentKindLabel(kind: string | null | undefined): string {
  if (!kind) return "Clinical document";
  return DOCUMENT_KIND_LABEL[kind] ?? "Clinical document";
}

// Build a human display name for an uploaded document: "Pathology report",
// or "Pathology report 2" when several of the same kind were uploaded.
// `indexOfKind` is the 0-based position of this doc within its kind group.
// `totalOfKind` is how many documents share this kind overall - used to
// decide whether to append a numeric suffix at all.
export function documentDisplayName(
  kind: string | null | undefined,
  indexOfKind: number,
  totalOfKind: number,
): string {
  const base = documentKindLabel(kind);
  if (totalOfKind <= 1) return base;
  return `${base} ${indexOfKind + 1}`;
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
