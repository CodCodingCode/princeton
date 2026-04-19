"use client";

import { useEffect, useRef, useState } from "react";

let mermaidInitPromise: Promise<typeof import("mermaid").default> | null = null;

async function getMermaid() {
  if (!mermaidInitPromise) {
    mermaidInitPromise = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "loose",
        themeVariables: {
          background: "transparent",
          primaryColor: "#ffffff",
          primaryTextColor: "#0a0a0a",
          primaryBorderColor: "#0a0a0a",
          lineColor: "#6b6b6b",
          fontSize: "13px",
        },
        flowchart: {
          curve: "basis",
          htmlLabels: true,
          padding: 12,
        },
      });
      return mod.default;
    });
  }
  return mermaidInitPromise;
}

export function RailwayMermaid({
  mermaidSource,
  empty,
}: {
  mermaidSource: string;
  empty?: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!mermaidSource || !ref.current) return;
    setErr(null);
    setRendering(true);
    (async () => {
      try {
        const mermaid = await getMermaid();
        const id = `nv-railway-${Date.now()}`;
        const { svg } = await mermaid.render(id, mermaidSource);
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setRendering(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mermaidSource]);

  if (empty) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-8 text-neutral-500 text-sm text-center">
        Treatment plan will appear here as the analysis progresses.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4 overflow-x-auto">
      {rendering && (
        <div className="text-neutral-500 text-xs mb-2">Rendering…</div>
      )}
      {err && (
        <div className="text-red-600 text-xs mb-2">Unable to render chart.</div>
      )}
      <div ref={ref} className="mermaid" />
    </div>
  );
}
