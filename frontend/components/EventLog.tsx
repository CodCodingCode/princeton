"use client";

import type { AgentEvent } from "@/lib/types";

const NOISY = new Set(["thinking_delta", "answer_delta", "ping"]);

export function EventLog({ events }: { events: AgentEvent[] }) {
  const visible = events.filter((e) => !NOISY.has(e.kind));
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-3 text-xs font-mono max-h-56 overflow-y-auto">
      <div className="text-ink-500 mb-1">Pipeline events</div>
      {visible.slice(-30).map((e, i) => (
        <div key={i} className="flex gap-2 text-ink-300">
          <span className="text-ink-500 shrink-0">
            {new Date(e.timestamp * 1000).toLocaleTimeString()}
          </span>
          <span className="text-teal-400 shrink-0 w-36 truncate">{e.kind}</span>
          <span className="truncate">{e.label}</span>
        </div>
      ))}
    </div>
  );
}
