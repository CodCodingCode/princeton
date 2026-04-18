"use client";

import type { AgentEvent, PatientCase } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";
import {
  CaseTabs,
  type ExtractFeedEntry,
  type ExtractProgress,
} from "@/components/CaseTabs";
import { ReportButton } from "@/components/ReportButton";
import { useMemo } from "react";

interface Props {
  caseData: PatientCase;
  events: AgentEvent[];
  done: boolean;
  extractProgress?: ExtractProgress | null;
  extractFeed?: ExtractFeedEntry[];
  open?: boolean;
}

export function ResultsSidebar({
  caseData,
  events,
  done,
  extractProgress,
  extractFeed,
  open = true,
}: Props) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  const banner = useMemo(() => {
    const parts: string[] = [];
    if (caseData.intake.age_years)
      parts.push(`Age ${caseData.intake.age_years}`);
    const primary =
      caseData.primary_cancer_type || caseData.pathology.primary_cancer_type;
    if (primary && primary !== "unknown")
      parts.push(primary.replace(/_/g, " "));
    if (caseData.pathology.primary_site)
      parts.push(caseData.pathology.primary_site);
    if (caseData.intake.ajcc_stage)
      parts.push(`AJCC ${caseData.intake.ajcc_stage}`);
    const firstMut = caseData.mutations[0];
    if (firstMut)
      parts.push(
        `${firstMut.gene} ${firstMut.ref_aa}${firstMut.position}${firstMut.alt_aa}`,
      );
    return parts;
  }, [caseData]);

  return (
    <aside
      className={`fixed top-20 right-6 bottom-6 w-[34vw] min-w-[420px] max-w-[560px] z-20 flex flex-col min-h-0 rounded-2xl bg-white/75 backdrop-blur-xl border border-neutral-200/70 shadow-xl shadow-black/5 overflow-hidden transition-all duration-[600ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
        open
          ? "translate-x-0 opacity-100 pointer-events-auto"
          : "translate-x-[calc(100%+2rem)] opacity-0 pointer-events-none"
      }`}
    >
      <header className="border-b border-neutral-200/70 px-5 py-3 flex items-center justify-between gap-3 shrink-0">
        <div className="min-w-0">
          <div className="eyebrow flex items-center gap-2">
            <span className="truncate font-mono tabular-nums">
              Case {caseData.case_id}
            </span>
          </div>
          <h1 className="text-sm font-semibold tracking-tight text-black truncate">
            {friendly.diagnosisHeadline}
          </h1>
        </div>
        <div className="shrink-0">
          <ReportButton caseId={caseData.case_id} enabled={done} />
        </div>
      </header>

      {banner.length > 0 && (
        <div className="border-b border-neutral-200/70 px-5 py-2 bg-[#faf7f3]/40 shrink-0">
          <div className="flex items-center gap-2 text-[11px] font-mono tabular-nums text-neutral-700 flex-wrap">
            {banner.map((p, i) => (
              <span key={i} className="flex items-center gap-2">
                {i > 0 && <span className="text-neutral-300">·</span>}
                <span className="whitespace-nowrap">{p}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0">
        <CaseTabs
          caseData={caseData}
          events={events}
          extractProgress={extractProgress}
          extractFeed={extractFeed}
        />
      </div>
    </aside>
  );
}
