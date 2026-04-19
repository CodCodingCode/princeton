"use client";

import type { PatientCase } from "@/lib/types";
import { DocumentsPanel } from "@/components/DocumentsPanel";

export function DocumentsTab({ caseData }: { caseData: PatientCase }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow mb-2">Source documents</div>
        <p className="text-sm text-neutral-600 leading-relaxed">
          Every clinical finding traces back to a source page. Expand a document
          to see what was read from it.
        </p>
      </div>

      <DocumentsPanel
        documents={caseData.documents}
        provenance={caseData.provenance}
        conflicts={caseData.conflicts}
      />
    </div>
  );
}
