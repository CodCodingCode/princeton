"use client";

// "Questions to ask" - was a section at the bottom of NextStepsTab before it
// earned its own tab. Pulls the LLM-generated questions_for_doctor list from
// the patient guide. The backend caches the guide, so re-fetching here on tab
// mount is effectively free after the Healing / Next-steps tabs have warmed it.

import { useEffect, useState } from "react";
import type { PatientCase } from "@/lib/types";
import { fetchPatientGuide, type PatientGuide } from "@/lib/patientApi";

export function QuestionsTab({ caseData }: { caseData: PatientCase }) {
  const [guide, setGuide] = useState<PatientGuide | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPatientGuide(caseData.case_id)
      .then((g) => {
        if (!cancelled) setGuide(g);
      })
      .catch(() => {
        // Silent - the Healing tab surfaces fetch errors, no need to double up.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.case_id]);

  const questions = guide?.questions_for_doctor ?? [];

  return (
    <div className="space-y-5">
      <section>
        <div className="eyebrow mb-3">Bring these to your next visit</div>
        {loading && !guide ? (
          <ol className="space-y-2 animate-pulse">
            {[0, 1, 2, 3].map((i) => (
              <li
                key={i}
                className="flex gap-3 rounded-xl border border-neutral-200 bg-white p-3"
              >
                <div className="h-3 w-3 rounded bg-neutral-200/70 shrink-0 mt-1" />
                <div className="h-3 w-full rounded bg-neutral-200/60" />
              </li>
            ))}
          </ol>
        ) : questions.length === 0 ? (
          <p className="text-sm text-neutral-700 leading-relaxed">
            We&apos;ll generate a tailored list of questions for you to ask at
            your next appointment once the case finishes processing. Check back
            in a minute.
          </p>
        ) : (
          <ol className="space-y-2 text-sm text-black">
            {questions.map((q, i) => (
              <li
                key={i}
                className="flex gap-3 rounded-xl border border-neutral-200 bg-white p-3"
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
        )}
      </section>

      <section className="card-muted p-5">
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
