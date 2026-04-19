"use client";

// Processing-phase overlay. Floats in the top-right of the avatar stage
// while the pipeline runs. Matches the app's light theme: solid white card,
// single navy accent, eyebrow labels, no glass or color saturation.

import { useEffect, useMemo, useRef } from "react";
import type { EventKind } from "@/lib/types";
import type { ExtractFeedEntry } from "@/components/CaseTabs";

export interface StageLogEntry {
  stage: string;
  phase: "start" | "done" | "fail";
  message: string;
  seconds?: number;
  at: number;
}

export interface ProcessingState {
  extractProgress: { done: number; total: number; latest: string } | null;
  extractFeed?: ExtractFeedEntry[];
  firedMilestones: Set<EventKind>;
  currentStage: string | null;
  stageLog?: StageLogEntry[];
}

type RowStatus = "pending" | "active" | "done";

interface Row {
  key: string;
  label: string;
  status: RowStatus;
  detail?: string;
  progress?: { done: number; total: number; pct: number };
}

function stageBody(message: string): string {
  const m = message.match(/·\s+(.+)$/);
  return m ? m[1] : message;
}

function fmtBytes(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function deriveRows(s: ProcessingState): Row[] {
  const hasPdf = s.firedMilestones.has("pdf_extracted");
  const hasAggregate = s.firedMilestones.has("aggregation_done");
  const hasRailway = s.firedMilestones.has("railway_ready");
  const hasTrials = s.firedMilestones.has("trial_matches_ready");
  const hasSites = s.firedMilestones.has("trial_sites_ready");

  const extractDetail = s.extractProgress
    ? `${s.extractProgress.done}/${s.extractProgress.total} files`
    : undefined;

  const readProgress =
    !hasPdf && s.extractProgress && s.extractProgress.total > 0
      ? {
          done: s.extractProgress.done,
          total: s.extractProgress.total,
          pct: Math.round(
            (s.extractProgress.done / s.extractProgress.total) * 100,
          ),
        }
      : undefined;

  return [
    {
      key: "read",
      label: "Reading records",
      status: hasPdf ? "done" : "active",
      detail: hasPdf ? undefined : extractDetail,
      progress: readProgress,
    },
    {
      key: "reconcile",
      label: "Reconciling across documents",
      status: hasAggregate ? "done" : hasPdf ? "active" : "pending",
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

  const overallExtractPct = state.extractProgress?.total
    ? Math.round(
        (state.extractProgress.done / state.extractProgress.total) * 100,
      )
    : 0;

  // Overall pipeline progress: % of steps completed, with a soft credit for
  // the currently-active step's sub-progress when available.
  const overallPct = useMemo(() => {
    const done = rows.filter((r) => r.status === "done").length;
    const activeIndex = rows.findIndex((r) => r.status === "active");
    const activeSub = rows[activeIndex]?.progress?.pct ?? 0;
    const active = activeIndex >= 0 ? activeSub / 100 : 0;
    return Math.round(((done + active) / rows.length) * 100);
  }, [rows]);

  const doneCount = rows.filter((r) => r.status === "done").length;
  const currentStepNumber = Math.min(doneCount + 1, rows.length);

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
    <div className="absolute top-24 right-6 pointer-events-none">
      <div className="pointer-events-auto w-[360px] rounded-2xl border border-neutral-200 bg-white shadow-sm overflow-hidden scan-line">
        {/* ── Header ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-brand-700 animate-breathe" />
            <span className="eyebrow">Onkos · Processing</span>
          </div>
          <span className="font-mono text-[10px] tabular-nums text-neutral-500">
            <span className="text-black">
              {String(currentStepNumber).padStart(2, "0")}
            </span>
            <span className="text-neutral-300 mx-0.5">/</span>
            <span>{String(rows.length).padStart(2, "0")}</span>
          </span>
        </div>

        {/* ── Overall ruler ────────────────────────────────────────── */}
        <div className="px-5 pb-4">
          <div className="h-[2px] w-full rounded-full bg-neutral-200 overflow-hidden">
            <div
              className="h-full bg-black transition-[width] duration-500 ease-out"
              style={{ width: `${overallPct}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span className="eyebrow">Analysis progress</span>
            <span className="font-mono text-[10px] tabular-nums text-black">
              {overallPct}%
            </span>
          </div>
        </div>

        {/* ── Step rail ────────────────────────────────────────────── */}
        <div className="px-5 pb-4">
          <ul className="space-y-3">
            {rows.map((r) => (
              <StepRow key={r.key} row={r} />
            ))}
          </ul>
        </div>

        {/* ── Pipeline log ─────────────────────────────────────────── */}
        {state.stageLog && state.stageLog.length > 0 && (
          <div className="border-t border-neutral-100 px-5 py-3">
            <div className="flex items-center justify-between mb-2">
              <span className="eyebrow">Activity</span>
              <span className="font-mono text-[10px] tabular-nums text-neutral-400">
                {state.stageLog.length} events
              </span>
            </div>
            <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
              {state.stageLog.slice(-6).map((e, i) => (
                <div
                  key={`${e.stage}-${e.phase}-${e.at}-${i}`}
                  className="flex items-center gap-2 text-[11px] leading-snug"
                >
                  <LogGlyph phase={e.phase} />
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-neutral-400">
                    {e.stage.padStart(2, "0")}
                  </span>
                  <span className="flex-1 min-w-0 truncate text-neutral-700">
                    {stageBody(e.message)}
                  </span>
                  {typeof e.seconds === "number" && (
                    <span className="shrink-0 font-mono text-[10px] tabular-nums text-neutral-500">
                      {e.seconds.toFixed(1)}s
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Live extraction feed ─────────────────────────────────── */}
        {extracting && fileRows.length > 0 && (
          <div className="border-t border-neutral-100 px-5 py-3">
            <div className="flex items-center justify-between mb-2">
              <span className="eyebrow">Reading documents</span>
              <span className="font-mono text-[10px] tabular-nums text-neutral-500">
                <span className="text-black">
                  {state.extractProgress!.done}
                </span>
                <span className="text-neutral-300 mx-0.5">/</span>
                {state.extractProgress!.total}
                <span className="text-neutral-300 mx-1.5">·</span>
                {overallExtractPct}%
              </span>
            </div>
            <div
              ref={feedRef}
              className="max-h-44 overflow-y-auto space-y-2 pr-1"
            >
              {fileRows.map((row) => {
                const isDone = row.status === "done";
                const elapsedMs = isDone
                  ? (row.finishedAt ?? row.startedAt) - row.startedAt
                  : 0;
                return (
                  <div key={row.filename} className="space-y-1">
                    <div className="flex items-center gap-2 text-[11px]">
                      <span className="flex-1 min-w-0 truncate text-neutral-700">
                        {row.filename}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] tabular-nums">
                        {isDone ? (
                          <span className="text-neutral-500">
                            Done
                            {elapsedMs
                              ? ` · ${(elapsedMs / 1000).toFixed(1)}s`
                              : ""}
                          </span>
                        ) : (
                          <span className="text-brand-700">
                            Reading
                            {row.bytes ? ` · ${fmtBytes(row.bytes)}` : ""}
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="h-[2px] w-full rounded-full bg-neutral-200 overflow-hidden">
                      {isDone ? (
                        <div className="h-full w-full bg-black" />
                      ) : (
                        <div className="h-full w-full bar-indeterminate" />
                      )}
                    </div>
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

// ── Step row: rail glyph vertically centered with the label ──────────
function StepRow({ row }: { row: Row }) {
  const labelCls =
    row.status === "pending"
      ? "text-neutral-400"
      : row.status === "active"
        ? "text-black font-medium"
        : "text-neutral-700";

  return (
    <li>
      <div className="flex items-center gap-3">
        <StepGlyph status={row.status} />
        <span className={`flex-1 min-w-0 text-[13px] leading-snug ${labelCls}`}>
          {row.label}
        </span>
        <StepStatusChip status={row.status} detail={row.detail} />
      </div>
      {row.progress ? (
        <div className="mt-2 pl-[22px]">
          <div className="h-[2px] w-full rounded-full bg-neutral-200 overflow-hidden">
            <div
              className="h-full bg-brand-700 transition-[width] duration-300"
              style={{ width: `${row.progress.pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="font-mono text-[10px] tabular-nums text-neutral-500">
              {row.progress.done}/{row.progress.total}
            </span>
            <span className="font-mono text-[10px] tabular-nums text-black">
              {row.progress.pct}%
            </span>
          </div>
        </div>
      ) : null}
    </li>
  );
}

// ── Step glyph: fixed 10×10 box, dot vertically centered with the label
function StepGlyph({ status }: { status: RowStatus }) {
  return (
    <span className="shrink-0 w-2.5 h-2.5 flex items-center justify-center">
      {status === "done" ? (
        <span className="w-2.5 h-2.5 rounded-full bg-black" />
      ) : status === "active" ? (
        <span className="relative w-2.5 h-2.5 flex items-center justify-center">
          <span className="absolute inset-0 rounded-full border-[1.5px] border-brand-700 border-t-transparent animate-spin" />
          <span className="w-1 h-1 rounded-full bg-brand-700" />
        </span>
      ) : (
        <span className="w-2 h-2 rounded-full border border-neutral-300 bg-white" />
      )}
    </span>
  );
}

// ── Status chip on the right of each step row ──────────────────────────
function StepStatusChip({
  status,
  detail,
}: {
  status: RowStatus;
  detail?: string;
}) {
  if (status === "done") {
    return (
      <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.18em] text-neutral-500">
        complete
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.18em] text-brand-700">
        {detail ?? "live"}
      </span>
    );
  }
  return (
    <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.18em] text-neutral-400">
      queued
    </span>
  );
}

// ── Pipeline log glyph: mono directional markers ──────────────────────
function LogGlyph({ phase }: { phase: "start" | "done" | "fail" }) {
  if (phase === "done") {
    return (
      <span className="shrink-0 w-3 text-center text-black font-mono text-[11px] leading-none">
        ✓
      </span>
    );
  }
  if (phase === "fail") {
    return (
      <span className="shrink-0 w-3 text-center text-black font-mono text-[11px] leading-none">
        ✗
      </span>
    );
  }
  return (
    <span className="shrink-0 w-3 text-center text-brand-700 font-mono text-[11px] leading-none">
      ▸
    </span>
  );
}
