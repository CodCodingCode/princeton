"use client";

// Patient-side tab switcher. Mirrors CaseTabs.tsx but the tabs and the
// components they render are patient-facing. URL-syncs via ?tab= so the
// avatar can navigate programmatically in future work.

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useMemo } from "react";
import type { PatientCase } from "@/lib/types";
import { DiagnosisTab } from "./tabs/DiagnosisTab";
import { PlanTab } from "./tabs/PlanTab";
import { HealingTab } from "./tabs/HealingTab";
import { NextStepsTab } from "./tabs/NextStepsTab";
import { QuestionsTab } from "./tabs/QuestionsTab";

const TABS = [
  { id: "diagnosis", label: "Your diagnosis" },
  { id: "plan", label: "Your plan" },
  { id: "healing", label: "How to heal" },
  { id: "next_steps", label: "Next steps" },
  { id: "questions", label: "Questions to ask" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function PatientTabs({ caseData }: { caseData: PatientCase }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const active: TabId = useMemo(() => {
    const t = params.get("tab");
    return TABS.some((x) => x.id === t) ? (t as TabId) : "diagnosis";
  }, [params]);

  function setTab(id: TabId) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  return (
    <aside className="flex flex-col h-full bg-white min-h-0">
      <div className="border-b border-neutral-200 px-2 flex overflow-x-auto shrink-0">
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
        {active === "diagnosis" && <DiagnosisTab caseData={caseData} />}
        {active === "plan" && <PlanTab caseData={caseData} />}
        {active === "healing" && <HealingTab caseData={caseData} />}
        {active === "next_steps" && <NextStepsTab caseData={caseData} />}
        {active === "questions" && <QuestionsTab caseData={caseData} />}
      </div>
    </aside>
  );
}
