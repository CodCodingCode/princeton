import type { EventKind, PatientCase } from "./types";

// Scripted copy - centralized so the orchestrator pulls everything the
// avatar says from one place. Swap freely without touching the page.
export const GREETING =
  "Hi there. I'm your virtual oncology concierge. I'll read through your records with you and walk through what the guidelines say about your options.";

export const INTAKE_PROMPT =
  "To start, share every PDF from your workup: pathology, imaging, any notes you have.";

export const UPLOAD_ACK =
  "Thanks. Let me take a look. This will take a minute.";

export const READY_CUE =
  "I'm ready. Take a look at the panel on the right, and ask me anything.";

// Milestone narration - fired at most once per event kind per case session.
// Keep phrases short; the avatar will queue them and the patient shouldn't
// be waiting on long speech to finish before the next milestone arrives.
//
// NOTE: `done` is intentionally omitted here - it's handled specially in
// page.tsx so the final narration can pull real numbers from the case data.
export const EVENT_NARRATION: Partial<Record<EventKind, string>> = {
  pdf_extracted: "Okay, I've finished reading through every document.",
  aggregation_done:
    "Your records agree on the important things. I have a clean picture now.",
  railway_ready: "I've mapped out your treatment options.",
  trial_matches_ready: "I've matched you against clinical trials.",
  trial_sites_ready: "And I've located the trial sites nearest you.",
};

// Filler narration - played during the long analysis wait to keep the avatar
// engaged. Each entry is spoken only once per case, queued whenever the avatar
// has been silent for roughly 20 seconds. The order matters: start with the
// "what is this" framing, then zoom into what the pipeline is doing right now.
export const PROJECT_EXPLAINERS: string[] = [
  "While I'm working, let me tell you a bit about what I'm doing. I'm NeoVax. My job is to sit with you and your oncologist and turn a messy pile of medical records into a clear treatment plan.",
  "Most cancer cases live across ten or twenty different documents. Pathology reports, imaging, notes, molecular panels. Nobody has time to read them all at once. I do.",
  "Right now I'm reading every page of every file you shared, carefully, from pathology slides and imaging reports to clinician notes.",
  "After reading, I cross-check the files against each other. If one report says stage two and another says stage three, I flag it instead of picking one silently.",
  "Then I walk through the national oncology guidelines, step by step, to decide which treatments actually fit your specific case. Not a generic list. A path built for you.",
  "I also match you against open clinical trials. Real trials, with real eligibility rules. If a trial might accept you, you'll see it on the right, with the nearest sites on a map.",
  "Everything I do is shown to your oncologist as a report they can download. I don't replace their judgment. I just make sure they've seen every option.",
  "Almost there. Thanks for your patience. Good medicine is worth a minute of waiting.",
];

// Build a case-specific results narration fired when processing completes.
// Pulls the few numbers that actually matter: cancer type, top mutations,
// eligible trials, trial sites. Falls back to a generic READY_CUE if the
// case data is empty (e.g. backend crashed mid-run).
export function buildResultsNarration(
  c: PatientCase | null | undefined,
): string {
  if (!c) return READY_CUE;

  const cancerRaw =
    c.primary_cancer_type || c.pathology?.primary_cancer_type || "";
  const cancer = cancerRaw ? cancerRaw.replace(/_/g, " ") : "";

  const mutations = (c.mutations || []).slice(0, 2).map((m) => {
    const isPoint =
      m.position !== null && m.position !== undefined && m.ref_aa && m.alt_aa;
    return isPoint
      ? `${m.gene} ${m.ref_aa}${m.position}${m.alt_aa}`
      : m.raw_label || m.gene || "variant";
  });

  const eligibleTrials = (c.trial_matches || []).filter(
    (t) => t.status === "eligible",
  ).length;

  const siteCount = (c.trial_sites || []).length;

  const parts: string[] = ["Alright. I'm done. Here's the quick read."];
  if (cancer) {
    parts.push(`Your primary diagnosis looks like ${cancer}.`);
  }
  if (mutations.length === 1) {
    parts.push(`I picked up ${mutations[0]} in your molecular data.`);
  } else if (mutations.length >= 2) {
    parts.push(
      `I picked up ${mutations[0]} and ${mutations[1]} in your molecular data.`,
    );
  }
  if (eligibleTrials > 0 && siteCount > 0) {
    parts.push(
      `You have ${eligibleTrials} clinical trial${eligibleTrials === 1 ? "" : "s"} you may be eligible for, across ${siteCount} site${siteCount === 1 ? "" : "s"}.`,
    );
  } else if (eligibleTrials > 0) {
    parts.push(
      `You have ${eligibleTrials} clinical trial${eligibleTrials === 1 ? "" : "s"} you may be eligible for.`,
    );
  }
  parts.push("Take a look at the panel on the right, and ask me anything.");
  return parts.join(" ");
}

// Stage-start narration - fired when the backend emits a [stage N] ▶ START
// log event. Keeps the avatar talking during the long waits (stage 1 can take
// a minute or two on a big PDF folder) so the patient isn't staring at a
// silent face. Only the stages with meaningful wait time are narrated.
export const STAGE_START_NARRATION: Record<string, string> = {
  "1": "Alright. I'm starting to read through each of your documents now. This is the slowest part. Give me a minute.",
  "2": "Good. I've got every page. Now I'm piecing the facts together into one clean record.",
  "6": "Next, I'm walking through the oncology treatment guidelines, step by step, to see what fits your case.",
  "7": "Almost there. Let me check which clinical trials might be a match for you.",
  "8": "Last step. I'm finding the trial sites nearest to you.",
};
