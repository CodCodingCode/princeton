"use client";

// "Your diagnosis" - renders the plainEnglish.ts output with generous
// typography. Nothing calls the LLM here; it's pure presentation of
// toPatientFriendly() fields.

import { useMemo } from "react";
import type { PatientCase } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";

export function DiagnosisTab({ caseData }: { caseData: PatientCase }) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  return (
    <div className="space-y-8">
      <section>
        <div className="eyebrow mb-2">What we're seeing</div>
        <p className="font-serif text-2xl leading-tight text-black mb-3">
          {friendly.diagnosisHeadline}
        </p>
        <p className="text-sm text-neutral-700 leading-relaxed">
          {friendly.diagnosisDetails}
        </p>
      </section>

      {friendly.aboutYou.length > 0 && (
        <section>
          <div className="eyebrow mb-3">About your case</div>
          <dl className="divide-y divide-neutral-200/80 border-t border-b border-neutral-200/80">
            {friendly.aboutYou.map((row) => (
              <div
                key={row.label}
                className="grid grid-cols-[10rem_1fr] gap-4 py-3"
              >
                <dt className="text-xs uppercase tracking-widest text-neutral-500 font-semibold pt-0.5">
                  {row.label}
                </dt>
                <dd className="text-sm text-black leading-relaxed">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="rounded-xl border border-neutral-200/80 bg-white/60 p-5">
        <div className="eyebrow mb-2">A note on jargon</div>
        <p className="text-sm text-neutral-700 leading-relaxed">
          The clinician view has all the raw pathology terms, mutation notation,
          and guideline citations. This view strips those out on purpose. If
          anything here is unclear, ask the avatar. You don&apos;t need to learn
          a new vocabulary to understand your own case.
        </p>
      </section>
    </div>
  );
}
