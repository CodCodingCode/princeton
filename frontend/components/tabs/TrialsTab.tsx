"use client";

import { useEffect, useState } from "react";
import type { PatientCase } from "@/lib/types";
import type { UserLocation } from "@/lib/geo";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";
import {
  LocationPrompt,
  readStoredLocation,
} from "@/components/LocationPrompt";

export function TrialsTab({ caseData }: { caseData: PatientCase }) {
  const [selectedNct, setSelectedNct] = useState<string | null>(null);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);

  // Restore any saved location from localStorage once the caseId is known.
  useEffect(() => {
    setUserLocation(readStoredLocation(caseData.case_id));
  }, [caseData.case_id]);

  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow mb-2">Matching trials</div>
        <p className="text-sm text-neutral-600 leading-relaxed mb-3">
          Regeneron-sponsored trials use hand-written eligibility rules. Other
          trials come from ClinicalTrials.gov, filtered to recruiting studies
          for your cancer type. Share your location to rank by nearest site.
        </p>
      </div>

      <LocationPrompt
        caseId={caseData.case_id}
        location={userLocation}
        onChange={setUserLocation}
      />

      <TrialMap
        sites={caseData.trial_sites}
        selected={selectedNct}
        onSelect={setSelectedNct}
        userLocation={userLocation}
      />

      <TrialList
        matches={caseData.trial_matches}
        sites={caseData.trial_sites}
        selected={selectedNct}
        onSelect={setSelectedNct}
        userLocation={userLocation}
      />
    </div>
  );
}
