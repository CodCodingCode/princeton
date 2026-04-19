"use client";

// "Next steps" - trials the patient may be eligible for + questions to
// bring to their next oncology visit. Questions come from the same
// patient-guide endpoint the Healing tab uses, so we re-fetch (the
// backend caches the result, so this is effectively free after the
// first call).

import { useEffect, useMemo, useState } from "react";
import type { PatientCase, TrialMatch } from "@/lib/types";
import { fetchPatientGuide, type PatientGuide } from "@/lib/patientApi";

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
  const [guide, setGuide] = useState<PatientGuide | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPatientGuide(caseData.case_id)
      .then((g) => {
        if (!cancelled) setGuide(g);
      })
      .catch(() => {
        // Silent - the Healing tab will also have surfaced the error if there
        // was one. This tab can still render the trial list without the guide.
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.case_id]);

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
    <div className="space-y-8">
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
                <article
                  key={t.nct_id}
                  className="rounded-xl border border-neutral-200/80 bg-white/70 p-4"
                >
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

      {guide?.questions_for_doctor?.length ? (
        <section>
          <div className="eyebrow mb-3">Bring these to your next visit</div>
          <ol className="space-y-2 text-sm text-black">
            {guide.questions_for_doctor.map((q, i) => (
              <li
                key={i}
                className="flex gap-3 rounded-lg border border-neutral-200/80 bg-white/60 p-3"
              >
                <span
                  aria-hidden
                  className="font-mono text-[11px] text-neutral-400 shrink-0 pt-1"
                >
                  {i + 1}
                </span>
                <span className="leading-relaxed">{q}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="rounded-xl border border-neutral-200/80 bg-[#faf7f3]/60 p-5">
        <div className="eyebrow mb-2">A small thing that helps a lot</div>
        <p className="text-sm text-neutral-700 leading-relaxed">
          Bring someone with you to the appointment where these questions get
          answered. Two sets of ears catch more than one, and it&apos;s easier
          to make decisions later when you can talk them through with someone
          who heard the same words you did.
        </p>
      </section>
    </div>
  );
}
