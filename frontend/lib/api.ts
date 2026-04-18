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
 */
export function subscribeCaseEvents(
  caseId: string,
  onEvent: (ev: AgentEvent) => void,
): () => void {
  const es = new EventSource(`/api/cases/${caseId}/stream`);
  for (const kind of ALL_EVENT_KINDS) {
    es.addEventListener(kind, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as AgentEvent;
        onEvent(data);
      } catch (err) {
        console.error("SSE parse error", err, e.data);
      }
    });
  }
  es.onerror = () => {
    // EventSource auto-reconnects; no-op.
  };
  return () => es.close();
}

/**
 * POST a chat turn and stream the response events. Returns an async generator
 * yielding typed events, plus a cancel function.
 */
export async function streamChatTurn(
  caseId: string,
  message: string,
  onEvent: (ev: AgentEvent) => void,
): Promise<void> {
  const resp = await fetch(`/api/cases/${caseId}/chat`, {
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
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE records are separated by a blank line
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = raw.split("\n");
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
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
