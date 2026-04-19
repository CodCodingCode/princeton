"use client";

import { reportUrl } from "@/lib/api";
import { buttonClasses } from "@/components/ui/Button";

export function ReportButton({
  caseId,
  enabled,
}: {
  caseId: string;
  enabled: boolean;
}) {
  const extra = enabled
    ? "shadow-sm"
    : "pointer-events-none opacity-40 cursor-not-allowed";
  return (
    <a
      href={enabled ? reportUrl(caseId) : undefined}
      target="_blank"
      rel="noreferrer"
      className={buttonClasses("primary", "md", extra)}
    >
      <span>Download oncologist report</span>
      <span aria-hidden>↓</span>
    </a>
  );
}
