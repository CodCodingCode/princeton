"use client";

// "Your plan" - walks the railway steps the oncologist version shows and
// re-frames each as a patient-facing "what the guidelines suggest" card.
// We prefer the systemic phase (that's the decision most patients want
// spelled out) but fall back to the full set of non-terminal steps.

import { useMemo } from "react";
import type { PatientCase, RailwayStep } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";

function cleanOption(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/→.*/g, "")
    .trim();
}

function humanPhase(phaseId: string | null | undefined): string {
  switch (phaseId) {
    case "staging":
      return "Making sure we have the full picture";
    case "primary":
      return "Treating the tumour directly";
    case "systemic":
      return "Body-wide treatment";
    case "followup":
      return "What happens after";
    default:
      return phaseId ? phaseId.replace(/_/g, " ") : "";
  }
}

export function PlanTab({ caseData }: { caseData: PatientCase }) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  const steps = useMemo<RailwayStep[]>(() => {
    const all = caseData.railway?.steps ?? [];
    const meaningful = all.filter((s) => !s.is_terminal);
    const systemic = meaningful.filter((s) => s.phase_id === "systemic");
    const pool = systemic.length ? systemic : meaningful;
    return pool.slice(0, 5);
  }, [caseData]);

  return (
    <div className="space-y-5">
      <section>
        <div className="eyebrow mb-2">The headline</div>
        <p className="text-xl font-semibold tracking-tight leading-tight text-black mb-2">
          {friendly.recommendedAction}
        </p>
        <p className="text-sm text-neutral-700 leading-relaxed">
          {friendly.recommendedActionDetail}
        </p>
      </section>

      {steps.length > 0 && (
        <section>
          <div className="eyebrow mb-3">What the guidelines suggest</div>
          <div className="space-y-3">
            {steps.map((step) => (
              <article key={step.node_id} className="card p-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-semibold mb-1">
                  {humanPhase(step.phase_id)}
                </div>
                <h3 className="text-sm font-semibold text-black leading-snug mb-2">
                  {step.title}
                </h3>
                <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 font-semibold mb-1">
                  Recommended
                </div>
                <p className="text-sm text-black font-medium leading-snug mb-2">
                  {cleanOption(step.chosen_option_label) || "-"}
                </p>
                {step.chosen_rationale && (
                  <p className="text-xs text-neutral-600 leading-relaxed">
                    Why: {step.chosen_rationale.split(/[.!?]/)[0].trim()}.
                  </p>
                )}
                {step.alternatives?.length ? (
                  <p className="text-xs text-neutral-500 leading-relaxed mt-2">
                    Other options considered:{" "}
                    {step.alternatives
                      .slice(0, 2)
                      .map((a) => cleanOption(a.option_label))
                      .filter(Boolean)
                      .join(", ")}
                    .
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="card-muted p-5">
        <div className="eyebrow mb-2">Important</div>
        <p className="text-sm text-neutral-700 leading-relaxed">
          These are guideline-grounded options to bring to your oncologist, not
          a final prescription. The best plan comes from combining what the data
          says with what matters most to you: your schedule, your family, your
          tolerance for side effects. Bring the questions from the &ldquo;Next
          steps&rdquo; tab to your next visit.
        </p>
      </section>
    </div>
  );
}
