"use client";

// Intake overlay - centered card with drag-drop + folder/file pickers, queued
// file list, and submit. Upload mechanics (isPdfFile, walkEntry, etc.) lifted
// from the former `app/upload/page.tsx`.

import { useEffect, useRef, useState } from "react";
import { uploadPdfs } from "@/lib/api";
import { Button } from "@/components/ui/Button";

interface Props {
  onUploaded: (caseId: string) => void;
}

export function IntakeOverlay({ onUploaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const [visible, setVisible] = useState(false);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // The parent already delays mounting this overlay until ~2.8s into the
  // doctor's greeting, so we just need a tiny delay here to let the initial
  // opacity-0 render commit before flipping to opacity-100 - that's what
  // makes the CSS transition actually animate instead of snapping.
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  // The pipeline accepts a messy mix: PDFs (primary), text-like notes
  // (.txt/.md/.csv/.json/.html/.log/.rtf), and images (.png/.jpg/.jpeg/.webp/
  // .tiff/.bmp/.gif). The backend routes each by extension.
  const SUPPORTED_EXTS = [
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".log",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tiff",
    ".tif",
    ".bmp",
    ".gif",
  ];

  function isSupportedFile(f: File): boolean {
    const name = f.name.toLowerCase();
    // Skip OS junk files.
    if (name === ".ds_store" || name.startsWith("._")) return false;
    return SUPPORTED_EXTS.some((ext) => name.endsWith(ext));
  }

  function mergeFiles(files: File[]) {
    if (!files.length) {
      setError(
        "No supported files detected. Expected PDFs, text (.txt/.md/.csv/.json), or images.",
      );
      return;
    }
    setError(null);
    setPicked((prev) => {
      const seen = new Set(prev.map((p) => p.name));
      const merged = [...prev];
      for (const p of files) if (!seen.has(p.name)) merged.push(p);
      return merged;
    });
  }

  function addFiles(fileList: FileList | null | undefined) {
    if (!fileList) return;
    mergeFiles(Array.from(fileList).filter(isSupportedFile));
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

    const files: File[] = [];
    await Promise.all(entries.map((e) => walkEntry(e, files)));
    mergeFiles(files);
  }

  async function walkEntry(entry: FileSystemEntry, out: File[]): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File | null>((resolve) => {
        (entry as FileSystemFileEntry).file(
          (f) => resolve(f),
          () => resolve(null),
        );
      });
      if (file && isSupportedFile(file)) out.push(file);
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
      <div
        className={`max-w-xl w-full rounded-2xl bg-white/40 backdrop-blur-2xl backdrop-saturate-150 border border-white/50 ring-1 ring-black/5 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.25)] p-8 transition-all duration-[700ms] ease-out ${
          visible
            ? "opacity-100 translate-y-0 pointer-events-auto"
            : "opacity-0 translate-y-2 pointer-events-none"
        }`}
      >
        <div className="eyebrow mb-2">Step 1 · Share your records</div>
        <h2 className="text-2xl font-semibold tracking-tight text-black leading-tight mb-1">
          Drop your medical records
        </h2>
        <p className="text-xs text-neutral-500 mb-5">
          PDFs, scans, notes: .pdf · .txt · .md · .csv · .json · .png · .jpg ·
          .tiff
        </p>

        {/* Once the user has queued at least one file, hide the dashed
            drop zone entirely - the Analyze button + queued list below is
            the next action, and re-adding more docs on top would muddy the
            "Step 1" framing. Clearing the queue brings this block back. */}
        {picked.length === 0 && (
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
            className={`border border-dashed rounded-xl p-8 text-center transition backdrop-blur-sm ${
              dragOver
                ? "border-black bg-white/60"
                : "border-white/60 bg-white/20 hover:bg-white/30"
            }`}
          >
            <input
              ref={folderInputRef}
              type="file"
              multiple
              accept=".pdf,.txt,.md,.csv,.json,.html,.htm,.log,.rtf,.png,.jpg,.jpeg,.webp,.tiff,.tif,.bmp,.gif,application/pdf,text/plain,application/json,image/*"
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
              accept=".pdf,.txt,.md,.csv,.json,.html,.htm,.log,.rtf,.png,.jpg,.jpeg,.webp,.tiff,.tif,.bmp,.gif,application/pdf,text/plain,application/json,image/*"
              className="sr-only"
              onChange={(e) => addFiles(e.target.files)}
            />
            {busy ? (
              <p className="text-neutral-600 text-sm">
                Uploading {picked.length} file{picked.length === 1 ? "" : "s"}…
              </p>
            ) : (
              <>
                <p className="text-black font-medium mb-1">
                  Drop a folder here
                </p>
                <p className="text-xs text-neutral-500 mb-4">
                  Or pick files below.
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => folderInputRef.current?.click()}
                  >
                    Select folder
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Select files
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {picked.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-neutral-700">
                Queued {picked.length} document{picked.length === 1 ? "" : "s"}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPicked([])}
                disabled={busy}
              >
                Clear
              </Button>
            </div>
            <ul className="text-xs space-y-1 max-h-36 overflow-y-auto border border-white/60 bg-white/30 backdrop-blur rounded-lg p-2">
              {picked.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center justify-between gap-2 text-neutral-800"
                >
                  <span className="font-mono">{f.name}</span>
                  <span className="text-neutral-500 shrink-0">
                    {Math.round(f.size / 1024)} kB
                  </span>
                </li>
              ))}
            </ul>
            <Button
              onClick={submit}
              disabled={busy || !picked.length}
              size="lg"
              className="mt-4 w-full"
            >
              {busy
                ? "Starting…"
                : `Analyze ${picked.length} document${picked.length === 1 ? "" : "s"}`}
            </Button>
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
