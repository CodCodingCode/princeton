"use client";

import { useEffect, useMemo, useRef } from "react";
import type { PatientCase } from "@/lib/types";
import { toPatientFriendly } from "@/lib/plainEnglish";
import type { ExtractFeedEntry, ExtractProgress } from "../CaseTabs";

function fmtBytes(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function OverviewTab({
  caseData,
  extractProgress,
  extractFeed,
}: {
  caseData: PatientCase;
  extractProgress?: ExtractProgress | null;
  extractFeed?: ExtractFeedEntry[];
}) {
  const friendly = useMemo(() => toPatientFriendly(caseData), [caseData]);
  const extracting =
    !!extractProgress &&
    extractProgress.total > 0 &&
    extractProgress.done < extractProgress.total;
  const feedRef = useRef<HTMLDivElement | null>(null);

  // Collapse the flat start/done event stream into per-file rows so each file
  // gets its own progress bar (indeterminate while in-flight, filled when done).
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
    for (const entry of extractFeed ?? []) {
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
    // Keep stable order by first-seen time.
    return Array.from(map.values()).sort((a, b) => a.startedAt - b.startedAt);
  }, [extractFeed]);

  useEffect(() => {
    // Auto-scroll the feed so the newest in-flight row is always visible.
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [fileRows.length, extractProgress?.done]);

  const overallPct =
    extractProgress && extractProgress.total > 0
      ? Math.round((extractProgress.done / extractProgress.total) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {extracting && fileRows.length > 0 && (
        <section className="rounded-2xl border border-neutral-200 bg-neutral-50 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[11px] uppercase tracking-widest text-neutral-600 font-semibold flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-black opacity-40" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-black" />
              </span>
              Extracting your uploaded documents
            </div>
            <div className="text-[11px] tabular-nums text-neutral-500">
              {extractProgress!.done}/{extractProgress!.total} · {overallPct}%
            </div>
          </div>

          {/* Overall bar across all files */}
          <div className="h-1.5 w-full bg-neutral-200 rounded-full overflow-hidden mb-4">
            <div
              className="h-full bg-black transition-[width] duration-300"
              style={{ width: `${overallPct}%` }}
            />
          </div>

          {/* Per-file rows — each with its own bar */}
          <div
            ref={feedRef}
            className="max-h-64 overflow-y-auto space-y-2 pr-1"
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
                    <span className="tabular-nums text-neutral-500 shrink-0">
                      {isDone ? (
                        <>
                          <span className="text-emerald-700 mr-1">done</span>
                          {row.chars ? `${row.chars} chars` : ""}
                          {elapsedMs
                            ? ` · ${(elapsedMs / 1000).toFixed(1)}s`
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
                    <div className="h-1 w-full rounded-full bg-emerald-500/80" />
                  ) : (
                    <div className="h-1 w-full rounded-full bar-indeterminate" />
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Diagnosis summary */}
      <section>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Diagnosis
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-black leading-tight">
          {friendly.diagnosisHeadline}
        </h2>
        <p className="text-sm text-neutral-600 mt-2 leading-relaxed">
          {friendly.diagnosisDetails}
        </p>
      </section>

      {/* Recommended next step */}
      <section className="rounded-2xl border border-neutral-200 p-5">
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Recommended next step
        </div>
        <div className="text-base font-medium text-black leading-snug mb-2">
          {friendly.recommendedAction}
        </div>
        <div className="text-sm text-neutral-600 leading-relaxed mb-4">
          <span className="text-black font-medium">Why: </span>
          {friendly.recommendedActionDetail}
        </div>

        {friendly.nextSteps.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-1">
              Plan at a glance
            </div>
            <ol className="text-sm text-neutral-800 space-y-1">
              {friendly.nextSteps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-neutral-400 shrink-0 tabular-nums">
                    {i + 1}.
                  </span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      {/* About you */}
      <section>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-3">
          About you
        </div>
        <ul className="space-y-3">
          {friendly.aboutYou.map((item, i) => (
            <li
              key={i}
              className="border-b border-neutral-100 pb-2 last:border-none"
            >
              <div className="text-[11px] uppercase tracking-wider text-neutral-500">
                {item.label}
              </div>
              <div className="text-sm text-black leading-snug mt-0.5">
                {item.value}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {caseData.conflicts.length > 0 && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
          <span className="font-semibold">Worth reviewing:</span>{" "}
          {caseData.conflicts.length} fact
          {caseData.conflicts.length === 1 ? "" : "s"} disagreed between your
          documents — see the Documents tab.
        </div>
      )}
    </div>
  );
}
