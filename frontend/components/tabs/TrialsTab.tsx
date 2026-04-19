"use client";

import { useEffect, useState } from "react";
import type { PatientCase } from "@/lib/types";
import type { UserLocation } from "@/lib/geo";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";
import { readStoredLocation } from "@/components/LocationPrompt";

export function TrialsTab({ caseData }: { caseData: PatientCase }) {
  const [selectedNct, setSelectedNct] = useState<string | null>(null);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);

  // Restore any saved location from localStorage once the caseId is known.
  // The visible location banner was removed on request; sorting by distance
  // still applies silently if a prior session cached a location.
  useEffect(() => {
    setUserLocation(readStoredLocation(caseData.case_id));
  }, [caseData.case_id]);

  return (
    <div className="space-y-5">
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
