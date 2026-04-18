"""LangGraph chat agent for a finished patient case.

State graph (one user turn = one full traversal):

    [rag_retrieve] → [k2_respond] (stream) ──┐
                        │                     │
                  tool_calls? ────────────► [tool_dispatch] (loop, max 3)

* Streaming events (`<think>` blocks + answer chunks) are emitted to the
  ambient ``EventBus`` out-of-band so the UI can render them live.
* Conversation memory: every turn appends to ``state.messages``.
* RAG: triggered when the router thinks the question needs literature.
* Tools: registered in ``chat/tools.py``. Up to 3 tool-call rounds per turn.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..agent.events import AgentEvent, EventBus, EventKind, set_current_bus
from ..models import PatientCase
from ..rag import has_store as _rag_available, query_papers
from .k2_client import has_kimi_key, k2_stream_with_thinking
from .state import ChatMessage, ChatState, ToolCall
from .tools import TOOL_SCHEMAS, execute_tool


MAX_TOOL_LOOPS = 3


SYSTEM_PROMPT = """You are an oncology patient copilot. The patient's document
folder has already been analysed: structured fields extracted, a 4-phase
treatment railway generated from phase-2+ trial literature, clinical trials
matched, trial sites geocoded. You have the full case summary in your context.
The patient may have any cancer type — do not assume melanoma.

Your job is to help the patient (or their clinician) understand the railway
and the matched trials. Explain the agent's reasoning, show alternative
options that were considered, surface PubMed evidence, and use tools to
scroll the dashboard.

Rules:
* Always reason inside <think>...</think> first, then write the user-facing
  answer.
* When the user asks "why this recommendation?" or "why not X?", call
  explain_node or explain_branch.
* When the user asks "where is trial X?", call show_trial.
* When the user asks for evidence or recent papers, call pubmed_search — the
  corpus is phase-2+ interventional trials across all major cancers.
