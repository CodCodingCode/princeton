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
    <div className="max-w-3xl mx-auto px-6 pt-16 pb-24">
      <h1 className="text-3xl font-semibold tracking-tight mb-2">
        Upload a patient&apos;s document folder
      </h1>
      <p className="text-ink-400 mb-8 leading-relaxed">
        Drop every PDF from the patient&apos;s workup — pathology reports, NGS,
        imaging, H&amp;P notes. MediX VLM reads each page; Kimi K2 reconciles
        across documents into one de-noised record with provenance.
      </p>

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
        className={`border-2 border-dashed rounded-xl p-12 text-center transition ${
          dragOver
            ? "border-teal-400 bg-teal-400/5"
            : "border-ink-700 bg-ink-900/40"
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
        <div className="text-ink-300">
          <div className="text-5xl mb-4 text-teal-400">{busy ? "…" : "📁"}</div>
          {busy ? (
            <p>Uploading {picked.length} PDFs and starting pipeline…</p>
          ) : (
            <>
              <p className="font-medium text-ink-100 mb-1">
                Drop the patient&apos;s folder here
              </p>
              <p className="text-sm text-ink-400 mb-4">
                or pick a folder / individual PDFs below
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="px-4 py-2 rounded-lg bg-ink-800 hover:bg-ink-700 text-ink-100 text-sm"
                >
                  Select folder
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 rounded-lg bg-ink-800 hover:bg-ink-700 text-ink-100 text-sm"
                >
                  Select PDFs
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {picked.length > 0 && (
        <div className="mt-6 rounded-xl border border-ink-800 bg-ink-900/40 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-ink-300">
              Queued {picked.length} document{picked.length === 1 ? "" : "s"}
            </span>
            <button
              type="button"
              onClick={() => setPicked([])}
              disabled={busy}
              className="text-xs text-ink-500 hover:text-ink-300 disabled:opacity-40"
            >
              clear
            </button>
          </div>
          <ul className="text-sm space-y-1 max-h-48 overflow-y-auto">
            {picked.map((f, i) => (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center justify-between gap-2 text-ink-200"
              >
                <span className="truncate font-mono text-xs">{f.name}</span>
                <span className="text-ink-500 text-xs shrink-0">
                  {Math.round(f.size / 1024)} kB
                </span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !picked.length}
            className="mt-4 w-full px-4 py-2 rounded-lg bg-teal-500 hover:bg-teal-400 text-ink-950 font-medium text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {busy ? "Starting…" : `Run NeoVax on ${picked.length} PDFs`}
          </button>
        </div>
      )}

      {error && (
        <p className="mt-4 text-red-400 text-sm whitespace-pre-wrap">{error}</p>
      )}

      <div className="mt-12 grid md:grid-cols-3 gap-4 text-sm text-ink-400">
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">1 · Per-doc VLM</div>
          Every page rasterized → MediX vision → structured findings
        </div>
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">
            2 · Kimi reconcile
          </div>
          Resolve contradictions, dedup mutations, track provenance
        </div>
        <div className="p-4 rounded-lg bg-ink-900/50 border border-ink-800">
          <div className="text-teal-400 font-medium mb-1">
            3 · Railway + trials
          </div>
          4-phase dynamic railway grounded in phase-2+ trial literature, matched
          trials, map, PDF report
        </div>
      </div>
    </div>
  );
}
