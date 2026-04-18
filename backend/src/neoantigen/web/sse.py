"""SSE helpers — bridge an ``EventBus`` (or a fanout subscriber queue) to a
Server-Sent Events stream the frontend can consume via ``EventSource``.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from ..agent.events import AgentEvent


def format_event(event: AgentEvent) -> dict[str, str]:
    """Format for sse-starlette's EventSourceResponse (dict with event/data keys)."""
    return {
        "event": event.kind.value,
        "data": json.dumps({
            "kind": event.kind.value,
            "label": event.label,
            "payload": event.payload,
            "timestamp": event.timestamp,
        }),
    }


async def queue_to_sse(
    queue: asyncio.Queue[AgentEvent | None],
    *,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-ready dicts from a fanout subscriber queue.

    Emits a comment-style heartbeat every ``heartbeat_seconds`` so intermediate
    proxies don't close an idle connection.
    """
    while True:
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
        except asyncio.TimeoutError:
            yield {"event": "ping", "data": "{}"}
            continue
        if ev is None:
            yield {"event": "stream_end", "data": "{}"}
            break
        yield format_event(ev)