* Be concise. Answer in 2-4 sentences unless explicitly asked for depth.
* Cite PMIDs inline when referencing a paper.
* You are NOT a licensed physician; defer final decisions to the oncologist.
"""


def _slim_case(case: PatientCase) -> str:
    """Render the case as a token-efficient string (~2K tokens)."""
    p = case.pathology
    i = case.intake
    lines = [
        f"CASE {case.case_id}",
        "",
        "DIAGNOSIS",
        f"  primary cancer: {case.primary_cancer_type or 'unknown'}",
        f"  histology: {p.histology or 'unknown'}",
        f"  primary site: {p.primary_site or 'unknown'}",
        "",
        "PATHOLOGY (melanoma-specific fields — null if not melanoma)",
        f"  subtype: {p.melanoma_subtype}",
        f"  Breslow: {p.breslow_thickness_mm} mm" if p.breslow_thickness_mm is not None else "  Breslow: unknown",
        f"  ulceration: {p.ulceration}",
        f"  T-stage: {p.t_stage}",
        f"  TILs: {p.tils_present}, PD-L1: {p.pdl1_estimate}",
        "",
        "INTAKE",
        f"  AJCC stage: {i.ajcc_stage or 'unknown'}",
        f"  ECOG: {i.ecog if i.ecog is not None else 'unknown'}",
        f"  Measurable disease (RECIST): {i.measurable_disease_recist}",
        f"  Prior systemic therapy: {i.prior_systemic_therapy}",
        f"  Prior anti-PD-1: {i.prior_anti_pd1}",
        f"  Age: {i.age_years}",
        "",
        f"MUTATIONS ({len(case.mutations)}):",
    ]
    for m in case.mutations[:20]:
        lines.append(f"  {m.gene} {m.label}")
    if len(case.mutations) > 20:
        lines.append(f"  …and {len(case.mutations) - 20} more")

    if case.railway and case.railway.steps:
        lines.append("")
        lines.append("NCCN RAILWAY:")
        for s in case.railway.steps:
            lines.append(f"  [{s.node_id}] {s.title} → {s.chosen_option_label}")
            if s.chosen_rationale:
                lines.append(f"      chosen: {s.chosen_rationale[:160]}")
            for alt in s.alternatives[:3]:
                reason = (alt.reason_not_chosen or "")[:120]
                lines.append(f"      ◦ alt {alt.option_label!r} — {reason}")
        if case.railway.final_recommendation:
            lines.append("")
            lines.append(f"FINAL RECOMMENDATION: {case.railway.final_recommendation}")

    if case.trial_matches:
        lines.append("")
        lines.append("TRIAL MATCHES:")
        for m in case.trial_matches[:6]:
            lines.append(
                f"  {m.nct_id} [{m.status}] {m.title[:90]}"
            )
            if m.failing_criteria:
                lines.append(f"      fails: {'; '.join(m.failing_criteria[:3])}")
            if m.unknown_criteria:
                lines.append(f"      unknown: {'; '.join(m.unknown_criteria[:3])}")

    if case.trial_sites:
        sites_by_nct: dict[str, int] = {}
        for s in case.trial_sites:
            sites_by_nct[s.nct_id] = sites_by_nct.get(s.nct_id, 0) + 1
        lines.append("")
        lines.append(
            "TRIAL SITES: "
            + ", ".join(f"{nct}×{n}" for nct, n in sorted(sites_by_nct.items()))
        )

    return "\n".join(lines)


def _needs_rag(question: str) -> bool:
    triggers = [
        "paper", "literature", "evidence", "study", "cite", "pmid",
        "publish", "recent", "review", "data",
    ]
    q = question.lower()
    return any(t in q for t in triggers)


async def _node_rag_retrieve(state: ChatState) -> ChatState:
    if not _rag_available():
        state["rag_hits"] = []
        return state
    last_user = next(
        (m for m in reversed(state["messages"]) if m.role == "user"),
        None,
    )
    if last_user is None or not _needs_rag(last_user.content):
        state["rag_hits"] = []
        return state
    try:
        papers = query_papers(last_user.content, top_k=3)
    except Exception:
        papers = []
    state["rag_hits"] = [
        {
            "pmid": p.pmid,
            "title": p.title,
            "year": p.year,
            "journal": p.journal,
            "snippet": p.snippet,
            "url": p.url,
        }
        for p in papers
    ]
    return state


async def _node_k2_respond(state: ChatState) -> ChatState:
    sys_msg = {
        "role": "system",
        "content": SYSTEM_PROMPT + "\n\nCASE SUMMARY:\n" + state.get("case_summary", ""),
    }
    if state.get("rag_hits"):
        cite_lines = ["PUBMED HITS (fresh search — cite these inline):"]
        for h in state["rag_hits"]:
            cite_lines.append(f"  [{h['pmid']}] {h['title']} ({h.get('journal','')} {h.get('year','')})")
            if h.get("snippet"):
                cite_lines.append(f"    {h['snippet']}")
        sys_msg["content"] += "\n\n" + "\n".join(cite_lines)

    messages = [sys_msg] + [m.to_openai() for m in state["messages"]]

    thinking_buf = ""
    answer_buf = ""
    tool_calls: list[dict] = []

    bus = state.get("bus")  # type: ignore[assignment]
    try:
        async for kind, payload in k2_stream_with_thinking(
            messages, tools=TOOL_SCHEMAS, max_tokens=1200,
        ):
            if kind == "thinking":
                thinking_buf += payload  # type: ignore[operator]
                if bus is not None:
                    await bus.emit(
                        EventKind.CHAT_THINKING_DELTA, "thinking", {"delta": payload},
                    )
            elif kind == "answer":
                answer_buf += payload  # type: ignore[operator]
                if bus is not None:
                    await bus.emit(
                        EventKind.CHAT_ANSWER_DELTA, "answer", {"delta": payload},
                    )
            elif kind == "tool_call":
                tool_calls.append(payload)  # type: ignore[arg-type]
    except Exception as e:
        if bus is not None:
            await bus.emit(EventKind.TOOL_ERROR, f"K2 stream failed: {e}")
        state["last_assistant_text"] = f"(K2 unavailable: {e})"
        state["last_assistant_thinking"] = ""
        state["pending_tool_calls"] = []
        return state

    state["last_assistant_text"] = answer_buf.strip()
    state["last_assistant_thinking"] = thinking_buf.strip()
    parsed: list[ToolCall] = []
    for tc in tool_calls:
        try:
            args = json.loads(tc.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        parsed.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))
    state["pending_tool_calls"] = parsed

    assistant_msg = ChatMessage(
        role="assistant",
        content=answer_buf.strip(),
        thinking=thinking_buf.strip(),
        tool_calls=parsed,
        citations=state.get("rag_hits", []),
    )
    state["messages"].append(assistant_msg)
    return state


async def _node_tool_dispatch(state: ChatState) -> ChatState:
    pending = state.get("pending_tool_calls") or []
    if not pending:
        return state
    case_dict = state.get("case_dict", {})  # type: ignore[arg-type]
    bus = state.get("bus")  # type: ignore[assignment]

    async def _run_one(tc: ToolCall):
        if bus is not None:
            await bus.emit(
                EventKind.CHAT_TOOL_CALL,
                f"{tc.name}({json.dumps(tc.arguments)[:80]})",
                {"name": tc.name, "arguments": tc.arguments, "id": tc.id},
            )
        try:
            result = await execute_tool(tc.name, tc.arguments, case_dict)
        except Exception as e:
            result = json.dumps({"error": f"{type(e).__name__}: {e}"})
        tc.result = result
        state["messages"].append(
            ChatMessage(role="tool", content=result, tool_call_id=tc.id)
        )

    await asyncio.gather(*(_run_one(tc) for tc in pending))
    state["pending_tool_calls"] = []
    state["iteration"] = int(state.get("iteration", 0)) + 1
    return state


def _route_after_respond(state: ChatState) -> str:
    if state.get("pending_tool_calls") and int(state.get("iteration", 0)) < MAX_TOOL_LOOPS:
        return "tool_dispatch"
    return "end"


def _build_graph():
    from langgraph.graph import StateGraph, END

    g: StateGraph = StateGraph(dict)
    g.add_node("rag_retrieve", _node_rag_retrieve)
    g.add_node("k2_respond", _node_k2_respond)
    g.add_node("tool_dispatch", _node_tool_dispatch)
    g.set_entry_point("rag_retrieve")
    g.add_edge("rag_retrieve", "k2_respond")
    g.add_conditional_edges(
        "k2_respond",
        _route_after_respond,
        {"tool_dispatch": "tool_dispatch", "end": END},
    )
    g.add_edge("tool_dispatch", "k2_respond")
    return g.compile()


@dataclass
class CaseChatAgent:
    case: PatientCase
    bus: EventBus = field(default_factory=EventBus)
    messages: list[ChatMessage] = field(default_factory=list)
    _graph: Any = None
    _case_summary: str = ""
    _case_dict: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._case_summary = _slim_case(self.case)
        self._case_dict = self.case.model_dump()

    @property
    def available(self) -> bool:
        return has_kimi_key()

    async def send(self, user_msg: str) -> ChatMessage:
        if not self.available:
            await self.bus.emit(
                EventKind.CHAT_ANSWER_DELTA,
                "answer",
                {"delta": "Chat disabled — K2_API_KEY not configured."},
            )
            await self.bus.emit(EventKind.CHAT_DONE, "done", {})
            return ChatMessage(role="assistant", content="Chat disabled.")

        if self._graph is None:
            self._graph = _build_graph()

        self.messages.append(ChatMessage(role="user", content=user_msg))
        state: ChatState = {
            "messages": self.messages,
            "case_summary": self._case_summary,
            "pending_tool_calls": [],
            "rag_hits": [],
            "last_assistant_text": "",
            "last_assistant_thinking": "",
            "iteration": 0,
        }
        state["bus"] = self.bus           # type: ignore[typeddict-unknown-key]
        state["case_dict"] = self._case_dict  # type: ignore[typeddict-unknown-key]

        set_current_bus(self.bus)
        try:
            await self._graph.ainvoke(state)
        finally:
            last = self.messages[-1] if self.messages else None
            citations = (
                list(last.citations)
                if last is not None and last.role == "assistant"
                else []
            )
            await self.bus.emit(
                EventKind.CHAT_DONE, "done", {"citations": citations},
            )

        return self.messages[-1]

    async def stream_events(self) -> AsyncIterator[AgentEvent]:
        async for ev in self.bus.stream():
            yield ev
