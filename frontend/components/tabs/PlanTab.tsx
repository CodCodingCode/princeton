"use client";

import type { PatientCase, RailwayStep } from "@/lib/types";
import { RailwayMermaid } from "@/components/RailwayMermaid";

export function PlanTab({ caseData }: { caseData: PatientCase }) {
  const mermaid = caseData.railway?.mermaid ?? "";
  const steps = caseData.railway?.steps ?? [];

  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
          Treatment railway
        </div>
        <p className="text-sm text-neutral-600 leading-relaxed mb-4">
          Four-phase dynamic railway grounded in phase-2+ trial literature. Ask
          the avatar to explain any branch.
        </p>
        <RailwayMermaid mermaidSource={mermaid} empty={!mermaid} />
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
        <div
          key={group.phaseId}
          className="rounded-xl border border-neutral-200 bg-white"
        >
          {group.phaseTitle && (
            <div className="px-3 py-2 border-b border-neutral-200 text-[11px] uppercase tracking-widest text-neutral-500 font-semibold">
              {group.phaseTitle}
            </div>
          )}
          <div className="divide-y divide-neutral-200">
            {group.steps.map((s) => (
              <details key={s.node_id} className="p-3 group">
                <summary className="cursor-pointer flex items-start gap-3 list-none">
                  <span className="text-xs font-mono text-neutral-500 shrink-0 w-32 truncate">
                    {s.node_id}
                  </span>
                  <div className="flex-1">
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
                  <span className="text-neutral-400 text-xs group-open:rotate-90 transition">
                    ▸
                  </span>
                </summary>
                {s.alternatives.length > 0 && (
                  <div className="mt-3 pl-36 space-y-1.5 text-xs">
                    {s.alternatives.map((a, i) => (
                      <div key={i}>
                        <span className="text-neutral-700">
                          {a.option_label}:
                        </span>{" "}
                        <span className="text-neutral-500">
                          {a.reason_not_chosen || "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {s.citations.length > 0 && (
                  <div className="mt-3 pl-36 space-y-1 text-xs">
                    {s.citations.map((c) => (
                      <a
                        key={c.pmid}
                        href={`https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`}
                        target="_blank"
                        rel="noreferrer"
                        className="block text-brand-700 hover:text-black underline decoration-neutral-300 hover:decoration-black truncate"
                      >
                        PMID {c.pmid} — {c.title}
                      </a>
                    ))}
                  </div>
                )}
              </details>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
