"use client";

// Phase-driven main experience. Avatar is the canvas; overlays render inside
// the stage depending on the current phase. Ready phase introduces a side
// pane with the case data tabs.
//
// Phases:
//   welcome     — full-screen avatar + Welcome overlay. Needs a user gesture
//                 to unlock audio autoplay → clicking "Begin" starts the
//                 session and speaks the greeting.
//   intake      — full-screen avatar + Intake overlay (PDF drop zone).
//   processing  — full-screen avatar + Processing overlay (status ticker).
//                 Avatar narrates milestone events via EVENT_NARRATION.
//   ready       — grid split: avatar left, ResultsSidebar right.

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchCase, subscribeCaseEvents } from "@/lib/api";
import { emptyCase } from "@/lib/empty-case";
import {
  EVENT_NARRATION,
  GREETING,
  INTAKE_PROMPT,
  UPLOAD_ACK,
} from "@/lib/narration";
import type {
  AgentEvent,
  EventKind,
  PatientCase,
  RailwayMap,
  RailwayStep,
  TrialMatch,
  TrialSite,
} from "@/lib/types";
import {
  AvatarStage,
  type AvatarStageHandle,
  type AvatarStatus,
} from "@/components/AvatarStage";
import { WelcomeOverlay } from "@/components/stage/WelcomeOverlay";
import { IntakeOverlay } from "@/components/stage/IntakeOverlay";
import {
  ProcessingOverlay,
  type ProcessingState,
} from "@/components/stage/ProcessingOverlay";
import { ResultsSidebar } from "@/components/stage/ResultsSidebar";
import type { ExtractFeedEntry } from "@/components/CaseTabs";

type Phase = "welcome" | "intake" | "processing" | "ready";

export default function Page() {
  return (
    <Suspense fallback={<div className="w-screen h-screen bg-black" />}>
      <ExperiencePage />
    </Suspense>
  );
}

