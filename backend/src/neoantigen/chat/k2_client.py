"""Kimi K2 client for the post-run chat agent.

Mirrors the surface of [agent/_llm.py](../agent/_llm.py) but reads its own env
vars so K2 (cloud, used for chat) and MediX (GH200, used for the orchestrator)
can both be live in the same process.

Env:
    KIMI_BASE_URL    default https://api.k2think.ai/v1
    KIMI_API_KEY     required
    KIMI_MODEL       default MBZUAI-IFM/K2-Think-v2

Two functions:

* ``k2_stream_with_thinking(...)`` — async generator yielding
  ``("thinking", chunk)`` and ``("answer", chunk)`` tuples. Used for the
  final user-visible response.
* ``k2_call_with_tools(...)`` — single-shot tool-aware call returning the
  parsed `ChatCompletion` with `.choices[0].message.tool_calls` populated.
  Used by the LangGraph router to decide which tools to invoke.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import AsyncIterator, Literal


KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.k2think.ai/v1")
KIMI_MODEL_DEFAULT = os.environ.get("KIMI_MODEL_DEFAULT", "MBZUAI-IFM/K2-Think-v2")

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def has_kimi_key() -> bool:
    return bool(os.environ.get("KIMI_API_KEY"))


def _model_name() -> str:
    return os.environ.get("KIMI_MODEL", KIMI_MODEL_DEFAULT)


@lru_cache(maxsize=1)
def _client():
    from openai import AsyncOpenAI

    api_key = os.environ.get("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY not set — chat agent disabled")
    return AsyncOpenAI(base_url=KIMI_BASE_URL, api_key=api_key)


async def k2_stream_with_thinking(
    messages: list[dict],
    *,
    max_tokens: int = 1500,
    tools: list[dict] | None = None,
) -> AsyncIterator[tuple[Literal["thinking", "answer", "tool_call"], object]]:
    """Stream K2 reply, splitting on `<think>...</think>` boundaries.

    Yields:
      ("thinking", str_chunk)   — content inside <think>
      ("answer",   str_chunk)   — content after </think>
      ("tool_call", payload)    — full tool call (only emitted at end of stream
                                  if K2 chose tools instead of free text).
    """
    client = _client()

    create_kwargs: dict = dict(
        model=_model_name(),
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
    )
    if tools:
        create_kwargs["tools"] = tools
        create_kwargs["tool_choice"] = "auto"

    stream = await client.chat.completions.create(**create_kwargs)

    state: Literal["pre", "thinking", "answer"] = "pre"
    buffer = ""
    tool_call_accum: dict[int, dict] = {}

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # Tool calls first — K2/OpenAI streams them in fragments per index
        for tc in (delta.tool_calls or []):
            slot = tool_call_accum.setdefault(
                tc.index,
                {"id": "", "name": "", "arguments": ""},
            )
            if tc.id:
                slot["id"] = tc.id
            if tc.function and tc.function.name:
                slot["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                slot["arguments"] += tc.function.arguments

        text = delta.content or ""
        if not text:
            continue
        buffer += text

        while True:
            if state == "pre":
                idx = buffer.find(_THINK_OPEN)
                if idx == -1:
                    if buffer:
                        state = "answer"
                        emit_text, buffer = buffer, ""
                        if emit_text:
                            yield ("answer", emit_text)
                    break
                pre_text = buffer[:idx]
                buffer = buffer[idx + len(_THINK_OPEN):]
                state = "thinking"
                if pre_text:
                    yield ("answer", pre_text)
                continue

            if state == "thinking":
                idx = buffer.find(_THINK_CLOSE)
                if idx == -1:
                    safe_len = max(0, len(buffer) - (len(_THINK_CLOSE) - 1))
                    if safe_len > 0:
                        emit_text, buffer = buffer[:safe_len], buffer[safe_len:]
                        yield ("thinking", emit_text)
                    break
                think_text = buffer[:idx]
                buffer = buffer[idx + len(_THINK_CLOSE):]
                state = "answer"
                if think_text:
                    yield ("thinking", think_text)
                continue

            if state == "answer":
                if buffer:
                    emit_text, buffer = buffer, ""
                    yield ("answer", emit_text)
                break

    if buffer:
        yield (state if state != "pre" else "answer", buffer)

    for slot in sorted(tool_call_accum.keys()):
        yield ("tool_call", tool_call_accum[slot])


async def k2_call_with_tools(
    messages: list[dict],
    tools: list[dict],
    *,
    max_tokens: int = 800,
) -> dict:
    """One-shot tool-aware call. Returns ``{"text": str, "tool_calls": [...]}``.

    Used by the router node to classify the user's intent in one cheap call.
    """
    client = _client()
    resp = await client.chat.completions.create(
        model=_model_name(),
        messages=messages,
        max_tokens=max_tokens,
        tools=tools,
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    return {
        "text": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in (msg.tool_calls or [])
        ],
    }
