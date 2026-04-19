// Thin client for the patient-facing endpoints. Right now just the healing
// guide - keeps patient-only calls out of lib/api.ts so the oncologist side
// can evolve independently.

export interface HealingBlock {
  heading: string;
  body: string;
  bullets: string[];
}

export interface PatientGuide {
  headline: string;
  healing: HealingBlock[];
  warning_signs: string[];
  things_to_avoid: string[];
  questions_for_doctor: string[];
}

export async function fetchPatientGuide(
  caseId: string,
  opts: { refresh?: boolean } = {},
): Promise<PatientGuide> {
  const qs = opts.refresh ? "?refresh=true" : "";
  const resp = await fetch(`/api/cases/${caseId}/patient-guide${qs}`, {
    method: "POST",
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`Patient guide failed: ${resp.status} ${detail}`);
  }
  return (await resp.json()) as PatientGuide;
}
