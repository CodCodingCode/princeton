"use client";

import { useEffect, useRef, useState } from "react";
import { streamChatTurn } from "@/lib/api";
import type { AgentEvent } from "@/lib/types";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  thinking: string;
}

export function ChatPanel({ caseId }: { caseId: string }) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState<ChatMessage | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [history, streaming]);

  async function send() {
    const msg = input.trim();
    if (!msg || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    setHistory((prev) => [...prev, { role: "user", text: msg, thinking: "" }]);

    const acc: ChatMessage = { role: "assistant", text: "", thinking: "" };
    setStreaming(acc);

    const onEvent = (ev: AgentEvent) => {
      if (ev.kind === "chat_thinking_delta") {
        acc.thinking += String(ev.payload.delta ?? "");
      } else if (ev.kind === "chat_answer_delta") {
        acc.text += String(ev.payload.delta ?? "");
      }
      setStreaming({ ...acc });
    };

    try {
      await streamChatTurn(caseId, msg, onEvent);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }

    if (acc.text || acc.thinking) {
      setHistory((prev) => [...prev, acc]);
    }
    setStreaming(null);
    setBusy(false);
  }

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 flex flex-col h-[28rem]">
      <div className="px-4 py-2 border-b border-ink-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-teal-400">
          Ask Kimi K2 about this case
        </span>
        {busy && (
          <span className="text-xs text-ink-400 pulse-dot">thinking</span>
        )}
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm"
      >
        {history.length === 0 && !streaming && (
          <p className="text-ink-500">
            Try: <em>&quot;Why adjuvant IO here?&quot;</em> ·{" "}
            <em>&quot;What about the BRAF-mutant branch?&quot;</em> ·{" "}
            <em>&quot;Show me NCT05352672.&quot;</em>
          </p>
        )}
        {history.concat(streaming ? [streaming] : []).map((m, i) => (
          <div key={i}>
            {m.role === "user" ? (
              <div className="text-right">
                <span className="inline-block px-3 py-1.5 rounded-lg bg-teal-400/15 text-teal-100 max-w-[85%] text-left">
                  {m.text}
                </span>
              </div>
            ) : (
              <div>
                {m.thinking && (
                  <details className="mb-1 text-xs text-ink-500">
                    <summary className="cursor-pointer hover:text-ink-300">
                      reasoning
                    </summary>
                    <pre className="whitespace-pre-wrap font-mono mt-1 opacity-80">
                      {m.thinking}
                    </pre>
                  </details>
                )}
                <div className="inline-block px-3 py-1.5 rounded-lg bg-ink-800 text-ink-100 max-w-[95%] whitespace-pre-wrap">
                  {m.text || (busy && streaming === m ? "…" : "")}
                </div>
              </div>
            )}
          </div>
        ))}
        {error && <p className="text-red-400 text-xs">{error}</p>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="border-t border-ink-800 p-2 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          placeholder="Ask about the railway, alternatives, or trials…"
          className="flex-1 bg-ink-950 border border-ink-800 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-teal-600 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="px-3 py-1.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-ink-950 font-medium text-sm disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </form>
    </div>
  );
}
