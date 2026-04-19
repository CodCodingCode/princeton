"use client";

// Patient-facing cockpit. Thin mirror of app/page.tsx but always in the
// equivalent of "ready" phase - the patient is landing here after the
// oncologist view has already kicked off the orchestrator.
//
//   /patient?case=<id>   → avatar left, PatientSidebar right
//
// If ?case= is missing we send them back to /. If the case isn't in the
// backend yet (or the backend is down) we fall through to an emptyCase()
// stub so the layout still renders and the avatar still greets.

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchCase, subscribeCaseEvents } from "@/lib/api";
import { emptyCase } from "@/lib/empty-case";
import {
  PATIENT_GREETING,
  buildPatientResultsNarration,
} from "@/lib/patientNarration";
import type {
  PatientCase,
  RailwayMap,
  TrialMatch,
  TrialSite,
} from "@/lib/types";
import {
  AvatarStage,
  type AvatarStageHandle,
  type AvatarStatus,
} from "@/components/AvatarStage";
import { PatientSidebar } from "@/components/patient/PatientSidebar";
import { Button, buttonClasses } from "@/components/ui/Button";

export default function Page() {
  return (
    <Suspense fallback={<div className="w-screen h-screen bg-[#faf7f3]" />}>
      <PatientExperience />
    </Suspense>
  );
}

function PatientExperience() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const caseId = searchParams.get("case");

  const stageRef = useRef<AvatarStageHandle | null>(null);
  const greetedRef = useRef(false);
  const finalNarratedRef = useRef(false);

  const [caseData, setCaseData] = useState<PatientCase | null>(null);
  const [avatarStatus, setAvatarStatus] = useState<AvatarStatus>("idle");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Redirect when the URL has no ?case= - the patient page needs a case.
  useEffect(() => {
    if (!caseId) {
      router.replace("/");
    }
  }, [caseId, router]);

  // Fetch the case snapshot. Fall back to emptyCase() so the page still
  // renders if the backend is down.
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    fetchCase(caseId)
      .then((c) => {
        if (!cancelled) setCaseData(c);
      })
      .catch(() => {
        if (!cancelled) setCaseData(emptyCase(caseId));
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // Subscribe to live SSE - the clinician view kicked off the orchestrator,
  // but if the patient lands here before it finishes, we still want the
  // tabs to fill in as events arrive. Same reducer shape as app/page.tsx,
  // scoped to the fields the patient tabs actually read.
  useEffect(() => {
    if (!caseId) return;
    const cleanup = subscribeCaseEvents(caseId, (ev) => {
      if (ev.kind === "case_update") {
        setCaseData(ev.payload as unknown as PatientCase);
      } else if (ev.kind === "pdf_extracted") {
        const p = ev.payload as Record<string, unknown>;
        setCaseData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            pathology:
              (p.pathology as PatientCase["pathology"]) ?? prev.pathology,
            intake: (p.intake as PatientCase["intake"]) ?? prev.intake,
            mutations:
              (p.mutations as PatientCase["mutations"]) ?? prev.mutations,
            primary_cancer_type:
              (p.primary_cancer_type as string) ?? prev.primary_cancer_type,
          };
        });
      } else if (ev.kind === "railway_ready") {
        setCaseData((prev) => {
          if (!prev) return prev;
          const railway = (ev.payload as { railway: RailwayMap }).railway;
          return { ...prev, railway };
        });
      } else if (ev.kind === "trial_matches_ready") {
        setCaseData((prev) => {
          if (!prev) return prev;
          const matches =
            (ev.payload as { matches: TrialMatch[] }).matches ?? [];
          return { ...prev, trial_matches: matches };
        });
      } else if (ev.kind === "trial_sites_ready") {
        setCaseData((prev) => {
          if (!prev) return prev;
          const sites = (ev.payload as { sites: TrialSite[] }).sites ?? [];
          return { ...prev, trial_sites: sites };
        });
      } else if (ev.kind === "done" || ev.kind === "stream_end") {
        // Fire the patient-tone "I've read through your records" narration
        // once per session, after the pipeline wraps.
        setCaseData((prev) => {
          if (prev && !finalNarratedRef.current) {
            finalNarratedRef.current = true;
            stageRef.current
              ?.speak(buildPatientResultsNarration(prev))
              .catch(() => {});
          }
          return prev;
        });
      }
    });
    return cleanup;
  }, [caseId]);

  const handleBegin = useCallback(async () => {
    if (greetedRef.current) return;
    greetedRef.current = true;
    await stageRef.current?.start();
    stageRef.current?.speak(PATIENT_GREETING).catch(() => {});
  }, []);

  const effectiveCase = caseData ?? (caseId ? emptyCase(caseId) : null);
  if (!caseId || !effectiveCase) return null;

  return (
    <div className="h-screen w-screen overflow-hidden relative">
      <AvatarStage
        ref={stageRef}
        onStatusChange={setAvatarStatus}
        compact={false}
      >
        {avatarStatus === "idle" && (
          <div className="absolute inset-0 flex items-end justify-start p-10 pointer-events-none">
            <Button
              onClick={handleBegin}
              size="lg"
              className="pointer-events-auto shadow-lg"
            >
              <span
                aria-hidden
                className="inline-block w-2 h-2 rounded-full bg-emerald-400"
              />
              Start a conversation
            </Button>
          </div>
        )}
      </AvatarStage>

      <PatientSidebar caseData={effectiveCase} open={!sidebarCollapsed} />

      <button
        type="button"
        onClick={() => setSidebarCollapsed((c) => !c)}
        aria-label={sidebarCollapsed ? "Show case panel" : "Hide case panel"}
        title={sidebarCollapsed ? "Show case panel" : "Hide case panel"}
        aria-pressed={!sidebarCollapsed}
        className={buttonClasses(
          "secondary",
          "icon",
          "fixed top-[14px] right-6 z-40",
        )}
      >
        <svg
          aria-hidden
          viewBox="0 0 20 20"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        >
          <line x1="4" y1="6" x2="16" y2="6" />
          <line x1="4" y1="10" x2="16" y2="10" />
          <line x1="4" y1="14" x2="16" y2="14" />
        </svg>
      </button>
    </div>
  );
}
