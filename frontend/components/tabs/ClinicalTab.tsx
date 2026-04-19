"use client";

import { useState } from "react";
import type { AgentEvent, PatientCase } from "@/lib/types";
import { deriveTStage } from "@/lib/plainEnglish";
import { ExtractedFields } from "@/components/ExtractedFields";
import { EventLog } from "@/components/EventLog";

export function ClinicalTab({
  caseData,
  events,
}: {
  caseData: PatientCase;
  events: AgentEvent[];
}) {
  const tStage = deriveTStage(
    caseData.pathology.breslow_thickness_mm,
    caseData.pathology.ulceration,
  );
  const [showPipeline, setShowPipeline] = useState(false);

  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow mb-2">Clinical detail</div>
        <p className="text-sm text-neutral-600 leading-relaxed">
          Structured clinical findings distilled from the uploaded records,
          formatted for handoff to the treating oncologist.
        </p>
      </div>

      <ExtractedFields
        pathology={caseData.pathology}
        intake={caseData.intake}
        enrichment={caseData.enrichment}
        mutations={caseData.mutations}
        primaryCancerType={caseData.primary_cancer_type}
        tStage={tStage}
      />

      <div>
        <button
          type="button"
          onClick={() => setShowPipeline((v) => !v)}
          aria-expanded={showPipeline}
          aria-controls="pipeline-events-panel"
          className="w-full card flex items-center justify-between px-4 py-2.5 hover:bg-neutral-50 transition-colors"
        >
          <span className="flex items-center gap-2.5">
            <GearIcon spinning={showPipeline} />
            <span className="eyebrow">System activity</span>
            <span className="text-[11px] text-neutral-500 tabular-nums">
              {events.length} events
            </span>
          </span>
          <Chevron open={showPipeline} />
        </button>

        <div
          id="pipeline-events-panel"
          className={`grid transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${
            showPipeline
              ? "grid-rows-[1fr] opacity-100 mt-3"
              : "grid-rows-[0fr] opacity-0 mt-0"
          }`}
        >
          <div className="overflow-hidden">
            <EventLog events={events} />
          </div>
        </div>
      </div>
    </div>
  );
}

function GearIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`text-neutral-500 transition-transform duration-500 ${
        spinning ? "rotate-90" : "rotate-0"
      }`}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`text-neutral-400 transition-transform duration-300 ${
        open ? "rotate-180" : "rotate-0"
      }`}
      aria-hidden="true"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
