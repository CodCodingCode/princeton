"use client";

import { useMemo, useState } from "react";
import type { PatientCase, RailwayStep } from "@/lib/types";
import { RailwayChart } from "@/components/RailwayChart";
import { toPatientFriendly } from "@/lib/plainEnglish";

// Never let the final-recommendation strip render empty or show a raw
// placeholder like "Needs clinician review". Priority:
//   1. Backend-composed railway recommendation (skip placeholders).
//   2. Top-level case.final_recommendation.
//   3. toPatientFriendly().recommendedAction as a derived fallback.
//   4. Generic hand-off so the strip always has substance.
const PLACEHOLDER_TOKENS = [
  "needs clinician review",
  "needs more data",
  "pending",
];

function isPlaceholder(s: string): boolean {
  const lower = s.trim().toLowerCase();
  if (!lower) return true;
  return PLACEHOLDER_TOKENS.some(
    (p) => lower === p || lower.endsWith(`: ${p}`),
  );
}

export function PlanTab({ caseData }: { caseData: PatientCase }) {
  const steps = caseData.railway?.steps ?? [];
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);

  const finalRec = useMemo(() => {
    const candidates = [
      caseData.railway?.final_recommendation,
      caseData.final_recommendation,
      friendly.recommendedAction,
    ];
    for (const c of candidates) {
      if (c && !isPlaceholder(c)) return c;
    }
    return "Refer to medical oncology for guideline-directed treatment planning and clinical-trial screening.";
  }, [caseData, friendly.recommendedAction]);

  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow mb-2">Treatment plan</div>
        <p className="text-sm text-neutral-600 leading-relaxed mb-4">
          Four-phase plan grounded in current oncology-guideline and
          clinical-trial literature. Ask the avatar to explain any branch.
        </p>
        <RailwayChart
          steps={steps}
          finalRecommendation={finalRec}
          empty={!steps.length}
        />
      </div>

      {steps.length > 0 && <RailwayStepsTable steps={steps} />}
    </div>
  );
}

function RailwayStepsTable({ steps }: { steps: RailwayStep[] }) {
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
    <div className="space-y-3">
      {grouped.map((group) => (
        <div key={group.phaseId} className="card">
          {group.phaseTitle && (
            <div className="eyebrow px-4 py-2.5 border-b border-neutral-100">
              {group.phaseTitle}
            </div>
          )}
          <div className="divide-y divide-neutral-100">
            {group.steps.map((s) => (
              <StepRow key={s.node_id} step={s} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Per-row collapsible with the same expand/collapse animation TrialList uses
// (`grid` + `grid-rows-[0fr]/[1fr]` + `overflow-hidden`). `<details>` would be
// simpler but the native disclosure widget doesn't animate, which made the
// Plan tab look inconsistent next to the Trials tab.
function StepRow({ step: s }: { step: RailwayStep }) {
  const [open, setOpen] = useState(false);
  const hasExpandable = s.alternatives.length > 0 || s.citations.length > 0;

  return (
    <div className="p-3">
      <button
        type="button"
        onClick={() => hasExpandable && setOpen((v) => !v)}
        disabled={!hasExpandable}
        className="w-full text-left flex items-start gap-3 cursor-pointer disabled:cursor-default"
      >
        <span className="text-xs font-mono text-neutral-500 shrink-0 w-32 ">
          {s.node_id.replace(/_/g, " ")}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-black">
            {s.title}
            {!s.is_terminal && (
              <span className="text-neutral-600">
                {" "}
                → {s.chosen_option_label}
              </span>
            )}
          </div>
          {s.chosen_rationale && (
            <div className="text-xs text-neutral-600 mt-0.5">
              {s.chosen_rationale}
            </div>
          )}
        </div>
        {hasExpandable && (
          <span
            className={`text-neutral-400 text-xs transition-transform duration-300 ${
              open ? "rotate-90" : "rotate-0"
            }`}
          >
            ▸
          </span>
        )}
      </button>

      {hasExpandable && (
        <div
          className={`grid transition-all duration-300 ease-out ${
            open
              ? "grid-rows-[1fr] opacity-100 mt-3"
              : "grid-rows-[0fr] opacity-0 mt-0"
          }`}
        >
          <div className="overflow-hidden min-h-0">
            <div className="pl-36 space-y-3 text-xs">
              {s.alternatives.length > 0 && (
                <div className="space-y-1.5">
                  {s.alternatives.map((a, i) => (
                    <div key={i}>
                      <span className="text-neutral-700">
                        {a.option_label}:
                      </span>{" "}
                      <span className="text-neutral-500">
                        {a.reason_not_chosen || "-"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {s.citations.length > 0 && (
                <div className="space-y-1">
                  {s.citations.map((c) => (
                    <a
                      key={c.pmid}
                      href={`https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`}
                      target="_blank"
                      rel="noreferrer"
                      className="block text-brand-700 hover:text-black underline decoration-neutral-300 hover:decoration-black "
                    >
                      PMID {c.pmid} · {c.title}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
