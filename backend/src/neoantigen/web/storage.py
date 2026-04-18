"""In-process case storage.

Hackathon-simple: one dict keyed by case_id. Swap for SQLite later if multi-
process is needed. Each entry holds the current ``PatientCase``, the
``EventBus`` for the run (so SSE can bridge it live), and a completion flag.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..agent.events import AgentEvent, EventBus
from ..models import PatientCase


@dataclass
class CaseRecord:
    case_id: str
    case: PatientCase
    bus: EventBus = field(default_factory=EventBus)
    replay: list[AgentEvent] = field(default_factory=list)
    done: bool = False
    # Fanout queues so multiple subscribers (multiple open tabs) can all receive
    # the same events. New subscribers get the replay first, then live events.
    _subscribers: list[asyncio.Queue[AgentEvent | None]] = field(default_factory=list)
    _fanout_task: asyncio.Task | None = None

    def _ensure_fanout(self) -> None:
        if self._fanout_task is not None:
            return

        async def _pump() -> None:
            async for ev in self.bus.stream():
                self.replay.append(ev)
                for q in list(self._subscribers):
                    try:
                        q.put_nowait(ev)
                    except asyncio.QueueFull:
                        pass
            self.done = True
            for q in list(self._subscribers):
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass

        self._fanout_task = asyncio.create_task(_pump())

    async def subscribe(self) -> asyncio.Queue[AgentEvent | None]:
        self._ensure_fanout()
        q: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        for ev in self.replay:
            q.put_nowait(ev)
        if self.done:
            q.put_nowait(None)
        else:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[AgentEvent | None]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass


class CaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, CaseRecord] = {}

    def new_case_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def put(self, record: CaseRecord) -> None:
        self._cases[record.case_id] = record

    def get(self, case_id: str) -> CaseRecord | None:
        return self._cases.get(case_id)

    def update_case(self, case_id: str, case: PatientCase) -> None:
        rec = self._cases.get(case_id)
        if rec is not None:
            rec.case = case

    def list_cases(self) -> list[dict[str, Any]]:
        return [
            {"case_id": r.case_id, "done": r.done}
            for r in self._cases.values()
        ]


_STORE: CaseStore | None = None


def store() -> CaseStore:
    global _STORE
    if _STORE is None:
        _STORE = CaseStore()
    return _STORE
