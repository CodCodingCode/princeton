"use client";

// Treatment-railway chart. Replaces the Mermaid diagram, which rendered
// off-center with overlapping text and looked out of place in a clinician
// cockpit. This custom component renders the phase sequence as swim-lane
// columns of step cards with a clear "chosen vs. rejected" visual language:
//
//   * mono micro-labels for node_id + counters (bio-/pharma-dashboard feel)
//   * thin black left-bar accent for the chosen option
//   * muted, strike-through chips for alternatives (× not-chosen)
//   * dashed vertical divider between phases, round chevron joiner at the top
//   * a final-recommendation strip pinned to the bottom of the card
//
// The same step data drives the RailwayStepsTable below the chart for
// drilldown with citations, rationale, and alternative reasons.

import type { RailwayStep } from "@/lib/types";

interface PhaseGroup {
  id: string;
  title: string;
  steps: RailwayStep[];
}

function groupByPhase(steps: RailwayStep[]): PhaseGroup[] {
  const phases: PhaseGroup[] = [];
  for (const s of steps) {
    const id = s.phase_id || "main";
    const title = s.phase_title || "";
    const last = phases[phases.length - 1];
    if (last && last.id === id) {
      last.steps.push(s);
    } else {
      phases.push({ id, title, steps: [s] });
    }
  }
  return phases;
}

export function RailwayChart({
  steps,
  finalRecommendation,
  empty,
}: {
  steps: RailwayStep[];
  finalRecommendation?: string;
  empty?: boolean;
}) {
  if (empty || !steps.length) {
    return (
      <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50/60 p-10 text-center">
        <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-400 font-semibold mb-2">
          Treatment plan
        </div>
        <div className="text-sm text-neutral-500">
          Your treatment plan will appear here once the analysis finishes.
        </div>
      </div>
    );
  }

  const phases = groupByPhase(steps);

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white overflow-hidden shadow-sm">
      {/* Header strip - mono meta row, biotech-dashboard feel */}
      <div className="flex items-baseline justify-between px-5 py-3 border-b border-neutral-100 bg-neutral-50/50">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.3em] text-neutral-600 font-semibold">
            Treatment plan
          </span>
        </div>
        <div className="text-[10px] tabular-nums text-neutral-500 font-mono">
          {phases.length} PHASE{phases.length === 1 ? "" : "S"} · {steps.length}{" "}
          STEP{steps.length === 1 ? "" : "S"}
        </div>
      </div>

      {/* Phase swim-lanes */}
      <div className="overflow-x-auto">
        <div
          className="grid gap-0 p-5 min-w-max md:min-w-0"
          style={{
            gridTemplateColumns: `repeat(${phases.length}, minmax(240px, 1fr))`,
          }}
        >
          {phases.map((p, i) => (
            <PhaseColumn
              key={`${p.id}-${i}`}
              phase={p}
              index={i}
              last={i === phases.length - 1}
            />
          ))}
        </div>
      </div>

      {/* Final recommendation strip */}
      {finalRecommendation && (
        <div className="border-t border-neutral-100 bg-gradient-to-b from-neutral-50/60 to-white px-5 py-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-block h-px w-6 bg-black" />
            <span className="text-[10px] uppercase tracking-[0.3em] text-neutral-600 font-semibold">
              Final recommendation
            </span>
          </div>
          <div className="text-sm text-black leading-snug pl-8">
            {finalRecommendation}
          </div>
        </div>
      )}
    </div>
  );
}

function PhaseColumn({
  phase,
  index,
  last,
}: {
  phase: PhaseGroup;
  index: number;
  last: boolean;
}) {
  return (
    <div
      className={`relative px-3 ${
        !last ? "border-r border-dashed border-neutral-200" : ""
      }`}
    >
      {/* Phase header - phase number then title, nothing else, so the row
          reads as a clean 1/2/3/4 sequence across the top of the chart. The
          per-phase step count was removed because placed next to the phase
          number it made the headers scan as "1 3 2 2 3 2" instead of the
          intended 1/2/3/4 sequence. Total-step count already lives in the
          chart header strip. */}
      <div className="flex items-baseline gap-2 mb-4 pb-2 border-b border-neutral-100">
        <span className="font-mono text-[10px] tabular-nums text-neutral-400 font-semibold">
          {index + 1}
        </span>
        <span className="text-[10px] uppercase tracking-[0.22em] text-neutral-700 font-semibold">
          {phase.title || phase.id.replace(/_/g, " ")}
        </span>
      </div>

      {/* Step cards with vertical connectors */}
      <div>
        {phase.steps.map((s, i) => (
          <div key={s.node_id}>
            <StepCard step={s} />
            {i < phase.steps.length - 1 && <StepConnector />}
          </div>
        ))}
      </div>

      {/* Phase-to-phase chevron joiner on the right edge, level with headers */}
      {!last && (
        <div
          aria-hidden
          className="absolute top-3 -right-3 z-10 h-6 w-6 rounded-full bg-white border border-neutral-200 flex items-center justify-center text-neutral-500 text-[11px] shadow-sm"
        >
          →
        </div>
      )}
    </div>
  );
}

function StepCard({ step }: { step: RailwayStep }) {
  const citeCount = step.citations?.length ?? 0;

  return (
    <div className="group rounded-xl border border-neutral-200 bg-white p-3.5 hover:border-neutral-400 hover:shadow-sm transition">
      {/* Monospace node_id strip - the "chip" that anchors the card */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] font-mono uppercase tracking-[0.15em] text-neutral-400 ">
          {step.node_id.replace(/_/g, " ")}
        </span>
        {step.is_terminal && (
          <span className="text-[9px] font-mono uppercase tracking-[0.15em] text-emerald-600 font-semibold">
            END
          </span>
        )}
      </div>

      {/* Step question / title */}
      <div className="text-[12px] text-neutral-600 leading-snug mb-3 break-words">
        {step.title}
      </div>

      {/* Chosen option - left-bar accent */}
      <div className="border-l-2 border-black pl-2.5">
        <div className="text-[9px] uppercase tracking-[0.2em] text-neutral-500 font-semibold mb-0.5">
          {step.is_terminal ? "Outcome" : "Chosen"}
        </div>
        <div className="text-[13px] text-black font-medium leading-snug break-words">
          {step.chosen_option_label || "-"}
        </div>
      </div>

      {/* Citation footer */}
      {citeCount > 0 && (
        <div className="mt-2.5 pt-2 border-t border-neutral-100 flex items-center justify-between">
          <span className="text-[9px] font-mono uppercase tracking-[0.15em] text-neutral-500">
            Evidence
          </span>
          <span className="text-[9px] font-mono tabular-nums text-neutral-500">
            {citeCount} CITE{citeCount === 1 ? "" : "S"}
          </span>
        </div>
      )}
    </div>
  );
}

function StepConnector() {
  return (
    <div aria-hidden className="flex justify-center py-1.5">
      <span className="block w-px h-4 bg-neutral-300" />
    </div>
  );
}
