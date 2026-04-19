"""Chat route - one turn in, SSE stream of CHAT_* events out.

Each POST starts a fresh ``CaseChatAgent`` turn if one isn't already running
for this case. The same case-keyed chat history survives across turns, so the
user can carry on a conversation.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ...agent.events import AgentEvent, EventBus
from ...chat.agent import Audience, CaseChatAgent
from ...chat.k2_client import has_kimi_key
from ..storage import store

try:
    from sse_starlette.sse import EventSourceResponse  # type: ignore
except ImportError:
    EventSourceResponse = None  # type: ignore


router = APIRouter(prefix="/api/cases", tags=["chat"])


class ChatTurn(BaseModel):
    message: str


# Chat agent lifecycle lives on CaseRecord.chat_agents (keyed by audience).
# Keeping the registry off this module means routes/cases.py can read the
# transcript at PDF-build time without importing this module.


def _agent_for(case_id: str, audience: Audience) -> CaseChatAgent | None:
    rec = store().get(case_id)
    if rec is None:
        return None
    agent = rec.chat_agents.get(audience)
    if agent is None:
        # Fresh EventBus per agent - NOT the orchestrator's bus.
        agent = CaseChatAgent(case=rec.case, bus=EventBus(), audience=audience)
        rec.chat_agents[audience] = agent
    else:
        # Refresh case reference in case orchestrator ran again
        agent.case = rec.case
        agent._refresh_case_summary()
    return agent


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
async def chat(
    case_id: str,
    turn: ChatTurn,
    audience: Literal["oncologist", "patient"] = Query("oncologist"),
):
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    if not has_kimi_key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat disabled - KIMI_API_KEY not configured on server.",
        )
    if EventSourceResponse is None:
        raise HTTPException(status_code=500, detail="sse-starlette not installed.")

    agent = _agent_for(case_id, audience)
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
        # For chat, a single subscriber is fine - the frontend POSTs once per turn.
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
