"use client";

import type { TrialMatch } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  eligible: "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
  needs_more_data: "bg-amber-400/15 text-amber-300 border-amber-400/30",
  ineligible: "bg-red-400/15 text-red-300 border-red-400/30",
  unscored: "bg-ink-700 text-ink-300 border-ink-600",
};

const STATUS_LABEL: Record<string, string> = {
  eligible: "Eligible",
  needs_more_data: "Need more data",
  ineligible: "Not eligible",
  unscored: "Not scored",
};

export function TrialList({
  matches,
  selected,
  onSelect,
}: {
  matches: TrialMatch[];
  selected: string | null;
  onSelect: (nct: string | null) => void;
}) {
  if (!matches.length) {
    return (
      <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-6 text-ink-400 text-sm">
        Trials will appear here once the NCCN walker finishes…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {matches.map((m) => {
        const active = selected === m.nct_id;
        return (
          <button
            key={m.nct_id}
            onClick={() => onSelect(active ? null : m.nct_id)}
            className={`w-full text-left rounded-xl border p-4 transition ${
              active
                ? "border-teal-400 bg-teal-400/5"
                : "border-ink-800 bg-ink-900/40 hover:border-ink-600"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-mono text-teal-400 mb-1">
                  {m.nct_id}
                  {m.is_regeneron && (
                    <span className="ml-2 text-ink-400">· Regeneron</span>
                  )}
                </div>
                <div className="text-sm text-ink-100 leading-snug">
                  {m.title}
                </div>
                {m.phase && (
                  <div className="text-xs text-ink-400 mt-0.5">{m.phase}</div>
                )}
              </div>
              <span
                className={`px-2 py-0.5 rounded-md border text-xs whitespace-nowrap ${STATUS_STYLES[m.status] ?? STATUS_STYLES.unscored}`}
              >
                {STATUS_LABEL[m.status] ?? m.status}
              </span>
            </div>

            {active && (
              <div className="mt-3 text-xs space-y-2">
                {m.passing_criteria.length > 0 && (
                  <div>
                    <span className="text-emerald-400">Passing:</span>{" "}
                    <span className="text-ink-300">
                      {m.passing_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.failing_criteria.length > 0 && (
                  <div>
                    <span className="text-red-400">Failing:</span>{" "}
                    <span className="text-ink-300">
                      {m.failing_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.unknown_criteria.length > 0 && (
                  <div>
                    <span className="text-amber-400">Need more data:</span>{" "}
                    <span className="text-ink-300">
                      {m.unknown_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.url && (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-teal-400 hover:text-teal-300 underline"
                  >
                    ClinicalTrials.gov →
                  </a>
                )}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
