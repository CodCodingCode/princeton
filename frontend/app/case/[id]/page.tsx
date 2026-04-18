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
import { deriveTStage, toPatientFriendly } from "@/lib/plainEnglish";
import { RailwayMermaid } from "@/components/RailwayMermaid";
import { ExtractedFields } from "@/components/ExtractedFields";
import { TrialList } from "@/components/TrialList";
import { TrialMap } from "@/components/TrialMap";
import { ChatPanel } from "@/components/ChatPanel";
import { ReportButton } from "@/components/ReportButton";
import { EventLog } from "@/components/EventLog";
import { DocumentsPanel } from "@/components/DocumentsPanel";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;

  const [caseData, setCaseData] = useState<PatientCase | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const [selectedNct, setSelectedNct] = useState<string | null>(null);
  const [showClinician, setShowClinician] = useState(false);

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

  const friendly = useMemo(
    () => (caseData ? toPatientFriendly(caseData) : null),
    [caseData],
  );

  const statusLabel = useMemo(() => {
    if (!caseData) return "Loading…";
    if (done) return "Ready";
    if (caseData.trial_sites.length > 0) return "Locating trial sites…";
    if (caseData.trial_matches.length > 0) return "Matching trials…";
    if (caseData.railway?.steps.length) return "Planning your treatment…";
    if (caseData.documents.length > 0) return "Reading your records with AI…";
    return "Starting…";
  }, [caseData, done]);

  if (!caseData || !friendly) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 text-ink-400">
        Loading case {caseId}…
      </div>
    );
  }

  const tStage = deriveTStage(
    caseData.pathology.breslow_thickness_mm,
    caseData.pathology.ulceration,
  );

  return (
    <div className="px-4 py-3 max-w-[1400px] mx-auto flex flex-col gap-3 min-h-[calc(100vh-56px)]">
      {/* ── HERO ───────────────────────────────────────────── */}
      <section className="rounded-2xl border border-teal-400/30 bg-gradient-to-br from-teal-400/10 via-ink-900/80 to-ink-900/40 p-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-widest text-teal-400 mb-1">
            Case {caseId} ·{" "}
            <span
              className={done ? "text-emerald-400" : "text-teal-400 pulse-dot"}
            >
              {statusLabel}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight leading-tight">
            {friendly.diagnosisHeadline}
          </h1>
          <p className="text-ink-400 text-sm mt-1 max-w-2xl">
            {friendly.diagnosisDetails}
          </p>
        </div>
        <div className="shrink-0">
          <ReportButton caseId={caseId} enabled={done} />
        </div>
      </section>

      {/* ── MAIN GRID ─────────────────────────────────────── */}
      <section className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        {/* Recommended action */}
        <div className="col-span-12 md:col-span-4 rounded-2xl border border-teal-400/40 bg-teal-400/5 p-5 flex flex-col">
          <div className="text-[11px] uppercase tracking-widest text-teal-400 font-semibold mb-2">
            Recommended next step
          </div>
          <div className="text-lg font-medium leading-snug text-ink-100 mb-3">
            {friendly.recommendedAction}
          </div>
          <div className="text-sm text-ink-400 mb-4 leading-relaxed">
            <span className="text-ink-300 font-medium">Why: </span>
            {friendly.recommendedActionDetail}
          </div>

          {friendly.nextSteps.length > 0 && (
            <div className="mb-4">
              <div className="text-[11px] uppercase tracking-widest text-ink-500 mb-1">
                Plan at a glance
              </div>
              <ol className="text-sm text-ink-200 space-y-1">
                {friendly.nextSteps.map((s, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-teal-400 shrink-0">{i + 1}.</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <button
            disabled={!done}
            onClick={() => {
              // Placeholder — in production, hook into a scheduler.
              window.open(
                "https://www.cancer.net/find-a-cancer-doctor",
                "_blank",
              );
            }}
            className={`mt-auto w-full px-4 py-2.5 rounded-xl text-sm font-semibold transition ${
              done
                ? "bg-teal-500 hover:bg-teal-400 text-ink-950"
                : "bg-ink-800 text-ink-500 cursor-not-allowed"
            }`}
          >
            {friendly.ctaLabel}
          </button>
        </div>

        {/* About you */}
        <div className="col-span-12 md:col-span-4 rounded-2xl border border-ink-800 bg-ink-900/40 p-5 flex flex-col">
          <div className="text-[11px] uppercase tracking-widest text-teal-400 font-semibold mb-3">
            About you
          </div>
          <ul className="space-y-2.5 flex-1">
            {friendly.aboutYou.map((item, i) => (
              <li key={i}>
                <div className="text-[11px] uppercase tracking-wider text-ink-500">
                  {item.label}
                </div>
                <div className="text-sm text-ink-100 leading-snug">
                  {item.value}
                </div>
              </li>
            ))}
          </ul>
          {caseData.conflicts.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-400/10 border border-amber-400/30 p-2 text-xs text-amber-200">
              <span className="font-semibold">Worth reviewing:</span>{" "}
              {caseData.conflicts.length} fact
              {caseData.conflicts.length === 1 ? "" : "s"} disagreed between
              your documents.
            </div>
          )}
        </div>

        {/* Chat */}
        <div className="col-span-12 md:col-span-4 min-h-[24rem] md:min-h-0 flex flex-col">
          <ChatPanel caseId={caseId} />
        </div>
      </section>

      {/* ── TRIALS ROW ────────────────────────────────────── */}
      <section className="grid grid-cols-12 gap-3">
        <div className="col-span-12 lg:col-span-7">
          <div className="text-[11px] uppercase tracking-widest text-teal-400 font-semibold mb-2">
            Trials near you
          </div>
          <div className="text-sm text-ink-300 mb-2">{friendly.trialsCta}</div>
          <TrialMap
            sites={caseData.trial_sites}
            selected={selectedNct}
            onSelect={setSelectedNct}
          />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <div className="text-[11px] uppercase tracking-widest text-teal-400 font-semibold mb-2">
            Matching trials
          </div>
          <div className="max-h-80 overflow-y-auto pr-1">
            <TrialList
              matches={caseData.trial_matches}
              selected={selectedNct}
              onSelect={setSelectedNct}
            />
          </div>
        </div>
      </section>

      {/* ── CLINICIAN DRAWER ──────────────────────────────── */}
      <section>
        <button
          onClick={() => setShowClinician((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-ink-800 bg-ink-900/40 hover:border-ink-600 text-sm"
        >
          <span className="text-ink-300">
            <span className="text-teal-400 mr-2">⚕</span>
            Clinical detail for your oncologist — treatment railway, source
            documents, pipeline events
          </span>
          <span className="text-ink-500 text-xs">
            {showClinician ? "Hide" : "Show"}
          </span>
        </button>

        {showClinician && (
          <div className="mt-3 space-y-3">
            <ExtractedFields
              pathology={caseData.pathology}
              intake={caseData.intake}
              enrichment={caseData.enrichment}
              mutations={caseData.mutations}
              primaryCancerType={caseData.primary_cancer_type}
              tStage={tStage}
            />

            <div>
              <div className="text-xs uppercase tracking-widest text-teal-400 mb-2">
                Treatment railway (4 phases, phase-2+ trial-grounded)
              </div>
              <RailwayMermaid
                mermaidSource={caseData.railway?.mermaid ?? ""}
                empty={!caseData.railway?.mermaid}
              />
              {(caseData.railway?.steps?.length ?? 0) > 0 && (
                <RailwayStepsTable steps={caseData.railway!.steps} />
              )}
            </div>

            <DocumentsPanel
              documents={caseData.documents}
              provenance={caseData.provenance}
              conflicts={caseData.conflicts}
            />

            <EventLog events={events} />
          </div>
        )}
      </section>
    </div>
  );
}

function RailwayStepsTable({ steps }: { steps: RailwayStep[] }) {
  // Group steps by phase while preserving declaration order.
  const grouped: {
    phaseId: string;
    phaseTitle: string;
    steps: RailwayStep[];
  }[] = [];
  for (const s of steps) {
    const pid = s.phase_id || "main";
    const title = s.phase_title || "";
    const last = grouped[grouped.length - 1];
    if (last && last.phaseId === pid) {
      last.steps.push(s);
    } else {
      grouped.push({ phaseId: pid, phaseTitle: title, steps: [s] });
    }
  }

  return (
    <div className="mt-2 space-y-3">
      {grouped.map((group) => (
        <div
          key={group.phaseId}
          className="rounded-xl border border-ink-800 bg-ink-900/40"
        >
          {group.phaseTitle && (
            <div className="px-3 py-2 border-b border-ink-800 text-[11px] uppercase tracking-widest text-teal-400 font-semibold">
              {group.phaseTitle}
            </div>
          )}
          <div className="divide-y divide-ink-800">
            {group.steps.map((s) => (
              <details key={s.node_id} className="p-3 group">
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
        </div>
      ))}
    </div>
  );
}
