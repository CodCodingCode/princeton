"use client";

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

  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Clinical detail
        </div>
        <p className="text-sm text-neutral-600 leading-relaxed">
          Raw extracted fields and pipeline events. Use this tab when sharing
          the case with an oncologist.
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

      <EventLog events={events} />
    </div>
  );
}
