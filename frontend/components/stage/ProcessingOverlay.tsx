"use client";

import type { EventKind } from "@/lib/types";

export interface ProcessingState {
  extractProgress: { done: number; total: number; latest: string } | null;
  firedMilestones: Set<EventKind>;
  currentStage: string | null;
}

type RowStatus = "pending" | "active" | "done";

interface Row {
  key: string;
  label: string;
  status: RowStatus;
  detail?: string;
}

function deriveRows(s: ProcessingState): Row[] {
  const hasPdf = s.firedMilestones.has("pdf_extracted");
  const hasAggregate = s.firedMilestones.has("aggregation_done");
  const hasRailway = s.firedMilestones.has("railway_ready");
  const hasTrials = s.firedMilestones.has("trial_matches_ready");
  const hasSites = s.firedMilestones.has("trial_sites_ready");

  const extracting =
    !hasPdf &&
    s.extractProgress &&
    s.extractProgress.total > 0 &&
    s.extractProgress.done < s.extractProgress.total;

  const extractDetail = s.extractProgress
    ? `${s.extractProgress.done}/${s.extractProgress.total}`
    : undefined;

  return [
    {
      key: "read",
      label: "Reading records",
      status: hasPdf ? "done" : extracting ? "active" : "active",
      detail: hasPdf ? undefined : extractDetail,
    },
    {
      key: "reconcile",
      label: "Reconciling across documents",
      status: hasAggregate
        ? "done"
        : hasPdf
          ? "active"
          : s.currentStage === "2"
            ? "active"
            : "pending",
    },
    {
      key: "plan",
      label: "Walking the guidelines",
      status: hasRailway ? "done" : hasAggregate ? "active" : "pending",
    },
    {
      key: "trials",
      label: "Matching clinical trials",
      status:
        hasTrials && hasSites
          ? "done"
          : hasRailway || hasTrials
            ? "active"
            : "pending",
    },
  ];
}

export function ProcessingOverlay({ state }: { state: ProcessingState }) {
  const rows = deriveRows(state);

  return (
    <div className="absolute top-6 right-6 pointer-events-none">
      <div className="pointer-events-auto w-[320px] rounded-2xl bg-white/95 backdrop-blur shadow-2xl p-5">
        <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-500 font-semibold mb-3">
          Working on your case
        </div>
        <ul className="space-y-2.5">
          {rows.map((r) => (
            <li key={r.key} className="flex items-start gap-3">
              <StatusGlyph status={r.status} />
              <div className="flex-1 min-w-0">
                <div
                  className={`text-sm leading-snug ${
                    r.status === "pending"
                      ? "text-neutral-400"
                      : r.status === "active"
                        ? "text-black font-medium"
                        : "text-neutral-600"
                  }`}
                >
                  {r.label}
                </div>
                {r.detail && (
                  <div className="text-[11px] text-neutral-500 mt-0.5 tabular-nums">
                    {r.detail}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function StatusGlyph({ status }: { status: RowStatus }) {
  if (status === "done") {
    return (
      <span className="shrink-0 w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px]">
        ✓
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="shrink-0 w-5 h-5 rounded-full border-2 border-brand-700 border-t-transparent animate-spin" />
    );
  }
  return (
    <span className="shrink-0 w-5 h-5 rounded-full border border-neutral-300 bg-white" />
  );
}
