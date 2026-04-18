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
}

export function ResultsSidebar({
  caseData,
  events,
  done,
  extractProgress,
  extractFeed,
}: Props) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  return (
    <aside className="flex flex-col h-full bg-white border-l border-neutral-200 min-h-0">
      <header className="border-b border-neutral-200 px-5 py-3 flex items-center justify-between gap-3 shrink-0">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-semibold flex items-center gap-2">
            <span className="truncate">Case {caseData.case_id}</span>
            <span className="text-neutral-300">·</span>
            <span
              className={done ? "text-emerald-600" : "text-black pulse-dot"}
            >
              {done ? "Ready" : "Running"}
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
