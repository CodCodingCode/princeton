"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useMemo } from "react";
import type { AgentEvent, PatientCase } from "@/lib/types";
import { OverviewTab } from "./tabs/OverviewTab";
import { PlanTab } from "./tabs/PlanTab";
import { TrialsTab } from "./tabs/TrialsTab";
import { DocumentsTab } from "./tabs/DocumentsTab";
import { ClinicalTab } from "./tabs/ClinicalTab";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "plan", label: "Plan" },
  { id: "trials", label: "Trials" },
  { id: "documents", label: "Documents" },
  { id: "clinical", label: "Clinical" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export type ExtractFeedEntry = {
  kind: "start" | "done";
  filename: string;
  bytes?: number;
  chars?: number;
  done?: number;
  total?: number;
  ts: number;
};

export type ExtractProgress = {
  done: number;
  total: number;
  latest: string;
};

export function CaseTabs({
  caseData,
  events,
  extractProgress,
  extractFeed,
}: {
  caseData: PatientCase;
  events: AgentEvent[];
  extractProgress?: ExtractProgress | null;
  extractFeed?: ExtractFeedEntry[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const active: TabId = useMemo(() => {
    const t = params.get("tab");
    return TABS.some((x) => x.id === t) ? (t as TabId) : "overview";
  }, [params]);

  function setTab(id: TabId) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  return (
    <aside className="flex flex-col bg-white min-h-0">
      <div className="border-b border-neutral-200 px-2 flex overflow-x-auto">
        {TABS.map((tab) => {
          const isActive = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setTab(tab.id)}
              className={`px-4 py-3 text-sm whitespace-nowrap transition border-b-2 -mb-px ${
                isActive
                  ? "border-black text-black font-medium"
                  : "border-transparent text-neutral-500 hover:text-black"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {active === "overview" && (
          <OverviewTab
            caseData={caseData}
            extractProgress={extractProgress ?? null}
            extractFeed={extractFeed ?? []}
          />
        )}
        {active === "plan" && <PlanTab caseData={caseData} />}
        {active === "trials" && <TrialsTab caseData={caseData} />}
        {active === "documents" && <DocumentsTab caseData={caseData} />}
        {active === "clinical" && (
          <ClinicalTab caseData={caseData} events={events} />
        )}
      </div>
    </aside>
  );
}
