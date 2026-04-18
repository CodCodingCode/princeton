"""Live activity feed for the patient orchestrator.

The EventBus is an asyncio.Queue wrapper with typed events. The orchestrator,
NCCN walker, and chat agent emit events at every meaningful step; the Next.js
UI consumes them via Server-Sent Events and routes by EventKind.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class EventKind(str, Enum):
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    LOG = "log"
    DONE = "done"

    THINKING_DELTA = "thinking_delta"
    ANSWER_DELTA = "answer_delta"

    # Patient-flow events
    DOC_EXTRACTED = "doc_extracted"
    AGGREGATION_START = "aggregation_start"
    AGGREGATION_DONE = "aggregation_done"
    PDF_EXTRACTED = "pdf_extracted"
    NCCN_NODE_VISITED = "nccn_node_visited"
    RAILWAY_STEP = "railway_step"
    RAILWAY_READY = "railway_ready"
    RAG_CITATIONS = "rag_citations"
    TRIAL_MATCHES_READY = "trial_matches_ready"
    TRIAL_SITES_READY = "trial_sites_ready"
    CASE_UPDATE = "case_update"

    # Chat agent events
    CHAT_THINKING_DELTA = "chat_thinking_delta"
    CHAT_ANSWER_DELTA = "chat_answer_delta"
    CHAT_TOOL_CALL = "chat_tool_call"
    CHAT_TOOL_RESULT = "chat_tool_result"
    CHAT_UI_FOCUS = "chat_ui_focus"
    CHAT_DONE = "chat_done"


@dataclass
class AgentEvent:
    kind: EventKind
    label: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class EventBus:
    """Single-producer async event queue with an out-of-band interrupt slot."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._closed = False
        self._interrupt: str | None = None

    async def emit(self, kind: EventKind, label: str, payload: dict[str, Any] | None = None) -> None:
        if self._closed:
            return
        await self._queue.put(AgentEvent(kind=kind, label=label, payload=payload or {}))

    def emit_sync(self, kind: EventKind, label: str, payload: dict[str, Any] | None = None) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(AgentEvent(kind=kind, label=label, payload=payload or {}))
        except asyncio.QueueFull:
            pass

    def push_interrupt(self, message: str) -> None:
        self._interrupt = message

    def consume_interrupt(self) -> str | None:
        msg, self._interrupt = self._interrupt, None
        return msg

    async def close(self) -> None:
        self._closed = True
        await self._queue.put(None)

    async def stream(self) -> AsyncIterator[AgentEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event


_CURRENT_BUS: EventBus | None = None


def set_current_bus(bus: EventBus | None) -> None:
    global _CURRENT_BUS
    _CURRENT_BUS = bus


def current_bus() -> EventBus | None:
    return _CURRENT_BUS


async def emit(kind: EventKind, label: str, payload: dict[str, Any] | None = None) -> None:
    bus = current_bus()
    if bus is not None:
        await bus.emit(kind, label, payload)
