"use client";

// Patient-facing sidebar. Mirrors the shape + transitions of
// ResultsSidebar.tsx but the header is warmer and the tab surface is
// PatientTabs instead of CaseTabs. No Report PDF button - the clinician
// PDF is not meant for the patient view.

import type { PatientCase } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";
import { PatientTabs } from "./PatientTabs";
import { useMemo } from "react";

interface Props {
  caseData: PatientCase;
  open?: boolean;
}

export function PatientSidebar({ caseData, open = true }: Props) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  return (
    <aside
      className={`fixed top-20 right-6 bottom-6 w-[36vw] min-w-[440px] max-w-[600px] z-20 flex flex-col min-h-0 rounded-2xl bg-white/75 backdrop-blur-xl border border-neutral-200/70 shadow-xl shadow-black/5 overflow-hidden transition-all duration-[600ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
        open
          ? "translate-x-0 opacity-100 pointer-events-auto"
          : "translate-x-[calc(100%+2rem)] opacity-0 pointer-events-none"
      }`}
    >
      <header className="border-b border-neutral-200/70 px-6 pt-4 pb-4 shrink-0">
        <div className="flex items-center gap-2 text-[10px] font-mono tabular-nums uppercase tracking-[0.2em] text-neutral-500 mb-1.5">
          <span
            aria-hidden
            className="inline-block w-1.5 h-1.5 rounded-full bg-brand-700 animate-breathe"
          />
          <span className="text-neutral-700">For you · plain English</span>
        </div>
        <h1 className="font-serif text-2xl leading-tight text-black">
          {friendly.diagnosisHeadline}
        </h1>
      </header>

      <div className="flex-1 min-h-0">
        <PatientTabs caseData={caseData} />
      </div>
    </aside>
  );
}
