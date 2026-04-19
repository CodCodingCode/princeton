import type { AgentEvent, PatientCase } from "./types";

const ALL_EVENT_KINDS: string[] = [
  "log",
  "tool_start",
  "tool_result",
  "tool_error",
  "done",
  "thinking_delta",
  "answer_delta",
  "pdf_extracted",
  "doc_extracted",
  "aggregation_start",
  "aggregation_done",
  "nccn_node_visited",
  "railway_step",
  "railway_ready",
  "rag_citations",
  "trial_matches_ready",
  "trial_sites_ready",
  "case_update",
  "chat_thinking_delta",
  "chat_answer_delta",
  "chat_tool_call",
  "chat_tool_result",
  "chat_ui_focus",
  "chat_done",
  "ping",
  "stream_end",
];

export async function uploadPdfs(files: File[]): Promise<string> {
  if (!files.length) throw new Error("No PDFs to upload.");
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const resp = await fetch("/api/cases", { method: "POST", body: form });
  if (!resp.ok) {
    const msg = await resp.text();
    throw new Error(`Upload failed: ${resp.status} ${msg}`);
  }
  const data = (await resp.json()) as { case_id: string };
  return data.case_id;
}

export async function fetchCase(caseId: string): Promise<PatientCase> {
  const resp = await fetch(`/api/cases/${caseId}`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`Fetch case failed: ${resp.status}`);
  return (await resp.json()) as PatientCase;
}

/**
 * Open an EventSource against the case stream and invoke `onEvent` for every
 * typed event. Returns a cleanup function.
 *
 * Critically, we must close the EventSource on `done` / `stream_end`: when the
 * backend closes the stream normally the browser will otherwise auto-reconnect,
 * the backend replays the full event history on the new connection, and every
 * replay appends to the caller's events array + extractFeed. That manifests as
 * the sidebar flickering between states on a finished case.
 */
export function subscribeCaseEvents(
  caseId: string,
  onEvent: (ev: AgentEvent) => void,
): () => void {
  const es = new EventSource(`/api/cases/${caseId}/stream`);
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
  };
  for (const kind of ALL_EVENT_KINDS) {
    es.addEventListener(kind, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as AgentEvent;
        onEvent(data);
        if (data.kind === "done" || data.kind === "stream_end") close();
      } catch (err) {
        console.error("SSE parse error", err, e.data);
      }
    });
  }
  es.onerror = () => {
    // If the stream already delivered `done`, we'll have closed above. This
    // branch handles transient network errors - let the browser attempt one
    // reconnect (default SSE behavior). If the connection is already closed
    // this is a no-op.
  };
  return close;
}

export type ChatAudience = "oncologist" | "patient";

/**
 * POST a chat turn and stream the response events. The backend keeps a
 * separate conversation thread per audience — the doctor view talks to an
 * oncologist-tuned agent, the patient view to a plain-language one.
 */
export async function streamChatTurn(
  caseId: string,
  message: string,
  onEvent: (ev: AgentEvent) => void,
  opts: { audience?: ChatAudience } = {},
): Promise<void> {
  const audience = opts.audience ?? "oncologist";
  const resp = await fetch(`/api/cases/${caseId}/chat?audience=${audience}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message }),
  });
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`Chat failed: ${resp.status} ${detail}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  // SSE spec allows either LF or CRLF line endings. sse-starlette emits
  // CRLF, so we must accept \r?\n line separators AND \r?\n\r?\n record
  // separators — splitting on "\n\n" alone buffers events forever when the
  // server uses CRLF.
  const recordSep = /\r?\n\r?\n/;
  const lineSep = /\r?\n/;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    while (true) {
      const m = recordSep.exec(buf);
      if (!m) break;
      const raw = buf.slice(0, m.index);
      buf = buf.slice(m.index + m[0].length);
      const lines = raw.split(lineSep);
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith(":")) continue; // SSE comment (keepalive)
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      try {
        const data = JSON.parse(dataLines.join("\n")) as AgentEvent;
        onEvent(data);
        if (eventName === "chat_done" || data.kind === "chat_done") return;
      } catch (err) {
        console.error("chat SSE parse error", err, dataLines);
      }
    }
  }
}

export function reportUrl(caseId: string): string {
  return `/api/cases/${caseId}/report.pdf`;
}
