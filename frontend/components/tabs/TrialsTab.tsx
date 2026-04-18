"use client";

import { useState } from "react";
import type { PatientCase } from "@/lib/types";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";

export function TrialsTab({ caseData }: { caseData: PatientCase }) {
  const [selectedNct, setSelectedNct] = useState<string | null>(null);

  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Matching trials
        </div>
        <p className="text-sm text-neutral-600 leading-relaxed mb-3">
          Ranked against your extracted eligibility. Click a trial to filter the
          map.
        </p>
      </div>

      <TrialMap
        sites={caseData.trial_sites}
        selected={selectedNct}
        onSelect={setSelectedNct}
      />

      <TrialList
        matches={caseData.trial_matches}
        selected={selectedNct}
        onSelect={setSelectedNct}
      />
    </div>
  );
}
