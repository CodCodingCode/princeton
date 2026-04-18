"use client";

import type { AgentEvent } from "@/lib/types";

const NOISY = new Set(["thinking_delta", "answer_delta", "ping"]);

export function EventLog({ events }: { events: AgentEvent[] }) {
  const visible = events.filter((e) => !NOISY.has(e.kind));
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-3 text-xs font-mono max-h-56 overflow-y-auto">
      <div className="text-neutral-500 mb-1 uppercase tracking-widest font-sans">
        Pipeline events
      </div>
      {visible.slice(-30).map((e, i) => (
        <div key={i} className="flex gap-2 text-neutral-700">
          <span className="text-neutral-400 shrink-0">
            {new Date(e.timestamp * 1000).toLocaleTimeString()}
          </span>
          <span className="text-black shrink-0 w-36 truncate">{e.kind}</span>
          <span className="truncate">{e.label}</span>
        </div>
      ))}
    </div>
  );
}
