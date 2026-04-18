"use client";

// Intake overlay — centered card with drag-drop + folder/file pickers, queued
// file list, and submit. Upload mechanics (isPdfFile, walkEntry, etc.) lifted
// from the former `app/upload/page.tsx`.

import { useRef, useState } from "react";
import { uploadPdfs } from "@/lib/api";

interface Props {
  onUploaded: (caseId: string) => void;
}

export function IntakeOverlay({ onUploaded }: Props) {
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
      onUploaded(caseId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="absolute inset-0 flex items-center justify-center p-6 pointer-events-none">
      <div className="pointer-events-auto max-w-xl w-full rounded-2xl bg-white/95 backdrop-blur shadow-2xl p-8">
        <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-500 font-semibold mb-2">
          Step 1 · share your records
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-black leading-tight mb-5">
          Drop your medical PDFs
        </h2>

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
          className={`border border-dashed rounded-xl p-8 text-center transition ${
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
          {busy ? (
            <p className="text-neutral-600 text-sm">
              Uploading {picked.length} PDFs…
            </p>
          ) : (
            <>
              <p className="text-black font-medium mb-1">Drop a folder here</p>
              <p className="text-xs text-neutral-500 mb-4">
                or pick files below
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="px-4 py-2 rounded-full border border-black text-black hover:bg-black hover:text-white text-xs transition"
                >
                  Select folder
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 rounded-full border border-neutral-300 text-neutral-700 hover:border-black hover:text-black text-xs transition"
                >
                  Select PDFs
                </button>
              </div>
            </>
          )}
        </div>

        {picked.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-neutral-700">
                Queued {picked.length} document{picked.length === 1 ? "" : "s"}
              </span>
              <button
                type="button"
                onClick={() => setPicked([])}
                disabled={busy}
                className="text-[11px] text-neutral-500 hover:text-black disabled:opacity-40"
              >
                clear
              </button>
            </div>
            <ul className="text-xs space-y-1 max-h-36 overflow-y-auto border border-neutral-200 rounded-lg p-2">
              {picked.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center justify-between gap-2 text-neutral-800"
                >
                  <span className="truncate font-mono">{f.name}</span>
                  <span className="text-neutral-500 shrink-0">
                    {Math.round(f.size / 1024)} kB
                  </span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={submit}
              disabled={busy || !picked.length}
              className="mt-4 w-full px-4 py-3 rounded-full bg-brand-700 hover:bg-brand-900 text-white text-sm font-medium disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              {busy ? "Starting…" : `Analyze ${picked.length} PDFs`}
            </button>
          </div>
        )}

        {error && (
          <p className="mt-3 text-red-600 text-xs whitespace-pre-wrap">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
