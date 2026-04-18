"""Live activity feed for the agent orchestrator.

The EventBus is an asyncio.Queue wrapper with typed events. Tools emit events at
start/end, and the Streamlit UI consumes them via an async generator for live
activity feed rendering.
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
    STRUCTURE_READY = "structure_ready"
    EMAIL_DRAFTED = "email_drafted"
    EMAIL_SENT = "email_sent"
    CASE_UPDATE = "case_update"
    LOG = "log"
    DONE = "done"


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
    """Single-producer async event queue. Call `emit` from tools, `stream` from UI."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._closed = False

    async def emit(self, kind: EventKind, label: str, payload: dict[str, Any] | None = None) -> None:
        if self._closed:
            return
        await self._queue.put(AgentEvent(kind=kind, label=label, payload=payload or {}))

    def emit_sync(self, kind: EventKind, label: str, payload: dict[str, Any] | None = None) -> None:
        """Emit from a synchronous context — uses put_nowait."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(AgentEvent(kind=kind, label=label, payload=payload or {}))
        except asyncio.QueueFull:
            pass

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
    """Convenience: emit to the ambient current bus if set."""
    bus = current_bus()
    if bus is not None:
        await bus.emit(kind, label, payload)
