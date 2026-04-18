"use client";

import { useState } from "react";
import type { DocumentExtraction, ProvenanceEntry } from "@/lib/types";

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

  if (!documents.length) {
    return (
      <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-5 text-sm text-ink-400">
        Documents will appear here once the orchestrator starts extracting…
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

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest">
          Source documents ({documents.length})
        </h2>
        <span className="text-xs text-ink-500">
          {provenance.length} provenance entries
          {conflicts.length > 0 && (
            <span className="ml-3 text-amber-400">
              {conflicts.length} conflict{conflicts.length === 1 ? "" : "s"}
            </span>
          )}
        </span>
      </div>

      {conflicts.length > 0 && (
        <div className="mb-3 rounded-lg bg-amber-400/10 border border-amber-400/30 p-3 text-xs text-amber-200 space-y-1">
          {conflicts.map((c, i) => (
            <div key={i}>
              <span className="text-amber-400 mr-2">⚠</span>
              {c}
            </div>
          ))}
        </div>
      )}

      <div className="divide-y divide-ink-800">
        {documents.map((doc) => {
          const isOpen = open === doc.filename;
          const mutCount = doc.pages.reduce(
            (n, p) => n + p.mutations_text.length,
            0,
          );
          const provRows = provByFile[doc.filename] ?? [];
          return (
            <div key={doc.filename} className="py-2">
              <button
                onClick={() => setOpen(isOpen ? null : doc.filename)}
                className="w-full text-left flex items-start gap-3 hover:bg-ink-800/30 -mx-2 px-2 py-1 rounded"
              >
                <span className="text-teal-400 text-xs mt-0.5 shrink-0">
                  {isOpen ? "▾" : "▸"}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-mono text-ink-100 truncate">
                      {doc.filename}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-ink-800 text-ink-400">
                      {doc.document_kind}
                    </span>
                  </div>
                  <div className="text-xs text-ink-500 mt-0.5">
                    {doc.page_count} pages ·{" "}
                    {doc.used_vision_fallback ? "VLM vision" : "text-only"} ·{" "}
                    {mutCount} mutation mentions · {provRows.length} extracted
                    fields
                  </div>
                </div>
              </button>

              {isOpen && (
                <div className="mt-2 ml-5 space-y-3 text-xs">
                  {provRows.length > 0 && (
                    <div>
                      <div className="text-ink-500 uppercase tracking-wider mb-1">
                        Fields sourced from this document
                      </div>
                      <div className="space-y-0.5">
                        {provRows.map((p, i) => (
                          <div key={i} className="flex gap-2">
                            <span className="text-ink-400 w-40 shrink-0 truncate">
                              {p.field}
                            </span>
                            <span className="text-ink-200 flex-1">
                              {p.value}
                            </span>
                            {p.page_number && (
                              <span className="text-ink-500 shrink-0">
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
                      <div className="text-ink-500 uppercase tracking-wider mb-1">
                        Per-page VLM notes
                      </div>
                      <div className="space-y-0.5 max-h-48 overflow-y-auto">
                        {doc.pages.slice(0, 20).map((page) => (
                          <div
                            key={page.page_number}
                            className="flex gap-2 text-ink-300"
                          >
                            <span className="text-ink-500 w-14 shrink-0">
                              p.{page.page_number}
                            </span>
                            <span className="truncate">{page.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
