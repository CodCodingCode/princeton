"use client";

// Client-side nav for the fixed header. Knows about pathname + searchParams
// so it can swap a "Patient view" / "Clinician view" toggle on top of the
// always-visible "New case" CTA.
//
// Both links must use Next.js `<Link>` (not plain `<a href>`). A full
// document navigation wipes `globalThis`, which destroys the avatar-session
// singleton in lib/avatar-session.ts and forces a cold HeyGen reconnect on
// every header click. With `<Link>`, the singleton survives the transition
// and AvatarStage's attachVideo() re-binds the already-running stream to
// the new page's <video> tag — no flicker, no token mint.

import Link from "next/link";
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
        <Link href={toggleHref} className={buttonClasses("secondary", "md")}>
          {toggleLabel}
          <span aria-hidden className="text-base leading-none">
            →
          </span>
        </Link>
      )}
      <Link href="/upload" className={buttonClasses("primary", "md")}>
        New case
        <span aria-hidden className="text-base leading-none">
          →
        </span>
      </Link>
    </nav>
  );
}
