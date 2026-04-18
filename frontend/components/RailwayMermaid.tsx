"use client";

import { useEffect, useRef, useState } from "react";

let mermaidInitPromise: Promise<typeof import("mermaid").default> | null = null;

async function getMermaid() {
  if (!mermaidInitPromise) {
    mermaidInitPromise = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "loose",
        themeVariables: {
          background: "transparent",
          primaryColor: "#134e4a",
          primaryTextColor: "#e5e7eb",
          primaryBorderColor: "#0d9488",
          lineColor: "#6b7280",
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
      <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-8 text-ink-400 text-sm text-center">
        Railway will appear here as the NCCN walker runs…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-4 overflow-x-auto">
      {rendering && <div className="text-ink-500 text-xs mb-2">rendering…</div>}
      {err && (
        <div className="text-red-400 text-xs mb-2">mermaid error: {err}</div>
      )}
      <div ref={ref} className="mermaid" />
    </div>
  );
}
