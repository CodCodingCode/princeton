// Softer narration pack for the patient dashboard. Mirrors lib/narration.ts
// but the register is patient-facing: warmer, second-person, no clinician
// jargon. The avatar on /patient pulls from this file instead.

import type { PatientCase } from "./types";

export const PATIENT_GREETING =
  "Hi. I'm here to walk you through what we found in your records, and more importantly, what you can do for yourself right now. Take your time with this page.";

export const PATIENT_TAB_HINTS: Record<string, string> = {
  diagnosis:
    "This is what we're seeing in your records, in plain terms. No jargon. If anything here is confusing, ask me.",
  plan: "Here is what the guidelines suggest for someone in your situation. These are options to bring to your oncologist, not a final decision.",
  healing:
    "This part is about you, not the drugs. Sleep, food, movement, your people. Small things, done steadily, matter more than you'd think.",
  next_steps:
    "These are clinical trials you might qualify for, and questions I'd bring to your next visit.",
};

export function buildPatientResultsNarration(
  c: PatientCase | null | undefined,
): string {
  if (!c) return PATIENT_GREETING;

  const cancerRaw =
    c.primary_cancer_type || c.pathology?.primary_cancer_type || "";
  const cancer = cancerRaw ? cancerRaw.replace(/_/g, " ") : "";

  const parts: string[] = ["Okay. I've been through your records with you."];
  if (cancer) {
    parts.push(`What we're seeing looks like ${cancer}.`);
  }
  parts.push(
    "Take a look at the four tabs on the right. The Healing tab is the one I most want you to read. It's about what you can do for yourself starting today.",
  );
  parts.push("Ask me anything. I'm here.");
  return parts.join(" ");
}
