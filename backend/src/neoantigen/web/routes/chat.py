"""Chat route — one turn in, SSE stream of CHAT_* events out.

Each POST starts a fresh ``CaseChatAgent`` turn if one isn't already running
for this case. The same case-keyed chat history survives across turns, so the
user can carry on a conversation.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...agent.events import AgentEvent, EventBus
from ...chat.agent import CaseChatAgent
from ...chat.k2_client import has_kimi_key
from ..storage import store

try:
    from sse_starlette.sse import EventSourceResponse  # type: ignore
except ImportError:
    EventSourceResponse = None  # type: ignore


router = APIRouter(prefix="/api/cases", tags=["chat"])


class ChatTurn(BaseModel):
    message: str


# One chat agent per case, lazy-constructed.
_AGENTS: dict[str, CaseChatAgent] = {}


def _agent_for(case_id: str) -> CaseChatAgent | None:
    rec = store().get(case_id)
    if rec is None:
        return None
    if case_id not in _AGENTS:
        # Fresh EventBus per agent — NOT the orchestrator's bus.
        _AGENTS[case_id] = CaseChatAgent(case=rec.case, bus=EventBus())
    else:
        # Refresh case reference in case orchestrator ran again
        _AGENTS[case_id].case = rec.case
    return _AGENTS[case_id]


def _format_sse(event: AgentEvent) -> dict[str, str]:
    return {
        "event": event.kind.value,
        "data": json.dumps({
            "kind": event.kind.value,
            "label": event.label,
            "payload": event.payload,
            "timestamp": event.timestamp,
        }),
    }


@router.post("/{case_id}/chat")
async def chat(case_id: str, turn: ChatTurn):
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if not has_kimi_key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat disabled — K2_API_KEY not configured on server.",
        )
    if EventSourceResponse is None:
        raise HTTPException(status_code=500, detail="sse-starlette not installed.")

    agent = _agent_for(case_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    bus = agent.bus

    async def _run_turn() -> None:
        try:
            await agent.send(turn.message)
        except Exception as e:  # noqa: BLE001
            from ...agent.events import EventKind
            try:
                await bus.emit(EventKind.TOOL_ERROR, f"chat crashed: {e}")
                await bus.close()
            except Exception:
                pass

    async def _stream() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(_run_turn())
        # We need a *fresh* stream view; but EventBus.stream consumes the queue.
        # For chat, a single subscriber is fine — the frontend POSTs once per turn.
        try:
            async for ev in bus.stream():
                yield _format_sse(ev)
                from ...agent.events import EventKind
                if ev.kind == EventKind.CHAT_DONE:
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (BaseException, Exception):
                    pass
            # Reset the bus for the next turn so the iterator above gets a
            # clean queue.
            agent.bus = EventBus()

    return EventSourceResponse(_stream())
