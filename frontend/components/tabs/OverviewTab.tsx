"use client";

import { useMemo } from "react";
import type { PatientCase } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";

export function OverviewTab({ caseData }: { caseData: PatientCase }) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  return (
    <div className="space-y-6">
      {/* Diagnosis summary */}
      <section>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Diagnosis
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-black leading-tight">
          {friendly.diagnosisHeadline}
        </h2>
        <p className="text-sm text-neutral-600 mt-2 leading-relaxed">
          {friendly.diagnosisDetails}
        </p>
      </section>

      {/* Recommended next step */}
      <section className="rounded-2xl border border-neutral-200 p-5">
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Recommended next step
        </div>
        <div className="text-base font-medium text-black leading-snug mb-2">
          {friendly.recommendedAction}
        </div>
        <div className="text-sm text-neutral-600 leading-relaxed mb-4">
          <span className="text-black font-medium">Why: </span>
          {friendly.recommendedActionDetail}
        </div>

        {friendly.nextSteps.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-1">
              Plan at a glance
            </div>
            <ol className="text-sm text-neutral-800 space-y-1">
              {friendly.nextSteps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-neutral-400 shrink-0 tabular-nums">
                    {i + 1}.
                  </span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      {/* About you */}
      <section>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-3">
          About you
        </div>
        <ul className="space-y-3">
          {friendly.aboutYou.map((item, i) => (
            <li
              key={i}
              className="border-b border-neutral-100 pb-2 last:border-none"
            >
              <div className="text-[11px] uppercase tracking-wider text-neutral-500">
                {item.label}
              </div>
              <div className="text-sm text-black leading-snug mt-0.5">
                {item.value}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {caseData.conflicts.length > 0 && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
          <span className="font-semibold">Worth reviewing:</span>{" "}
          {caseData.conflicts.length} fact
          {caseData.conflicts.length === 1 ? "" : "s"} disagreed between your
          documents — see the Documents tab.
        </div>
      )}
    </div>
  );
}
