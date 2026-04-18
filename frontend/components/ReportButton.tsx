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
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition ${
        enabled
          ? "bg-black hover:bg-neutral-800 text-white shadow-sm"
          : "bg-neutral-100 text-neutral-400 cursor-not-allowed pointer-events-none"
      }`}
    >
      <span>Download oncologist report</span>
      <span aria-hidden>↓</span>
    </a>
  );
}
