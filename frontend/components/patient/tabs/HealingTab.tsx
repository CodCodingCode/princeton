"use client";

// "How to heal" - fetches the LLM-generated patient guide on mount and
// renders it. Falls through to the backend's static fallback when Kimi
// is unavailable, so this tab is never empty.

import { useEffect, useState } from "react";
import type { PatientCase } from "@/lib/types";
import { fetchPatientGuide, type PatientGuide } from "@/lib/patientApi";

export function HealingTab({ caseData }: { caseData: PatientCase }) {
  const [guide, setGuide] = useState<PatientGuide | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPatientGuide(caseData.case_id)
      .then((g) => {
        if (cancelled) return;
        setGuide(g);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.case_id]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-6 w-2/3 rounded bg-neutral-200/80" />
        <div className="space-y-2">
          <div className="h-4 w-full rounded bg-neutral-200/60" />
          <div className="h-4 w-5/6 rounded bg-neutral-200/60" />
          <div className="h-4 w-4/6 rounded bg-neutral-200/60" />
        </div>
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="rounded-xl border border-neutral-200/80 bg-white/60 p-4 space-y-2"
            >
              <div className="h-4 w-1/3 rounded bg-neutral-200/70" />
              <div className="h-3 w-full rounded bg-neutral-200/50" />
              <div className="h-3 w-11/12 rounded bg-neutral-200/50" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error && !guide) {
    return (
      <div className="rounded-xl border border-neutral-200/80 bg-white/60 p-5 text-sm text-neutral-700 leading-relaxed">
        We couldn&apos;t load your healing guide right now. Try reloading the
        page, or ask the avatar directly about diet, sleep, and support.
      </div>
    );
  }

  if (!guide) return null;

  return (
    <div className="space-y-8">
      <section>
        <div className="eyebrow mb-2">For you, right now</div>
        <p className="font-serif text-xl leading-snug text-black">
          {guide.headline}
        </p>
      </section>

      <section>
        <div className="eyebrow mb-3">What you can do</div>
        <div className="space-y-4">
          {guide.healing.map((block, i) => (
            <article
              key={`${block.heading}-${i}`}
              className="rounded-xl border border-neutral-200/80 bg-white/70 p-5"
            >
              <h3 className="font-serif text-lg leading-snug text-black mb-2">
                {block.heading}
              </h3>
              <p className="text-sm text-neutral-700 leading-relaxed whitespace-pre-line mb-3">
                {block.body}
              </p>
              {block.bullets.length > 0 && (
                <ul className="space-y-1.5 text-sm text-black">
                  {block.bullets.map((b, j) => (
                    <li key={j} className="flex gap-2">
                      <span
                        aria-hidden
                        className="text-neutral-400 shrink-0 mt-0.5"
                      >
                        •
                      </span>
                      <span className="leading-relaxed">{b}</span>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </section>

      {guide.warning_signs.length > 0 && (
        <section className="rounded-xl border border-neutral-300/80 bg-white/70 p-5">
          <div className="eyebrow mb-2">When to call your care team</div>
          <ul className="space-y-1.5 text-sm text-black">
            {guide.warning_signs.map((w, i) => (
              <li key={i} className="flex gap-2">
                <span aria-hidden className="text-neutral-400 shrink-0 mt-0.5">
                  •
                </span>
                <span className="leading-relaxed">{w}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {guide.things_to_avoid.length > 0 && (
        <section>
          <div className="eyebrow mb-3">Things to avoid</div>
          <ul className="space-y-1.5 text-sm text-black">
            {guide.things_to_avoid.map((t, i) => (
              <li key={i} className="flex gap-2">
                <span aria-hidden className="text-neutral-400 shrink-0 mt-0.5">
                  •
                </span>
                <span className="leading-relaxed">{t}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
