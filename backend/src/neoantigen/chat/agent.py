"""LangGraph-driven chat agent for the post-run melanoma case.

State graph (one user turn = one full traversal):

    user_msg
        ▼
    [router] ──── tool_calls? ──► [tool_dispatch] ──┐
        │                                            │
    needs_rag?                                       │
        │                                            ▼
    [rag_retrieve] ────────────────────────────► [k2_respond] (stream)
                                                     │
                                              tool_calls? ─┐
                                                     │     │
                                                    END    └─► [tool_dispatch] (loop, max 3)

* Streaming events (`<think>` blocks + answer chunks) are emitted to the
  ambient ``EventBus`` out-of-band so the Streamlit UI can render them live.
* Conversation memory: every turn appends to ``state.messages``. The full
  list is sent to K2 each call so it remembers past Q&A across turns.
* RAG: triggered when the router thinks the question needs literature.
* Tools: registered in ``chat/tools.py``. Up to 3 tool-call rounds per turn.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from ..agent.events import AgentEvent, EventBus, EventKind, set_current_bus
from ..models import MelanomaCase
from ..rag import has_store as _rag_available, query_papers
from .k2_client import has_kimi_key, k2_call_with_tools, k2_stream_with_thinking
from .state import ChatMessage, ChatState, ToolCall
from .tools import TOOL_SCHEMAS, execute_tool


MAX_TOOL_LOOPS = 3


SYSTEM_PROMPT = """You are an oncologist's clinical copilot. The patient's full
case workup has already been completed by another agent — pathology read,
mutations parsed, NCCN guideline walked, molecular landscape built, vaccine
candidates designed, and twin-cohort survival computed. You have the full case
summary in your context.

Your job is to help the doctor drill into this case for tumor-board prep.
Answer follow-up questions, explain why the upstream agent made each decision,
pull additional literature when asked, and use tools to highlight relevant
panels in the doctor's UI.

Rules:
* Always reason inside <think>...</think> first, then write the user-facing
  answer.
* When the doctor asks to "show me" something, call the highlight_panel or
  show_twin tool.
* When the doctor asks for evidence or recent papers, call pubmed_search.
* When the doctor asks "why did you pick X at node Y?", call explain_node.
* Be concise. The doctor is preparing for tumor board, not reading a textbook.
* Cite PMIDs inline when you reference a paper.
"""


def _slim_case(case: MelanomaCase) -> str:
    """Render the case as a token-efficient string (~2-3K tokens)."""
    p = case.pathology
    lines = [
        "PATHOLOGY",
        f"  subtype: {p.melanoma_subtype}",
        f"  Breslow: {p.breslow_thickness_mm} mm" if p.breslow_thickness_mm else "  Breslow: unknown",
        f"  ulceration: {p.ulceration}",
        f"  T-stage: {p.t_stage}",
        f"  TILs: {p.tils_present}, PD-L1: {p.pdl1_estimate}",
        "",
        f"MUTATIONS ({len(case.mutations)}):",
    ]
    for m in case.mutations[:25]:
        lines.append(f"  {m.gene} {m.label}")
    if len(case.mutations) > 25:
        lines.append(f"  …and {len(case.mutations) - 25} more")

    if case.nccn_path:
        lines.append("")
        lines.append("NCCN PATH:")
        for s in case.nccn_path:
            reasoning_one_line = (s.reasoning or "").strip().splitlines()
            tip = reasoning_one_line[0][:140] if reasoning_one_line else ""
            lines.append(f"  [{s.node_id}] {s.node_title} → {s.chosen_option}")
            if tip:
                lines.append(f"      ↳ {tip}")

    if case.pipeline and case.pipeline.candidates:
        lines.append("")
        lines.append("TOP VACCINE PEPTIDES:")
        for c in case.pipeline.candidates[:5]:
            lines.append(
                f"  #{c.rank} {c.peptide.sequence}  "
                f"({c.peptide.mutation.full_label}, "
                f"{c.peptide.score_nm:.1f} nM)"
                if c.peptide.score_nm is not None
                else f"  #{c.rank} {c.peptide.sequence}  ({c.peptide.mutation.full_label})"
            )

    if case.cohort:
        lines.append("")
        lines.append(
            f"TCGA COHORT: n={case.cohort.cohort_size} · "
            f"median OS overall={case.cohort.median_survival_days}d · "
            f"twins={case.cohort.twin_median_survival_days}d"
        )
        for t in case.cohort.twins[:3]:
            lines.append(
                f"  twin {t.submitter_id} sim={t.similarity:.2f} "
                f"stage={t.stage} status={t.vital_status} survival={t.survival_days}d"
            )

    if case.final_recommendation:
        lines.append("")
        lines.append(f"FINAL RECOMMENDATION: {case.final_recommendation}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# LangGraph nodes
# ─────────────────────────────────────────────────────────────────


def _needs_rag(question: str) -> bool:
    """Cheap heuristic — avoid a router LLM call for the obvious cases."""
    triggers = ["paper", "literature", "evidence", "study", "trial",
                "cite", "pmid", "publish", "recent", "review"]
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
    if last_user is None:
        return state
    if not _needs_rag(last_user.content):
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
    """Stream K2's answer. Emits THINKING_DELTA / ANSWER_DELTA / TOOL_CALL events."""
    sys_msg = {
        "role": "system",
        "content": SYSTEM_PROMPT + "\n\nCASE SUMMARY:\n" + state.get("case_summary", ""),
    }
    if state.get("rag_hits"):
        cite_lines = ["PUBMED HITS FROM A FRESH SEARCH (cite these inline):"]
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
                f"🔧 {tc.name}({json.dumps(tc.arguments)[:80]})",
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
    """Lazy-built so importing the module doesn't require langgraph."""
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


# ─────────────────────────────────────────────────────────────────
# Public agent
# ─────────────────────────────────────────────────────────────────


@dataclass
class CaseChatAgent:
    case: MelanomaCase
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
        """Run one full turn. Streams events through ``self.bus``;
        returns the final assistant ChatMessage."""
        if not self.available:
            await self.bus.emit(
                EventKind.CHAT_ANSWER_DELTA,
                "answer",
                {"delta": "K2 (KIMI_API_KEY) not configured — chat disabled."},
            )
            await self.bus.emit(EventKind.CHAT_DONE, "done", {})
            return ChatMessage(role="assistant", content="K2 not configured.")

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
        # Smuggle bus + case dict through the state without typing them
        state["bus"] = self.bus           # type: ignore[typeddict-unknown-key]
        state["case_dict"] = self._case_dict  # type: ignore[typeddict-unknown-key]

        set_current_bus(self.bus)
        try:
            await self._graph.ainvoke(state)
        finally:
            await self.bus.emit(EventKind.CHAT_DONE, "done", {})

        return self.messages[-1]

    async def stream_events(self) -> AsyncIterator[AgentEvent]:
        """Yield events as they're emitted. Caller drains in parallel with .send()."""
        async for ev in self.bus.stream():
            yield ev
