"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { subscribeCaseEvents, fetchCase } from "@/lib/api";
import type {
  AgentEvent,
  PatientCase,
  RailwayMap,
  RailwayStep,
  TrialMatch,
  TrialSite,
} from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";
import { AvatarPanel } from "@/components/AvatarPanel";
import { CaseTabs } from "@/components/CaseTabs";
import { ReportButton } from "@/components/ReportButton";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;

  const [caseData, setCaseData] = useState<PatientCase | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const [extractProgress, setExtractProgress] = useState<{
    done: number;
    total: number;
    latest: string;
  } | null>(null);
  const [currentStage, setCurrentStage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCase(caseId)
      .then((c) => !cancelled && setCaseData(c))
      .catch((e) => console.error("fetchCase", e));
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  useEffect(() => {
    const cleanup = subscribeCaseEvents(caseId, (ev) => {
      setEvents((prev) => [...prev, ev]);

      // Track extraction progress & current stage for the status strip.
      const payload = ev.payload as Record<string, unknown> | undefined;
      const phase = payload?.phase as string | undefined;
      const stage = payload?.stage as string | undefined;
      if (stage && phase === "start") setCurrentStage(stage);
      if (phase === "extract_start") {
        const total = Number(payload?.total ?? 0);
        setExtractProgress({ done: 0, total, latest: "" });
      } else if (phase === "extract_progress") {
        setExtractProgress({
          done: Number(payload?.done ?? 0),
          total: Number(payload?.total ?? 0),
          latest: String(payload?.filename ?? ""),
        });
      }

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

  // Fall back to an empty-case stub so the cockpit shell renders immediately
  // even when the backend is unreachable or still spinning up. The tabs each
  // handle empty arrays gracefully, and the AvatarPanel has no case deps.
  const effectiveCase = caseData ?? emptyCase(caseId);
  const friendly = useMemo(
    () => toPatientFriendly(effectiveCase),
    [effectiveCase],
  );

  const statusLabel = useMemo(() => {
    if (done) return "Ready";
    if (
      extractProgress &&
      extractProgress.total > 0 &&
      extractProgress.done < extractProgress.total
    ) {
      return `Reading records · ${extractProgress.done}/${extractProgress.total}`;
    }
    if (!caseData) return "Waiting for backend…";
    if (caseData.trial_sites.length > 0) return "Locating trial sites…";
    if (caseData.trial_matches.length > 0) return "Matching trials…";
    if (caseData.railway?.steps.length) return "Planning your treatment…";
    if (currentStage === "2") return "Reconciling your records…";
    if (caseData.documents.length > 0) return "Reading your records…";
    return "Starting…";
  }, [caseData, done, extractProgress, currentStage]);

  const extractPct = extractProgress?.total
    ? Math.round((extractProgress.done / extractProgress.total) * 100)
    : 0;

  return (
    <div className="flex flex-col h-[calc(100vh-65px)]">
      {/* Compact case strip */}
      <header className="border-b border-neutral-200 bg-white px-6 py-3 flex items-center justify-between gap-4 shrink-0">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-semibold flex items-center gap-2">
            <span>Case {caseId}</span>
            <span className="text-neutral-300">·</span>
            <span
              className={done ? "text-emerald-600" : "text-black pulse-dot"}
            >
              {statusLabel}
            </span>
          </div>
          <h1 className="text-lg md:text-xl font-semibold tracking-tight text-black truncate">
            {friendly.diagnosisHeadline}
          </h1>
        </div>
        <div className="shrink-0">
          <ReportButton caseId={caseId} enabled={done} />
        </div>
      </header>

      {/* Extraction progress bar — visible while stage 1 is running */}
      {extractProgress &&
        extractProgress.total > 0 &&
        extractProgress.done < extractProgress.total && (
          <div className="border-b border-neutral-200 bg-neutral-50 px-6 py-2 shrink-0">
            <div className="flex items-center justify-between gap-4 text-[11px] text-neutral-600 mb-1">
              <span className="truncate">
                Reading {extractProgress.done} of {extractProgress.total}{" "}
                records
                {extractProgress.latest ? ` · ${extractProgress.latest}` : ""}
              </span>
              <span className="tabular-nums text-neutral-500 shrink-0">
                {extractPct}%
              </span>
            </div>
            <div className="h-1 w-full bg-neutral-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-black transition-[width] duration-300"
                style={{ width: `${extractPct}%` }}
              />
            </div>
          </div>
        )}

      {/* Cockpit split — avatar dominates, tabs beside it */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] min-h-0">
        <AvatarPanel />
        <CaseTabs caseData={effectiveCase} events={events} />
      </div>
    </div>
  );
}

function emptyCase(caseId: string): PatientCase {
  return {
    case_id: caseId,
    pathology: {
      primary_cancer_type: "unknown",
      histology: "",
      primary_site: "",
      melanoma_subtype: "unknown",
      breslow_thickness_mm: null,
      ulceration: null,
      mitotic_rate_per_mm2: null,
      tils_present: "",
      pdl1_estimate: "",
      lag3_ihc_percent: null,
      confidence: 0,
      notes: "",
    },
    primary_cancer_type: "unknown",
    intake: {
      ecog: null,
      lag3_ihc_percent: null,
      measurable_disease_recist: null,
      life_expectancy_months: null,
      prior_systemic_therapy: null,
      prior_anti_pd1: null,
      ajcc_stage: null,
      age_years: null,
    },
    enrichment: null,
    mutations: [],
    documents: [],
    provenance: [],
    conflicts: [],
    pdf_text_excerpt: "",
    railway: null,
    trial_matches: [],
    trial_sites: [],
    final_recommendation: "",
  };
}