function ExperiencePage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const stageRef = useRef<AvatarStageHandle | null>(null);
  const lastProcessedRef = useRef(0);

  const [phase, setPhase] = useState<Phase>("welcome");
  const [avatarStatus, setAvatarStatus] = useState<AvatarStatus>("idle");
  const [caseId, setCaseId] = useState<string | null>(null);
  const [caseData, setCaseData] = useState<PatientCase | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);

  // Processing-phase state (ported from the old /case/[id]/page.tsx).
  const [extractProgress, setExtractProgress] = useState<{
    done: number;
    total: number;
    latest: string;
  } | null>(null);
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [extractFeed, setExtractFeed] = useState<ExtractFeedEntry[]>([]);
  const [firedMilestones, setFiredMilestones] = useState<Set<EventKind>>(
    () => new Set(),
  );

  // URL-sync on mount: if ?case=<id> is present, skip welcome/intake.
  useEffect(() => {
    const fromUrl = searchParams.get("case");
    if (fromUrl && !caseId) {
      setCaseId(fromUrl);
      setPhase("processing");
    }
    // run once — deliberate
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch case snapshot whenever caseId changes.
  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    fetchCase(caseId)
      .then((c) => {
        if (cancelled) return;
        setCaseData(c);
      })
      .catch((e) => {
        if (cancelled) return;
        console.warn("fetchCase failed, falling back to empty-case stub", e);
        setCaseData(emptyCase(caseId));
        setPhase("ready");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // Subscribe SSE once a caseId is set.
  useEffect(() => {
    if (!caseId) return;
    const cleanup = subscribeCaseEvents(caseId, (ev) => {
      setEvents((prev) => [...prev, ev]);

      // Extraction progress + coarse stage tracking.
      const payload = ev.payload as Record<string, unknown> | undefined;
      const phaseField = payload?.phase as string | undefined;
      const stageField = payload?.stage as string | undefined;
      if (stageField && phaseField === "start") setCurrentStage(stageField);
      if (phaseField === "extract_start") {
        const total = Number(payload?.total ?? 0);
        setExtractProgress({ done: 0, total, latest: "" });
        // Per-file "start" entries when backend emits filename + bytes here.
        const filename = payload?.filename as string | undefined;
        if (filename) {
          setExtractFeed((prev) => [
            ...prev,
            {
              kind: "start",
              filename,
              bytes: payload?.bytes as number | undefined,
              ts: Date.now(),
            },
          ]);
        }
      } else if (phaseField === "extract_progress") {
        const done = Number(payload?.done ?? 0);
        const total = Number(payload?.total ?? 0);
        const filename = String(payload?.filename ?? "");
        setExtractProgress({ done, total, latest: filename });
        if (filename) {
          setExtractFeed((prev) => [
            ...prev,
            {
              kind: "done",
              filename,
              chars: payload?.chars as number | undefined,
              done,
              total,
              ts: Date.now(),
            },
          ]);
        }
      }

      // Fold events into the caseData snapshot.
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
            enrichment:
              (p.enrichment as PatientCase["enrichment"]) ?? prev.enrichment,
            mutations:
              (p.mutations as PatientCase["mutations"]) ?? prev.mutations,
            primary_cancer_type:
              (p.primary_cancer_type as string) ?? prev.primary_cancer_type,
          };
        });
      } else if (ev.kind === "railway_step") {
        setCaseData((prev) => {
          if (!prev) return prev;
          const step = (ev.payload as { step: RailwayStep }).step;
          const existing = prev.railway?.steps ?? [];
          const idx = existing.findIndex((s) => s.node_id === step.node_id);
          const newSteps =
            idx >= 0
              ? [...existing.slice(0, idx), step, ...existing.slice(idx + 1)]
              : [...existing, step];
          return {
            ...prev,
            railway: {
              steps: newSteps,
              mermaid: prev.railway?.mermaid ?? "",
              final_recommendation: prev.railway?.final_recommendation ?? "",
            },
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
        setDone(true);
      }
    });
    return cleanup;
  }, [caseId]);

  // Narration + phase-transition pump. Walks only new events since the last
  // render to avoid re-narrating on every update.
  useEffect(() => {
    for (let i = lastProcessedRef.current; i < events.length; i++) {
      const ev = events[i];
      const phrase = EVENT_NARRATION[ev.kind];
      if (phrase && !firedMilestones.has(ev.kind)) {
        setFiredMilestones((prev) => {
          const next = new Set(prev);
          next.add(ev.kind);
          return next;
        });
        stageRef.current?.speak(phrase).catch(() => {});
      }
      if (ev.kind === "done" || ev.kind === "stream_end") {
        setPhase("ready");
      }
    }
    lastProcessedRef.current = events.length;
  }, [events, firedMilestones]);

  const handleBegin = useCallback(async () => {
    await stageRef.current?.start();
    // Fire-and-forget: SDK queues speak calls sequentially.
    stageRef.current?.speak(GREETING).catch(() => {});
    setPhase("intake");
    stageRef.current?.speak(INTAKE_PROMPT).catch(() => {});
  }, []);

  const handleUploaded = useCallback(
    (newCaseId: string) => {
      setCaseId(newCaseId);
      setPhase("processing");
      stageRef.current?.speak(UPLOAD_ACK).catch(() => {});
      router.replace(`/?case=${newCaseId}`, { scroll: false });
    },
    [router],
  );

  const processingState: ProcessingState = useMemo(
    () => ({ extractProgress, extractFeed, firedMilestones, currentStage }),
    [extractProgress, extractFeed, firedMilestones, currentStage],
  );

  const effectiveCase = caseData ?? (caseId ? emptyCase(caseId) : null);

  return (
    <div
      className={`h-screen w-screen overflow-hidden grid ${
        phase === "ready"
          ? "lg:grid-cols-[minmax(0,1.5fr)_minmax(380px,1fr)] grid-cols-1"
          : "grid-cols-1"
      }`}
    >
      <div className="relative h-full w-full">
        <AvatarStage
          ref={stageRef}
          onStatusChange={setAvatarStatus}
          compact={phase === "ready"}
        >
          {phase === "welcome" && (
            <WelcomeOverlay
              onBegin={handleBegin}
              busy={avatarStatus === "connecting"}
            />
          )}
          {phase === "intake" && <IntakeOverlay onUploaded={handleUploaded} />}
          {phase === "processing" && (
            <ProcessingOverlay state={processingState} />
          )}
        </AvatarStage>
      </div>

      {phase === "ready" && effectiveCase && (
        <ResultsSidebar
          caseData={effectiveCase}
          events={events}
          done={done}
          extractProgress={extractProgress}
          extractFeed={extractFeed}
        />
      )}
    </div>
  );
}
