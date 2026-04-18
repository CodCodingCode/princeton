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
import { RailwayMermaid } from "@/components/RailwayMermaid";
import { ExtractedFields } from "@/components/ExtractedFields";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";
import { ChatPanel } from "@/components/ChatPanel";
import { ReportButton } from "@/components/ReportButton";
import { EventLog } from "@/components/EventLog";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;

  const [caseData, setCaseData] = useState<PatientCase | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const [selectedNct, setSelectedNct] = useState<string | null>(null);

  // Initial snapshot
  useEffect(() => {
    let cancelled = false;
    fetchCase(caseId)
      .then((c) => !cancelled && setCaseData(c))
      .catch((e) => console.error("fetchCase", e));
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // Live event stream
  useEffect(() => {
    const cleanup = subscribeCaseEvents(caseId, (ev) => {
      setEvents((prev) => [...prev, ev]);

      if (ev.kind === "case_update") {
        setCaseData(ev.payload as unknown as PatientCase);
      } else if (ev.kind === "pdf_extracted") {
        setCaseData((prev) => {
          const next = prev ? { ...prev } : null;
          if (!next) return prev;
          // Narrow: payload carries pathology, intake, mutations (typed on backend).
          const p = ev.payload as Record<string, unknown>;
          if (p.pathology)
            next.pathology = p.pathology as PatientCase["pathology"];
          if (p.intake) next.intake = p.intake as PatientCase["intake"];
          if (p.mutations)
            next.mutations = p.mutations as PatientCase["mutations"];
          return next;
        });
      } else if (ev.kind === "railway_step") {
        setCaseData((prev) => {
          if (!prev) return prev;
          const step = (ev.payload as { step: RailwayStep }).step;
          const existing = prev.railway?.steps ?? [];
          // Replace-or-append by node_id
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

  const statusLabel = useMemo(() => {
    if (!caseData) return "Loading…";
    if (done) return "Complete";
    if (caseData.trial_sites.length > 0) return "Geocoding trials…";
    if (caseData.trial_matches.length > 0) return "Matching trials…";
    if (caseData.railway?.steps.length) return "Walking NCCN railway…";
    if (caseData.mutations.length > 0) return "Railway walker ready…";
    return "Extracting PDF…";
  }, [caseData, done]);

  if (!caseData) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 text-ink-400">
        Loading case {caseId}…
      </div>
    );
  }

  const tStage = caseData.pathology.breslow_thickness_mm
    ? deriveTStage(
        caseData.pathology.breslow_thickness_mm,
        caseData.pathology.ulceration,
      )
    : "Tx";

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-widest text-ink-500 mb-1">
            Case · {caseId}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {caseData.final_recommendation || "Walking treatment railway…"}
          </h1>
          <div
            className={`mt-1 text-sm ${done ? "text-emerald-400" : "text-teal-400 pulse-dot"}`}
          >
            {statusLabel}
          </div>
        </div>
        <ReportButton caseId={caseId} enabled={done} />
      </div>

      <ExtractedFields
        pathology={caseData.pathology}
        intake={caseData.intake}
        mutations={caseData.mutations}
        tStage={tStage}
      />

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest">
            NCCN treatment railway
          </h2>
          {caseData.railway?.steps && (
            <span className="text-xs text-ink-500">
              {caseData.railway.steps.length} nodes ·{" "}
              {caseData.railway.steps.reduce(
                (n, s) => n + s.alternatives.length,
                0,
              )}{" "}
              sibling options
            </span>
          )}
        </div>
        <RailwayMermaid
          mermaidSource={caseData.railway?.mermaid ?? ""}
          empty={!caseData.railway?.mermaid}
        />
        {caseData.railway?.steps && caseData.railway.steps.length > 0 && (
          <RailwayStepsTable steps={caseData.railway.steps} />
        )}
      </section>

      <section className="grid md:grid-cols-5 gap-6">
        <div className="md:col-span-3 space-y-4">
          <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest">
            Matched trials
          </h2>
          <TrialList
            matches={caseData.trial_matches}
            selected={selectedNct}
            onSelect={setSelectedNct}
          />
        </div>
        <div className="md:col-span-2">
          <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest mb-4">
            Trial sites
          </h2>
          <TrialMap
            sites={caseData.trial_sites}
            selected={selectedNct}
            onSelect={setSelectedNct}
          />
        </div>
      </section>

      <section className="grid md:grid-cols-2 gap-6">
        <ChatPanel caseId={caseId} />
        <EventLog events={events} />
      </section>
    </div>
  );
}

function RailwayStepsTable({ steps }: { steps: RailwayStep[] }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 divide-y divide-ink-800">
      {steps.map((s) => (
        <details key={s.node_id} className="p-4 group">
          <summary className="cursor-pointer flex items-start gap-3 list-none">
            <span className="text-xs font-mono text-teal-400 shrink-0 w-32 truncate">
              {s.node_id}
            </span>
            <div className="flex-1">
              <div className="text-sm text-ink-100">
                {s.title}
                {!s.is_terminal && (
                  <span className="text-teal-400">
                    {" "}
                    → {s.chosen_option_label}
                  </span>
                )}
              </div>
              {s.chosen_rationale && (
                <div className="text-xs text-ink-400 mt-0.5">
                  {s.chosen_rationale}
                </div>
              )}
            </div>
            <span className="text-ink-500 text-xs group-open:rotate-90 transition">
              ▸
            </span>
          </summary>
          {s.alternatives.length > 0 && (
            <div className="mt-3 pl-36 space-y-1.5 text-xs">
              {s.alternatives.map((a, i) => (
                <div key={i}>
                  <span className="text-ink-300">{a.option_label}:</span>{" "}
                  <span className="text-ink-500">
                    {a.reason_not_chosen || "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
          {s.citations.length > 0 && (
            <div className="mt-3 pl-36 space-y-1 text-xs">
              {s.citations.map((c) => (
                <a
                  key={c.pmid}
                  href={`https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-teal-400 hover:text-teal-300 truncate"
                >
                  PMID {c.pmid} — {c.title}
                </a>
              ))}
            </div>
          )}
        </details>
      ))}
    </div>
  );
}

function deriveTStage(breslow: number, ulceration: boolean | null): string {
  const u = !!ulceration;
  if (breslow < 0.8 && !u) return "T1a";
  if (breslow < 1.0) return "T1b";
  if (breslow < 2.0) return u ? "T2b" : "T2a";
  if (breslow < 4.0) return u ? "T3b" : "T3a";
  return u ? "T4b" : "T4a";
}
