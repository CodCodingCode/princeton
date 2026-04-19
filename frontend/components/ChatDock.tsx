"use client";

// Caption-style chat input. A compact dark pill that sits directly under the
// avatar's spoken caption and lets the user ask the Kimi-K2 agent anything.
// No visible transcript — the avatar's own caption IS the response surface,
// so we just need an input.
//
// Two critical pieces of plumbing:
//   1. Sentence-chunked avatar speech. HeyGen's .repeat() swallows words if
//      you push raw answer_delta chunks at it, so we accumulate deltas into
//      a buffer and call stage.speak() only on sentence boundaries.
//   2. UI focus routing. Tool calls emit chat_ui_focus; the parent page maps
//      each payload to its own URL/tab scheme.

import {
  FormEvent,
  KeyboardEvent,
  RefObject,
  useCallback,
  useRef,
  useState,
} from "react";
import { streamChatTurn, type ChatAudience } from "@/lib/api";
import type { AgentEvent } from "@/lib/types";
import type { AvatarStageHandle } from "@/components/AvatarStage";

interface Props {
  caseId: string;
  audience: ChatAudience;
  stageRef: RefObject<AvatarStageHandle | null>;
  onUiFocus?: (payload: Record<string, unknown>) => void;
  // Compact mode = cockpit/doctor page where a sidebar occupies the right
  // ~36vw. The pill centers inside the avatar pane instead of the full
  // viewport so it aligns with the caption above it.
  compact?: boolean;
}

// Split a running buffer into (completed sentences, remaining fragment).
function splitSentences(buf: string): { speakable: string; rest: string } {
  const re = /[.!?]+["')\]]*(\s+|$)/g;
  let lastEnd = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(buf)) !== null) {
    lastEnd = m.index + m[0].length;
  }
  if (lastEnd === 0) return { speakable: "", rest: buf };
  return {
    speakable: buf.slice(0, lastEnd).trim(),
    rest: buf.slice(lastEnd),
  };
}

export function ChatDock({
  caseId,
  audience,
  stageRef,
  onUiFocus,
  compact = false,
}: Props) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const speakBufRef = useRef<string>("");
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFlushTimer = () => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  };

  const tryFlushSentence = useCallback(() => {
    const { speakable, rest } = splitSentences(speakBufRef.current);
    if (speakable) {
      speakBufRef.current = rest;
      stageRef.current?.speak(speakable).catch(() => {});
    }
  }, [stageRef]);

  const flushRemainder = useCallback(() => {
    clearFlushTimer();
    const tail = speakBufRef.current.trim();
    if (tail) {
      speakBufRef.current = "";
      stageRef.current?.speak(tail).catch(() => {});
    }
  }, [stageRef]);

  const send = useCallback(
    async (message: string) => {
      if (!message.trim() || busy) return;
      setError(null);
      setBusy(true);
      speakBufRef.current = "";
      clearFlushTimer();

      const onEvent = (ev: AgentEvent) => {
        const payload = ev.payload as Record<string, unknown> | undefined;
        if (ev.kind === "chat_answer_delta") {
          const delta = (payload?.delta as string | undefined) ?? "";
          if (!delta) return;
          speakBufRef.current += delta;
          tryFlushSentence();
          clearFlushTimer();
          flushTimerRef.current = setTimeout(() => {
            flushRemainder();
          }, 800);
        } else if (ev.kind === "chat_ui_focus") {
          if (payload) onUiFocus?.(payload);
        } else if (ev.kind === "chat_done") {
          flushRemainder();
        }
      };

      try {
        await streamChatTurn(caseId, message, onEvent, { audience });
      } catch (e) {
        console.error("chat turn failed", e);
        const msg = e instanceof Error ? e.message : "Chat failed.";
        setError(msg);
      } finally {
        flushRemainder();
        setBusy(false);
      }
    },
    [audience, busy, caseId, flushRemainder, onUiFocus, tryFlushSentence],
  );

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    void send(msg);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit(e as unknown as FormEvent);
    }
  };

  const placeholder =
    audience === "patient"
      ? "Ask anything about your diagnosis…"
      : "Ask about the case, evidence, or a trial…";

  return (
    // Outer flex row mirrors the caption's positioning — same compact/full
    // logic — so the pill always lands directly beneath the caption pill.
    // In compact mode both right-align toward the sidebar so the chat and
    // caption hug the data panel instead of floating centered over the
    // avatar's face.
    <div
      className={`pointer-events-none absolute bottom-6 z-30 flex px-6 ${
        compact
          ? "left-0 right-[calc(clamp(420px,34vw,560px)+2rem)] justify-end"
          : "left-0 right-0 justify-center"
      }`}
    >
      <form
        onSubmit={onSubmit}
        className="pointer-events-auto w-[min(80%,680px)] flex flex-col gap-1.5"
      >
        {error && (
          <div className="self-center text-xs text-red-200 bg-red-900/70 backdrop-blur-md rounded-full px-3 py-1 ring-1 ring-red-400/30">
            {error}
          </div>
        )}
        <div className="flex items-center gap-2 bg-black/65 backdrop-blur-md text-white rounded-full px-4 py-2 ring-1 ring-white/15 shadow-lg shadow-black/30">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={busy ? "…" : placeholder}
            disabled={busy}
            className="flex-1 bg-transparent outline-none text-sm md:text-base placeholder:text-white/50 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="Send"
            className="shrink-0 w-7 h-7 rounded-full bg-white hover:bg-white/90 text-black flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {busy ? (
              <span
                aria-hidden
                className="inline-block w-2 h-2 rounded-full bg-black/70 animate-pulse"
              />
            ) : (
              <svg
                viewBox="0 0 20 20"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M4 10 L16 10 M11 5 L16 10 L11 15" />
              </svg>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
