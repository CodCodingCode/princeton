"use client";

import { useEffect, useMemo, useRef } from "react";
import type { EventKind } from "@/lib/types";
import type { ExtractFeedEntry } from "@/components/CaseTabs";

export interface ProcessingState {
  extractProgress: { done: number; total: number; latest: string } | null;
  extractFeed?: ExtractFeedEntry[];
  firedMilestones: Set<EventKind>;
  currentStage: string | null;
}

function fmtBytes(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
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
  const extracting =
    !!state.extractProgress &&
    state.extractProgress.total > 0 &&
    state.extractProgress.done < state.extractProgress.total;
  const overallPct = state.extractProgress?.total
    ? Math.round(
        (state.extractProgress.done / state.extractProgress.total) * 100,
      )
    : 0;

  // Fold the flat start/done event stream into per-file rows.
  const fileRows = useMemo(() => {
    const map = new Map<
      string,
      {
        filename: string;
        bytes?: number;
        chars?: number;
        status: "extracting" | "done";
        startedAt: number;
        finishedAt?: number;
      }
    >();
    for (const entry of state.extractFeed ?? []) {
      const existing = map.get(entry.filename);
      if (entry.kind === "start") {
        if (!existing) {
          map.set(entry.filename, {
            filename: entry.filename,
            bytes: entry.bytes,
            status: "extracting",
            startedAt: entry.ts,
          });
        }
      } else {
        map.set(entry.filename, {
          filename: entry.filename,
          bytes: existing?.bytes ?? entry.bytes,
          chars: entry.chars,
          status: "done",
          startedAt: existing?.startedAt ?? entry.ts,
          finishedAt: entry.ts,
        });
      }
    }
    return Array.from(map.values()).sort((a, b) => a.startedAt - b.startedAt);
  }, [state.extractFeed]);

  const feedRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [fileRows.length, state.extractProgress?.done]);

  return (
    <div className="absolute top-6 right-6 pointer-events-none">
      <div className="pointer-events-auto w-[360px] rounded-2xl bg-white/95 backdrop-blur shadow-2xl p-5">
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

        {extracting && fileRows.length > 0 && (
          <div className="mt-4 pt-4 border-t border-neutral-200">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 font-semibold">
                Reading files
              </div>
              <div className="text-[11px] tabular-nums text-neutral-500">
                {state.extractProgress!.done}/{state.extractProgress!.total} ·{" "}
                {overallPct}%
              </div>
            </div>
            <div className="h-1.5 w-full bg-neutral-200 rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-black transition-[width] duration-300"
                style={{ width: `${overallPct}%` }}
              />
            </div>
            <div
              ref={feedRef}
              className="max-h-52 overflow-y-auto space-y-2 pr-1"
            >
              {fileRows.map((row) => {
                const isDone = row.status === "done";
                const elapsedMs = isDone
                  ? (row.finishedAt ?? row.startedAt) - row.startedAt
                  : 0;
                return (
                  <div key={row.filename} className="text-[11px]">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="truncate font-mono text-neutral-800">
                        {row.filename}
                      </span>
                      <span className="tabular-nums text-neutral-500 shrink-0 text-[10px]">
                        {isDone ? (
                          <>
                            <span className="text-emerald-700 mr-1">done</span>
                            {elapsedMs
                              ? `${(elapsedMs / 1000).toFixed(1)}s`
                              : ""}
                          </>
                        ) : (
                          <>
                            <span className="text-black mr-1">reading…</span>
                            {row.bytes ? fmtBytes(row.bytes) : ""}
                          </>
                        )}
                      </span>
                    </div>
                    {isDone ? (
                      <div className="h-[3px] w-full rounded-full bg-emerald-500/80" />
                    ) : (
                      <div className="h-[3px] w-full rounded-full bar-indeterminate" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
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
