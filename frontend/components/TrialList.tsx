"use client";

import { useMemo } from "react";
import type { TrialMatch, TrialSite } from "@/lib/types";
import { type UserLocation, formatMiles, nearestSite } from "@/lib/geo";

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

// Primary sort: eligibility tier (eligible > need-more > unscored > ineligible).
// Secondary sort: distance to nearest site when userLocation is set, otherwise
// NCT ID for determinism.
const STATUS_ORDER: Record<string, number> = {
  eligible: 0,
  needs_more_data: 1,
  unscored: 2,
  ineligible: 3,
};

interface Props {
  matches: TrialMatch[];
  sites: TrialSite[];
  selected: string | null;
  onSelect: (nct: string | null) => void;
  userLocation: UserLocation | null;
}

export function TrialList({
  matches,
  sites,
  selected,
  onSelect,
  userLocation,
}: Props) {
  // Group sites by NCT once so per-match lookup is O(1).
  const sitesByNct = useMemo(() => {
    const m = new Map<string, TrialSite[]>();
    for (const s of sites) {
      const arr = m.get(s.nct_id) ?? [];
      arr.push(s);
      m.set(s.nct_id, arr);
    }
    return m;
  }, [sites]);

  const ranked = useMemo(() => {
    const decorated = matches.map((m) => {
      const nearest = nearestSite(userLocation, sitesByNct.get(m.nct_id) ?? []);
      return { match: m, nearest };
    });
    decorated.sort((a, b) => {
      const sa = STATUS_ORDER[a.match.status] ?? 9;
      const sb = STATUS_ORDER[b.match.status] ?? 9;
      if (sa !== sb) return sa - sb;
      const da = a.nearest?.miles ?? Number.POSITIVE_INFINITY;
      const db = b.nearest?.miles ?? Number.POSITIVE_INFINITY;
      if (da !== db) return da - db;
      return a.match.nct_id.localeCompare(b.match.nct_id);
    });
    return decorated;
  }, [matches, sitesByNct, userLocation]);

  if (!matches.length) {
    return (
      <div className="card p-5 text-neutral-500 text-sm">
        Trials will appear here once the analysis finishes.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {ranked.map(({ match: m, nearest }) => {
        const active = selected === m.nct_id;
        return (
          <button
            key={m.nct_id}
            onClick={() => onSelect(active ? null : m.nct_id)}
            className={`w-full text-left rounded-2xl border p-4 transition ${
              active
                ? "border-black bg-white shadow-sm"
                : "border-neutral-200 bg-white hover:border-neutral-400"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mono-tag mb-1 ">
                  {m.nct_id}
                  {m.is_regeneron && (
                    <span className="ml-2 text-neutral-500">· Regeneron</span>
                  )}
                  {!m.is_regeneron && m.sponsor && m.sponsor !== "Unknown" && (
                    <span className="ml-2 text-neutral-500">· {m.sponsor}</span>
                  )}
                </div>
                <div className="text-sm text-black leading-snug">{m.title}</div>
                {m.phase && <div className="meta mt-0.5">{m.phase}</div>}
                {nearest && (
                  <div className="mt-1 text-[11px] text-neutral-600 tabular-nums">
                    Nearest site: {nearest.site.city}
                    {nearest.site.state ? `, ${nearest.site.state}` : ""}
                    <span className="text-neutral-400"> · </span>
                    <span className="text-black font-medium">
                      {formatMiles(nearest.miles)}
                    </span>
                  </div>
                )}
              </div>
              <span
                className={`px-2 py-0.5 rounded-full border text-[11px] font-medium whitespace-nowrap ${STATUS_STYLES[m.status] ?? STATUS_STYLES.unscored}`}
              >
                {STATUS_LABEL[m.status] ?? m.status}
              </span>
            </div>

            <div
              className={`grid transition-all duration-300 ease-out ${
                active
                  ? "grid-rows-[1fr] opacity-100 mt-3"
                  : "grid-rows-[0fr] opacity-0 mt-0"
              }`}
            >
              <div className="overflow-hidden min-h-0">
                <div className="text-xs space-y-2">
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
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
