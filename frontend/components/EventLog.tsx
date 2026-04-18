"use client";

// Pipeline events panel for the Clinical tab.
//
// Shows every event the backend EventBus has emitted for this case. Each row
// is collapsible: click it to reveal the full JSON payload. Rows are colored
// by category (milestone / error / normal / noisy) via a left-edge accent.
// Noisy token-delta events (thinking_delta, answer_delta, ping) are hidden
// by default and gated behind a toggle.

import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, EventKind } from "@/lib/types";

// Streaming-granular events. Useful for deep debugging but floods the log.
const NOISY: Set<EventKind> = new Set([
  "thinking_delta",
  "answer_delta",
  "chat_thinking_delta",
  "chat_answer_delta",
  "ping",
]);

// Events that mean a stage / phase completed successfully. Green accent.
const MILESTONE: Set<EventKind> = new Set([
  "pdf_extracted",
  "aggregation_done",
  "railway_ready",
  "trial_matches_ready",
  "trial_sites_ready",
  "done",
  "stream_end",
  "chat_done",
]);

// Something failed. Red accent.
const ERROR_KINDS: Set<EventKind> = new Set(["tool_error"]);

// Start / entry events. Navy accent.
const START_KINDS: Set<EventKind> = new Set([
  "aggregation_start",
  "tool_start",
  "chat_tool_call",
]);

function classifyKind(
  k: EventKind,
): "milestone" | "error" | "start" | "normal" {
  if (ERROR_KINDS.has(k)) return "error";
  if (MILESTONE.has(k)) return "milestone";
  if (START_KINDS.has(k)) return "start";
  return "normal";
}

function formatTime(ts: number): string {
  // Server timestamps are seconds; render HH:MM:SS.mmm.
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

function hasPayload(ev: AgentEvent): boolean {
  const p = ev.payload;
  if (!p) return false;
  if (typeof p !== "object") return false;
  return Object.keys(p).length > 0;
}

export function EventLog({ events }: { events: AgentEvent[] }) {
  const [showNoisy, setShowNoisy] = useState(false);
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return events.filter((e) => {
      if (!showNoisy && NOISY.has(e.kind)) return false;
      if (!q) return true;
      return (
        e.kind.toLowerCase().includes(q) ||
        (e.label || "").toLowerCase().includes(q)
      );
    });
  }, [events, filter, showNoisy]);

  // Auto-scroll to newest when the user hasn't scrolled away.
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [visible.length, autoScroll]);

  // Count per category for the header strip.
  const counts = useMemo(() => {
    const c = { milestone: 0, error: 0, start: 0, normal: 0 };
    for (const e of events) {
      if (NOISY.has(e.kind)) continue;
      c[classifyKind(e.kind)]++;
    }
    return c;
  }, [events]);

  return (
    <div className="card flex flex-col max-h-[32rem]">
      {/* Header */}
      <div className="border-b border-neutral-100 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3 text-xs">
          <span className="eyebrow">Pipeline events</span>
          <span className="text-neutral-500 tabular-nums">
            {visible.length} / {events.length}
          </span>
          {counts.milestone > 0 && (
            <span className="inline-flex items-center gap-1 text-emerald-700 tabular-nums">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              {counts.milestone}
            </span>
          )}
          {counts.error > 0 && (
            <span className="inline-flex items-center gap-1 text-red-700 tabular-nums">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {counts.error}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="search"
            placeholder="filter kind or label…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-xs border border-neutral-200 rounded px-2 py-1 w-44 focus:outline-none focus:border-black"
          />
          <label className="text-xs flex items-center gap-1 text-neutral-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showNoisy}
              onChange={(e) => setShowNoisy(e.target.checked)}
              className="accent-black"
            />
            noisy
          </label>
          <label className="text-xs flex items-center gap-1 text-neutral-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="accent-black"
            />
            auto-scroll
          </label>
        </div>
      </div>

      {/* Event list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto font-mono text-[11px] divide-y divide-neutral-100"
      >
        {visible.length === 0 && (
          <div className="px-3 py-4 text-neutral-500 text-xs">
            No events match the current filter.
          </div>
        )}
        {visible.map((e, i) => (
          <EventRow key={`${e.timestamp}-${i}`} event={e} />
        ))}
      </div>
    </div>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  const [open, setOpen] = useState(false);
  const category = classifyKind(event.kind);
  const expandable = hasPayload(event);

  const borderCls = {
    milestone: "border-l-emerald-500",
    error: "border-l-red-500",
    start: "border-l-brand-700",
    normal: "border-l-transparent",
  }[category];

  const kindCls = {
    milestone: "text-emerald-700",
    error: "text-red-700",
    start: "text-brand-700",
    normal: "text-black",
  }[category];

  return (
    <div className={`border-l-2 ${borderCls}`}>
      <button
        type="button"
        onClick={() => expandable && setOpen((v) => !v)}
        className={`w-full text-left flex gap-2 items-baseline px-3 py-1 hover:bg-neutral-50 transition ${
          expandable ? "cursor-pointer" : "cursor-default"
        }`}
      >
        <span className="text-neutral-400 shrink-0 tabular-nums">
          {formatTime(event.timestamp)}
        </span>
        <span className={`shrink-0 w-44 truncate font-semibold ${kindCls}`}>
          {event.kind}
        </span>
        <span className="flex-1 truncate text-neutral-700">{event.label}</span>
        {expandable && (
          <span className="text-neutral-400 shrink-0 w-4 text-center">
            {open ? "▾" : "▸"}
          </span>
        )}
      </button>
      {open && expandable && <PayloadView payload={event.payload} />}
    </div>
  );
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => {
    try {
      return JSON.stringify(payload, payloadReplacer, 2);
    } catch {
      return String(payload);
    }
  }, [payload]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="bg-neutral-50 border-t border-neutral-100 px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="eyebrow">Payload</span>
        <button
          type="button"
          onClick={copy}
          className="text-[10px] text-neutral-500 hover:text-black transition"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="text-[10px] leading-[1.5] text-neutral-700 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
        {text}
      </pre>
    </div>
  );
}

/**
 * Trim long string fields in payloads so a single pdf_extracted event doesn't
 * wall you with a 50k-char excerpt. Keeps full arrays and objects intact.
 */
function payloadReplacer(_key: string, value: unknown): unknown {
  if (typeof value === "string" && value.length > 400) {
    return value.slice(0, 400) + `… (${value.length - 400} more chars)`;
  }
  return value;
}
