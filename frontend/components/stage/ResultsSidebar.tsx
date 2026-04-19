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

  return (
    <aside
      className={`fixed top-20 right-6 bottom-6 w-[34vw] min-w-[420px] max-w-[560px] z-20 flex flex-col min-h-0 rounded-2xl bg-white/75 backdrop-blur-xl border border-neutral-200/70 shadow-xl shadow-black/5 overflow-hidden transition-all duration-[600ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
        open
          ? "translate-x-0 opacity-100 pointer-events-auto"
          : "translate-x-[calc(100%+2rem)] opacity-0 pointer-events-none"
      }`}
    >
      {/* Instrument-panel case header: status dot + case id + doc count on
          top row, serif diagnosis headline below, report action on the right.
          Hairline rule under the id row evokes a patient chart banner. */}
      <header className="border-b border-neutral-200/70 px-5 pt-3 pb-3 flex items-start justify-between gap-3 shrink-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5 text-[10px] font-mono tabular-nums uppercase tracking-[0.18em] text-neutral-500">
            <span
              aria-hidden
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                done ? "bg-black" : "bg-brand-700 animate-breathe"
              }`}
            />
            <span className="text-black">
              Case {caseData.case_id.slice(0, 10).toUpperCase()}
            </span>
            <span className="text-neutral-300">·</span>
            <span>
              {caseData.documents.length} doc
              {caseData.documents.length === 1 ? "" : "s"}
            </span>
            <span className="text-neutral-300">·</span>
            <span>{done ? "Ready" : "Running"}</span>
          </div>
          <h1 className="mt-1.5 text-xl font-semibold tracking-tight leading-tight text-black">
            {friendly.diagnosisHeadline}
          </h1>
        </div>
        <div className="shrink-0 pt-0.5">
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
