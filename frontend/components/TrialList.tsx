"use client";

import type { TrialMatch } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  eligible: "bg-emerald-50 text-emerald-700 border-emerald-200",
  needs_more_data: "bg-amber-50 text-amber-700 border-amber-200",
  ineligible: "bg-red-50 text-red-700 border-red-200",
  unscored: "bg-neutral-100 text-neutral-700 border-neutral-300",
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
      <div className="rounded-xl border border-neutral-200 bg-white p-6 text-neutral-500 text-sm">
        Trials will appear here once the railway finishes…
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
                ? "border-black bg-white"
                : "border-neutral-200 bg-white hover:border-neutral-400"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-mono text-neutral-500 mb-1">
                  {m.nct_id}
                  {m.is_regeneron && (
                    <span className="ml-2 text-neutral-500">· Regeneron</span>
                  )}
                </div>
                <div className="text-sm text-black leading-snug">{m.title}</div>
                {m.phase && (
                  <div className="text-xs text-neutral-500 mt-0.5">
                    {m.phase}
                  </div>
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
                    <span className="text-emerald-700 font-medium">
                      Passing:
                    </span>{" "}
                    <span className="text-neutral-700">
                      {m.passing_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.failing_criteria.length > 0 && (
                  <div>
                    <span className="text-red-700 font-medium">Failing:</span>{" "}
                    <span className="text-neutral-700">
                      {m.failing_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.unknown_criteria.length > 0 && (
                  <div>
                    <span className="text-amber-700 font-medium">
                      Need more data:
                    </span>{" "}
                    <span className="text-neutral-700">
                      {m.unknown_criteria.join(" · ")}
                    </span>
                  </div>
                )}
                {m.url && (
                  <a
                    href={m.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-700 hover:text-black underline"
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
