"use client";

// "Next steps" - trials the patient may be eligible for. The questions-for-
// doctor list + appointment tip used to live here too; they moved to their
// own "Questions to ask" tab to keep each tab single-purpose.

import { useMemo } from "react";
import type { PatientCase, TrialMatch } from "@/lib/types";

function trialStatusLabel(t: TrialMatch): string {
  switch (t.status) {
    case "eligible":
      return "You may qualify";
    case "needs_more_data":
      return "Possibly a fit: needs a few more tests";
    case "ineligible":
      return "Not a fit right now";
    default:
      return "Under review";
  }
}

export function NextStepsTab({ caseData }: { caseData: PatientCase }) {
  const trials = useMemo(() => {
    return (caseData.trial_matches ?? []).filter(
      (t) => t.status === "eligible" || t.status === "needs_more_data",
    );
  }, [caseData]);

  const sitesByNct = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of caseData.trial_sites ?? []) {
      m.set(s.nct_id, (m.get(s.nct_id) ?? 0) + 1);
    }
    return m;
  }, [caseData]);

  return (
    <div className="space-y-5">
      <section>
        <div className="eyebrow mb-2">Trials that might be open to you</div>
        {trials.length === 0 ? (
          <p className="text-sm text-neutral-700 leading-relaxed">
            No open trials matched your case today. That can change as new
            trials open and as your team gathers more data. Ask your oncologist
            to re-check in a few months.
          </p>
        ) : (
          <div className="space-y-3">
            {trials.map((t) => {
              const siteCount = sitesByNct.get(t.nct_id) ?? 0;
              return (
                <article key={t.nct_id} className="card p-4">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-semibold mb-1">
                    {trialStatusLabel(t)}
                  </div>
                  <h3 className="text-sm font-semibold text-black leading-snug mb-1">
                    {t.title}
                  </h3>
                  <div className="text-xs text-neutral-600 mb-2">
                    {t.sponsor}
                    {t.phase ? ` · Phase ${t.phase}` : ""}
                    {siteCount > 0
                      ? ` · ${siteCount} site${siteCount === 1 ? "" : "s"} available`
                      : ""}
                  </div>
                  {t.status === "needs_more_data" &&
                    t.unknown_criteria.length > 0 && (
                      <p className="text-xs text-neutral-600 leading-relaxed">
                        To know for sure, your team would need to confirm:{" "}
                        {t.unknown_criteria.slice(0, 3).join("; ")}.
                      </p>
                    )}
                  {t.url && (
                    <a
                      href={t.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block mt-2 text-xs font-medium text-black underline decoration-neutral-300 hover:decoration-black"
                    >
                      Read the full trial record →
                    </a>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
