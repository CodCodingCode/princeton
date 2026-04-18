"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { uploadPdf } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | undefined | null) {
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const caseId = await uploadPdf(file);
      router.push(`/case/${caseId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 pt-16 pb-24">
      <h1 className="text-3xl font-semibold tracking-tight mb-2">
        Upload a pathology PDF
      </h1>
      <p className="text-ink-400 mb-8 leading-relaxed">
        NeoVax extracts structured oncology fields, walks the NCCN treatment
        railway (with sibling branches), matches Regeneron trials, geocodes
        recruiting sites, and lets you ask Kimi why each step was chosen.
      </p>

      <label
        htmlFor="pdf-input"
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`block border-2 border-dashed rounded-xl p-12 text-center transition cursor-pointer ${
          dragOver
            ? "border-teal-400 bg-teal-400/5"
            : "border-ink-700 hover:border-teal-600 bg-ink-900/40"
        }`}
      >
        <input
          id="pdf-input"
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          disabled={busy}
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <div className="text-ink-300">
          <div className="text-5xl mb-4 text-teal-400">{busy ? "…" : "⬆"}</div>
          {busy ? (
            <p>Uploading and starting pipeline…</p>
          ) : (
            <>
              <p className="font-medium text-ink-100">
                Drop a pathology PDF here
              </p>
              <p className="text-sm text-ink-400 mt-1">
                or click to browse (noisy / scanned PDFs accepted — vision
                fallback kicks in when the text layer is empty)
              </p>
            </>
          )}
        </div>
      </label>

      {error && (
        <p className="mt-4 text-red-400 text-sm whitespace-pre-wrap">{error}</p>
      )}

      <div className="mt-12 grid md:grid-cols-3 gap-4 text-sm text-ink-400">
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">1 · Extract</div>
          Noisy PDF → stage, Breslow, ECOG, mutations
        </div>
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">2 · Railway</div>
          NCCN walk with sibling branches + PubMed citations
        </div>
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">3 · Explain</div>
          Kimi K2 chat + trial-site map + PDF report
        </div>
      </div>
    </div>
  );
}
