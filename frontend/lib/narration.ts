import type { EventKind } from "./types";

// Scripted copy — centralized so the orchestrator pulls everything the
// avatar says from one place. Swap freely without touching the page.
export const GREETING =
  "Hi there. I'm your virtual oncology concierge. I'll read through your records with you and walk through what the guidelines say about your options.";

export const INTAKE_PROMPT =
  "To start, share every PDF from your workup — pathology, imaging, any notes you have.";

export const UPLOAD_ACK =
  "Thanks. Let me take a look — this will take a minute.";

export const READY_CUE =
  "I'm ready. Take a look at the panel on the right, and ask me anything.";

// Milestone narration — fired at most once per event kind per case session.
// Keep phrases short; the avatar will queue them and the patient shouldn't
// be waiting on long speech to finish before the next milestone arrives.
export const EVENT_NARRATION: Partial<Record<EventKind, string>> = {
  pdf_extracted: "I've finished reading your pathology.",
  aggregation_done: "I've reconciled everything across your documents.",
  railway_ready: "I've mapped out your treatment options.",
  trial_matches_ready: "I've matched you against clinical trials.",
  trial_sites_ready: "And I've located the trial sites nearest you.",
  done: READY_CUE,
};
