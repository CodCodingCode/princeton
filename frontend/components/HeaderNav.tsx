"use client";

// Client-side nav for the fixed header. Knows about pathname + searchParams
// so it can swap a "Patient view" / "Clinician view" toggle on top of the
// always-visible "New case" CTA.

import { useSearchParams, usePathname } from "next/navigation";
import { buttonClasses } from "@/components/ui/Button";

export function HeaderNav() {
  const pathname = usePathname();
  const params = useSearchParams();
  const caseId = params.get("case");

  const onPatient = pathname?.startsWith("/patient");
  const toggleHref = caseId
    ? onPatient
      ? `/?case=${caseId}`
      : `/patient?case=${caseId}`
    : null;
  const toggleLabel = onPatient ? "Clinician view" : "Patient view";

  return (
    <nav className="flex items-center gap-4 mr-16">
      {toggleHref && (
        <a href={toggleHref} className={buttonClasses("secondary", "md")}>
          {toggleLabel}
          <span aria-hidden className="text-base leading-none">
            →
          </span>
        </a>
      )}
      <a href="/upload" className={buttonClasses("primary", "md")}>
        New case
        <span aria-hidden className="text-base leading-none">
          →
        </span>
      </a>
    </nav>
  );
}
