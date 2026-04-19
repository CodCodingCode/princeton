"use client";

import { Fragment, useMemo, useState } from "react";
import type {
  DocumentExtraction,
  PageFinding,
  ProvenanceEntry,
} from "@/lib/types";
import {
  cleanConflicts,
  documentDisplayName,
  documentKindLabel,
} from "@/lib/plainEnglish";

// Per-page field names we count as a "mention" when they're non-null.
// Excludes mutations_text (counted separately as mutation mentions) and
// narrative fields (description, notes).
const STRUCTURED_FIELDS: Array<keyof PageFinding> = [
  "primary_cancer_type",
  "histology",
  "primary_site",
  "melanoma_subtype",
  "breslow_thickness_mm",
  "ulceration",
  "mitotic_rate_per_mm2",
  "tils_present",
  "pdl1_estimate",
  "lag3_ihc_percent",
  "ajcc_stage",
  "age_years",
  "ecog",
  "measurable_disease_recist",
  "life_expectancy_months",
  "prior_systemic_therapy",
  "prior_anti_pd1",
];

const FIELD_LABEL: Partial<Record<keyof PageFinding, string>> = {
  primary_cancer_type: "Primary cancer",
  histology: "Histology",
  primary_site: "Primary site",
  melanoma_subtype: "Melanoma subtype",
  breslow_thickness_mm: "Breslow thickness",
  ulceration: "Ulceration",
  mitotic_rate_per_mm2: "Mitoses per mm²",
  tils_present: "TILs",
  pdl1_estimate: "PD-L1",
  lag3_ihc_percent: "LAG-3 IHC",
  ajcc_stage: "AJCC stage",
  age_years: "Age",
  ecog: "ECOG",
  measurable_disease_recist: "Measurable (RECIST)",
  life_expectancy_months: "Life expectancy",
  prior_systemic_therapy: "Prior systemic therapy",
  prior_anti_pd1: "Prior anti-PD-1",
};

function isPresent(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === "string") {
    const s = v.trim().toLowerCase();
    return s !== "" && s !== "unknown" && s !== "none";
  }
  return true;
}

function formatFieldValue(key: keyof PageFinding, v: unknown): string {
  if (v === true) return "Yes";
  if (v === false) return "No";
  if (typeof v === "number") {
    if (key === "breslow_thickness_mm") return `${v} mm`;
    if (key === "lag3_ihc_percent") return `${v}%`;
    if (key === "life_expectancy_months") return `${v} months`;
    return String(v);
  }
  if (typeof v === "string") {
    return v.replace(/_/g, " ");
  }
  return String(v);
}

function countFieldsOnPage(page: PageFinding): number {
  let n = 0;
  for (const k of STRUCTURED_FIELDS) {
    if (isPresent((page as unknown as Record<string, unknown>)[k])) n++;
  }
  return n;
}

