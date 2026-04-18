"use client";

import { reportUrl } from "@/lib/api";

export function ReportButton({
  caseId,
  enabled,
}: {
  caseId: string;
  enabled: boolean;
}) {
  return (
    <a
      href={enabled ? reportUrl(caseId) : undefined}
      target="_blank"
      rel="noreferrer"
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
        enabled
          ? "bg-brand-700 hover:bg-brand-900 text-white"
          : "bg-neutral-100 text-neutral-400 cursor-not-allowed pointer-events-none"
      }`}
    >
      <span>Download oncologist report</span>
      <span aria-hidden>↓</span>
    </a>
  );
}
