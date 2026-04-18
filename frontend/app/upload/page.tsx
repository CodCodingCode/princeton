"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { uploadPdfs } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function isPdfFile(f: File): boolean {
    return (
      f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
  }

  function mergePdfs(pdfs: File[]) {
    if (!pdfs.length) {
      setError(
        "No PDFs detected in that drop. Expected at least one .pdf file.",
      );
      return;
    }
    setError(null);
    setPicked((prev) => {
      const seen = new Set(prev.map((p) => p.name));
      const merged = [...prev];
      for (const p of pdfs) if (!seen.has(p.name)) merged.push(p);
      return merged;
    });
  }

  function addFiles(fileList: FileList | null | undefined) {
    if (!fileList) return;
    mergePdfs(Array.from(fileList).filter(isPdfFile));
  }

  // Drag-and-drop folder support: dataTransfer.files doesn't recurse into
  // subdirectories. We walk the FileSystemEntry tree via webkitGetAsEntry()
  // → readEntries() and collect .pdf files from every level.
  async function addFromDataTransfer(dt: DataTransfer) {
    const items = Array.from(dt.items).filter((i) => i.kind === "file");
    const entries = items
      .map((i) =>
        (
          i as unknown as { webkitGetAsEntry?: () => FileSystemEntry | null }
        ).webkitGetAsEntry?.(),
      )
      .filter((e): e is FileSystemEntry => !!e);

    if (!entries.length) {
      addFiles(dt.files);
      return;
    }

    const pdfs: File[] = [];
    await Promise.all(entries.map((e) => walkEntry(e, pdfs)));
    mergePdfs(pdfs);
  }

  async function walkEntry(entry: FileSystemEntry, out: File[]): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File | null>((resolve) => {
        (entry as FileSystemFileEntry).file(
          (f) => resolve(f),
          () => resolve(null),
        );
      });
      if (file && isPdfFile(file)) out.push(file);
      return;
    }
    if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      // readEntries only returns a page at a time — loop until empty.
      const readAll = (): Promise<FileSystemEntry[]> =>
        new Promise((resolve) => {
          const collected: FileSystemEntry[] = [];
          const pump = () => {
            reader.readEntries(
              (batch) => {
                if (!batch.length) return resolve(collected);
                collected.push(...batch);
                pump();
              },
              () => resolve(collected),
            );
          };
          pump();
        });
      const children = await readAll();
      await Promise.all(children.map((c) => walkEntry(c, out)));
    }
  }

  async function submit() {
    if (!picked.length || busy) return;
    setError(null);
    setBusy(true);
    try {
      const caseId = await uploadPdfs(picked);
      router.push(`/case/${caseId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 pt-20 pb-28">
      <div className="text-xs uppercase tracking-widest text-neutral-500 mb-6">
        About NeoVax
      </div>

      <div className="grid md:grid-cols-[1fr_2fr] gap-12 mb-20">
        <div />
        <div>
          <h1 className="font-sans text-4xl md:text-5xl font-semibold tracking-tight leading-[1.05] text-black mb-8">
            NeoVax is not just another oncology tool
          </h1>
          <p className="text-neutral-600 leading-relaxed mb-5 max-w-xl">
            Drop every PDF from a patient&apos;s workup — pathology, NGS,
            imaging, H&amp;P notes. A medical vision model reads each page; Kimi
            K2 reconciles across documents into one de-noised record with
            provenance you can audit.
          </p>
          <p className="text-neutral-600 leading-relaxed max-w-xl">
            What comes back is a dynamic NCCN-style railway grounded in phase-2+
            trial literature, a ranked list of matching Regeneron trials, a map
            of enrolling sites, and a downloadable oncologist report.
          </p>
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFromDataTransfer(e.dataTransfer);
        }}
        className={`border border-dashed rounded-2xl p-14 text-center transition ${
          dragOver
            ? "border-black bg-neutral-50"
            : "border-neutral-300 bg-white"
        }`}
      >
        <input
          ref={folderInputRef}
          type="file"
          multiple
          accept="application/pdf,.pdf"
          // Safari/Firefox accept both attrs; non-standard props are OK here.
          // eslint-disable-next-line @typescript-eslint/ban-ts-comment
          // @ts-ignore
          webkitdirectory=""
          directory=""
          className="sr-only"
          onChange={(e) => addFiles(e.target.files)}
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(e) => addFiles(e.target.files)}
        />
        <div>
          {busy ? (
            <p className="text-neutral-600">
              Uploading {picked.length} PDFs and starting pipeline…
            </p>
          ) : (
            <>
              <p className="font-medium text-black text-lg mb-1">
                Drop the patient&apos;s folder here
              </p>
              <p className="text-sm text-neutral-500 mb-6">
                or pick a folder or individual PDFs below
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="px-5 py-2.5 rounded-full border border-black text-black hover:bg-black hover:text-white text-sm transition"
                >
                  Select folder
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-5 py-2.5 rounded-full border border-neutral-300 text-neutral-700 hover:border-black hover:text-black text-sm transition"
                >
                  Select PDFs
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {picked.length > 0 && (
        <div className="mt-6 rounded-2xl border border-neutral-200 bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-neutral-700">
              Queued {picked.length} document{picked.length === 1 ? "" : "s"}
            </span>
            <button
              type="button"
              onClick={() => setPicked([])}
              disabled={busy}
              className="text-xs text-neutral-500 hover:text-black disabled:opacity-40"
            >
              clear
            </button>
          </div>
          <ul className="text-sm space-y-1 max-h-48 overflow-y-auto">
            {picked.map((f, i) => (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center justify-between gap-2 text-neutral-800"
              >
                <span className="truncate font-mono text-xs">{f.name}</span>
                <span className="text-neutral-500 text-xs shrink-0">
                  {Math.round(f.size / 1024)} kB
                </span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !picked.length}
            className="mt-5 w-full px-4 py-3 rounded-full bg-black hover:bg-neutral-800 text-white font-medium text-sm disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            {busy ? "Starting…" : `Run NeoVax on ${picked.length} PDFs`}
          </button>
        </div>
      )}

      {error && (
        <p className="mt-4 text-red-600 text-sm whitespace-pre-wrap">{error}</p>
      )}

      <div className="mt-28 grid md:grid-cols-3 gap-6 border-t border-neutral-200 pt-12">
        {[
          {
            num: "01",
            title: "Per-doc VLM",
            body: "Every page rasterized → MediX vision → structured findings",
          },
          {
            num: "02",
            title: "Kimi reconcile",
            body: "Resolve contradictions, dedup mutations, track provenance",
          },
          {
            num: "03",
            title: "Railway + trials",
            body: "Dynamic 4-phase railway, matched trials, map, PDF report",
          },
        ].map((step) => (
          <div key={step.num}>
            <div className="font-serif text-6xl md:text-7xl leading-none text-black mb-3">
              {step.num}
            </div>
            <div className="text-sm font-semibold text-black mb-1">
              {step.title}
            </div>
            <div className="text-sm text-neutral-600 leading-relaxed">
              {step.body}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