export function DocumentsPanel({
  documents,
  provenance,
  conflicts,
}: {
  documents: DocumentExtraction[];
  provenance: ProvenanceEntry[];
  conflicts: string[];
}) {
  const [open, setOpen] = useState<string | null>(null);

  // Filter out any technical/error strings that may have been persisted
  // into the conflicts list by an older pipeline run (cached cases). Only
  // real clinical disagreements should reach the UI.
  const visibleConflicts = useMemo(
    () => cleanConflicts(conflicts),
    [conflicts],
  );

  if (!documents.length) {
    return (
      <div className="card p-5 text-sm text-neutral-600">
        Documents will appear here once analysis begins.
      </div>
    );
  }

  const provByFile = provenance.reduce<Record<string, ProvenanceEntry[]>>(
    (acc, p) => {
      (acc[p.filename] ??= []).push(p);
      return acc;
    },
    {},
  );

  // Precompute a friendly display name for each doc: "Pathology report", or
  // "Pathology report 2" when several of the same kind were uploaded.
  const displayNames = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const d of documents) {
      totals[d.document_kind] = (totals[d.document_kind] ?? 0) + 1;
    }
    const seen: Record<string, number> = {};
    const out: Record<string, string> = {};
    for (const d of documents) {
      const idx = seen[d.document_kind] ?? 0;
      seen[d.document_kind] = idx + 1;
      out[d.filename] = documentDisplayName(
        d.document_kind,
        idx,
        totals[d.document_kind] ?? 1,
      );
    }
    return out;
  }, [documents]);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="eyebrow">Source documents ({documents.length})</h2>
        <span className="meta">
          {provenance.length} field{provenance.length === 1 ? "" : "s"} sourced
          {visibleConflicts.length > 0 && (
            <span className="ml-3 text-amber-700">
              {visibleConflicts.length} conflict
              {visibleConflicts.length === 1 ? "" : "s"}
            </span>
          )}
        </span>
      </div>

      {visibleConflicts.length > 0 && (
        <div className="mb-3 rounded-2xl bg-amber-50 border border-amber-200 p-4 text-xs text-amber-800 space-y-1">
          {visibleConflicts.map((c, i) => (
            <div key={i}>
              <span className="text-amber-700 mr-2">⚠</span>
              {c}
            </div>
          ))}
        </div>
      )}

      <div className="divide-y divide-neutral-100">
        {documents.map((doc) => {
          const isOpen = open === doc.filename;
          const mutCount = doc.pages.reduce(
            (n, p) => n + p.mutations_text.length,
            0,
          );
          const fieldMentions = doc.pages.reduce(
            (n, p) => n + countFieldsOnPage(p),
            0,
          );
          const provRows = provByFile[doc.filename] ?? [];
          const summaryChunks: string[] = [
            `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}`,
            doc.used_vision_fallback ? "Vision read" : "Text-only",
          ];
          if (fieldMentions > 0)
            summaryChunks.push(
              `${fieldMentions} field mention${fieldMentions === 1 ? "" : "s"}`,
            );
          if (mutCount > 0)
            summaryChunks.push(
              `${mutCount} mutation mention${mutCount === 1 ? "" : "s"}`,
            );
          if (provRows.length > 0)
            summaryChunks.push(`${provRows.length} used in record`);
          if (fieldMentions === 0 && mutCount === 0 && provRows.length === 0)
            summaryChunks.push("no structured data");
          return (
            <div key={doc.filename} className="py-2">
              <button
                onClick={() => setOpen(isOpen ? null : doc.filename)}
                className="w-full text-left flex items-start gap-3 hover:bg-neutral-50 -mx-2 px-2 py-1 rounded"
              >
                <span className="text-neutral-500 text-xs mt-0.5 shrink-0">
                  {isOpen ? "▾" : "▸"}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-black break-words">
                      {displayNames[doc.filename] ??
                        documentKindLabel(doc.document_kind)}
                    </span>
                  </div>
                  <div className="text-xs text-neutral-500 mt-0.5">
                    {summaryChunks.join(" · ")}
                  </div>
                  <div className="text-[10px] font-mono text-neutral-400 mt-0.5 break-all">
                    {doc.filename}
                  </div>
                </div>
              </button>

              <div
                className={`grid transition-all duration-300 ease-out ${
                  isOpen
                    ? "grid-rows-[1fr] opacity-100 mt-2"
                    : "grid-rows-[0fr] opacity-0 mt-0"
                }`}
              >
                <div className="overflow-hidden min-h-0">
                  <div className="ml-5 space-y-3 text-xs">
                    {provRows.length > 0 && (
                      <div>
                        <div className="eyebrow mb-1">Source of record</div>
                        <p className="text-[11px] text-neutral-500 mb-1">
                          These fields were taken from this document when the
                          record was assembled.
                        </p>
                        <div className="space-y-0.5">
                          {provRows.map((p, i) => (
                            <div key={i} className="flex gap-2">
                              <span className="text-neutral-500 w-40 shrink-0 break-words">
                                {p.field}
                              </span>
                              <span className="text-black flex-1">
                                {p.value}
                              </span>
                              {p.page_number && (
                                <span className="text-neutral-400 shrink-0">
                                  page {p.page_number}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {doc.pages.length > 0 && (
                      <div>
                        <div className="eyebrow mb-1">
                          What we read per page
                        </div>
                        <div
                          className={`space-y-3 ${
                            isOpen
                              ? "max-h-96 overflow-y-auto"
                              : "overflow-hidden"
                          }`}
                        >
                          {doc.pages.slice(0, 20).map((page) => {
                            const entries: Array<{
                              label: string;
                              value: string;
                            }> = [];
                            for (const k of STRUCTURED_FIELDS) {
                              const v = (
                                page as unknown as Record<string, unknown>
                              )[k];
                              if (isPresent(v)) {
                                entries.push({
                                  label: FIELD_LABEL[k] ?? k,
                                  value: formatFieldValue(k, v),
                                });
                              }
                            }
                            return (
                              <div
                                key={page.page_number}
                                className="border-l-2 border-neutral-200 pl-3"
                              >
                                <div className="flex items-baseline justify-between">
                                  <span className="text-neutral-500 font-mono shrink-0">
                                    p.{page.page_number}
                                  </span>
                                  <span className="text-[10px] text-neutral-400 tabular-nums">
                                    {entries.length} field
                                    {entries.length === 1 ? "" : "s"}
                                    {page.mutations_text.length > 0 &&
                                      ` · ${page.mutations_text.length} mut`}
                                  </span>
                                </div>
                                {page.description && (
                                  <div className="text-neutral-700 mt-0.5 break-words">
                                    {page.description}
                                  </div>
                                )}
                                {entries.length > 0 && (
                                  <div className="mt-1 grid grid-cols-[10rem_1fr] gap-x-2 gap-y-0.5">
                                    {entries.map((e, i) => (
                                      <Fragment key={i}>
                                        <span className="text-neutral-500">
                                          {e.label}
                                        </span>
                                        <span className="text-black break-words">
                                          {e.value}
                                        </span>
                                      </Fragment>
                                    ))}
                                  </div>
                                )}
                                {page.mutations_text.length > 0 && (
                                  <div className="mt-1 flex flex-wrap gap-1">
                                    {page.mutations_text.map((mt, i) => (
                                      <span
                                        key={i}
                                        className="inline-block px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-700 font-mono text-[10px]"
                                      >
                                        {mt}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {page.notes && (
                                  <div className="mt-1 text-neutral-500 italic break-words">
                                    {page.notes}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
