"""Kimi K2 client for the post-run chat agent.

The chat brain is INDEPENDENT from the orchestrator's medical reasoning
model. In local dev we tunnel ``K2_BASE_URL`` to a GH200 vLLM serving
MediX-R1 — that model is a JSON-extraction reasoner, not a conversational
tool-caller, so routing chat there produces empty streams. Chat must stay
on the real Kimi/K2 cloud endpoint unless the user explicitly overrides it.

Env vars (all chat-specific, fall back cleanly when unset):

    KIMI_API_KEY     required (legacy: K2_API_KEY accepted as a last resort)
    KIMI_BASE_URL    default https://api.k2think.ai/v1
    KIMI_MODEL       default MBZUAI-IFM/K2-Think-v2

Two functions:

* ``k2_stream_with_thinking(...)`` - async generator yielding
  ``("thinking", chunk)`` and ``("answer", chunk)`` tuples. Used for the
  final user-visible response.
* ``k2_call_with_tools(...)`` - single-shot tool-aware call returning the
  parsed `ChatCompletion` with `.choices[0].message.tool_calls` populated.
  Used by the LangGraph router to decide which tools to invoke.
"""

from __future__ import annotations

import ast
import os
import re
from functools import lru_cache
from typing import AsyncIterator, Literal

# K2-Think emits a protocol marker right after </think> announcing whether it
# decided to call a tool. The line looks like:
#   FN_CALL=False     → what follows is the spoken answer
#   FN_CALL=True      → what follows is a Python-style call expression,
#                       e.g. highlight_section(section='trials')
_FN_CALL_LINE_RE = re.compile(r"^\s*FN_CALL\s*=\s*(True|False)\s*(?:\n|$)")
_OTHER_PROTOCOL_LINE_RE = re.compile(r"^\s*(?:[A-Z_]+=\S+)\s*(?:\n|$)")


def _parse_k2think_call(expr: str) -> dict | None:
    """Parse a Python-style call expression into an OpenAI tool_call payload.

    K2-Think writes tool calls as prose, not as OpenAI JSON. Example input:
        highlight_section(section='trials', focus='NCT05')
    Returns ``{"id": "...", "name": "...", "arguments": "<json>"}`` or None
    on any parse error — the caller then falls back to a plain answer.
    """
    expr = expr.strip()
    if not expr:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    call = getattr(tree, "body", None)
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    name = call.func.id
    args: dict = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        try:
            args[kw.arg] = ast.literal_eval(kw.value)
        except Exception:
            return None
    import json as _json
    import uuid as _uuid
    return {
        "id": f"k2t_{_uuid.uuid4().hex[:10]}",
        "name": name,
        "arguments": _json.dumps(args),
    }

# Reuse the orchestrator's file-logger so chat entries land in k2.log
# alongside orchestrator calls (easier to debug "did the chat call even fire?"
# without tailing two files).
from ..agent._llm import get_logger

logger = get_logger()


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

# Default Kimi/K2 cloud endpoint + model. Kept as module constants so the
# health endpoint and the client share the same source of truth.
_KIMI_DEFAULT_BASE_URL = "https://api.k2think.ai/v1"
_KIMI_DEFAULT_MODEL = "MBZUAI-IFM/K2-Think-v2"


def _base_url() -> str:
    # Deliberately does NOT read K2_BASE_URL — that variable is for the
    # orchestrator and often points at a tunneled MediX vLLM, which would
    # silently break chat if we inherited it.
    return os.environ.get("KIMI_BASE_URL", _KIMI_DEFAULT_BASE_URL)


def _model_name() -> str:
    return os.environ.get("KIMI_MODEL", _KIMI_DEFAULT_MODEL)


def _kimi_keys() -> list[str]:
    """Round-robin pool of Kimi/K2 cloud keys.

    Reuses the orchestrator's pool discovery (KIMI_API_KEY_N, K2_API_KEY_N,
    comma-separated forms, dedupe) so chat automatically picks up any extra
    keys the user rotates in.
    """
    from ..agent._llm import _k2_api_keys

    return _k2_api_keys()


def _kimi_key() -> str | None:
    keys = _kimi_keys()
    return keys[0] if keys else None


def has_kimi_key() -> bool:
    return bool(_kimi_keys())


import itertools as _itertools

_chat_rr_counter = _itertools.count(0)


@lru_cache(maxsize=16)
def _client_for_key(api_key: str, base_url: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _client():
    keys = _kimi_keys()
    if not keys:
        raise RuntimeError("KIMI_API_KEY not set - chat agent disabled")
    base_url = _base_url()
    idx = next(_chat_rr_counter) % len(keys)
    key = keys[idx]
    logger.info(
        "chat client base=%s model=%s key_idx=%d pool=%d",
        base_url, _model_name(), idx, len(keys),
    )
    return _client_for_key(key, base_url)


async def k2_stream_with_thinking(
    messages: list[dict],
    *,
    max_tokens: int = 1500,
    tools: list[dict] | None = None,
) -> AsyncIterator[tuple[Literal["thinking", "answer", "tool_call"], object]]:
    """Stream K2 reply, splitting on `<think>...</think>` boundaries.

    Yields:
      ("thinking", str_chunk)   - content inside <think>
      ("answer",   str_chunk)   - content after </think>
      ("tool_call", payload)    - full tool call (only emitted at end of stream
                                  if K2 chose tools instead of free text).
    """
    client = _client()

    create_kwargs: dict = dict(
        model=_model_name(),
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
        temperature=0.6,
        # Ask the server to suppress the thinking pass entirely when the
        # backend supports it (Qwen/vLLM family honors this via
        # chat_template_kwargs). If the endpoint ignores the extra_body we
        # still have the prompt-level guardrails doing the job.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    if tools:
        create_kwargs["tools"] = tools
        create_kwargs["tool_choice"] = "auto"

    try:
        stream = await client.chat.completions.create(**create_kwargs)
    except Exception:
        # Some hosted endpoints 400 on unknown extra_body keys — retry once
        # without the thinking override so chat still works on those.
        create_kwargs.pop("extra_body", None)
        stream = await client.chat.completions.create(**create_kwargs)

    # States:
    #   pre                 - haven't seen </think> yet (reasoning phase)
    #   thinking            - between <think> ... </think> (rare; only when
    #                         the model uses opening tag)
    #   post_think_decide   - saw </think>, haven't decided FN_CALL yet;
    #                         accumulating silently until the first line lands
    #   answer              - streaming the spoken answer
    #   tool_call_text      - accumulating K2's textual tool call silently;
    #                         parsed and yielded at stream end
    state: Literal[
        "pre", "thinking", "post_think_decide", "answer", "tool_call_text"
    ] = "pre"
    buffer = ""
    tool_call_accum: dict[int, dict] = {}
    tool_call_text_buf = ""
    total_chunks = 0
    total_text = 0

    async for chunk in stream:
        total_chunks += 1
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # Some reasoning-style endpoints emit the chain-of-thought on a
        # separate ``reasoning_content`` / ``reasoning`` field and the final
        # answer on ``content``. Surface the reasoning as "thinking" so the
        # caller can drop it — or just ignore it here. We intentionally do
        # NOT yield reasoning tokens so the avatar never speaks them.
        _reasoning = getattr(delta, "reasoning_content", None) or getattr(
            delta, "reasoning", None
        )
        if _reasoning:
            # Silently drop — not part of the user-visible answer.
            continue

        # Tool calls first - K2/OpenAI streams them in fragments per index
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
        total_text += len(text)
        buffer += text

        while True:
            if state == "pre":
                # K2-Think streams chain-of-thought with NO opening <think>
                # tag but a closing </think> before the real answer. So "pre"
                # has to watch for either tag; whichever shows up first wins.
                open_idx = buffer.find(_THINK_OPEN)
                close_idx = buffer.find(_THINK_CLOSE)
                # If we see </think> first (or see it at all without an open
                # tag), treat everything up to and including </think> as
                # reasoning and drop it. The answer begins right after.
                if close_idx != -1 and (open_idx == -1 or close_idx < open_idx):
                    pre_text = buffer[:close_idx]
                    buffer = buffer[close_idx + len(_THINK_CLOSE):].lstrip()
                    state = "post_think_decide"
                    if pre_text:
                        yield ("thinking", pre_text)
                    continue
                if open_idx == -1:
                    # No tags at all yet. Assume this is the reasoning pass —
                    # buffer it as thinking and keep a small tail in case
                    # </think> straddles a chunk boundary.
                    safe_len = max(0, len(buffer) - (len(_THINK_CLOSE) - 1))
                    if safe_len > 0:
                        emit_text, buffer = buffer[:safe_len], buffer[safe_len:]
                        yield ("thinking", emit_text)
                    break
                pre_text = buffer[:open_idx]
                buffer = buffer[open_idx + len(_THINK_OPEN):]
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

            if state == "post_think_decide":
                # Need a full first line OR a terminator before we decide.
                # If no newline yet and buffer is short, wait for more.
                if "\n" not in buffer and len(buffer) < 40:
                    break
                m = _FN_CALL_LINE_RE.match(buffer)
                if m:
                    verdict = m.group(1)
                    buffer = buffer[m.end():].lstrip()
                    if verdict == "True":
                        state = "tool_call_text"
                        continue
                    # FN_CALL=False → fall through to answer streaming.
                # Drop any other protocol key=val lines at the top
                # (FN_NAME=..., THOUGHT=..., etc.) before streaming prose.
                while True:
                    m2 = _OTHER_PROTOCOL_LINE_RE.match(buffer)
                    if not m2:
                        break
                    buffer = buffer[m2.end():]
                state = "answer"
                continue

            if state == "tool_call_text":
                # Silently accumulate until stream ends — we parse the whole
                # expression at the end so incomplete fragments don't confuse
                # the AST parser.
                tool_call_text_buf += buffer
                buffer = ""
                break

            if state == "answer":
                if buffer:
                    emit_text, buffer = buffer, ""
                    yield ("answer", emit_text)
                break

    # Stream closed. Flush per-state tails.
    if state == "tool_call_text":
        tool_call_text_buf += buffer
        parsed = _parse_k2think_call(tool_call_text_buf)
        if parsed is not None:
            yield ("tool_call", parsed)
        else:
            # Parsing failed — don't leak raw prose to the avatar. Log and
            # emit a tiny fallback so the graph doesn't look "frozen".
            logger.warning(
                "K2 tool-call parse failed, buf=%r", tool_call_text_buf[:200],
            )
    elif buffer:
        # In "pre" or "thinking" we've been buffering; drop. In "answer" we
        # flush the tail.
        if state == "answer":
            yield ("answer", buffer)
        elif state == "thinking":
            yield ("thinking", buffer)
        elif state == "post_think_decide":
            # Stream ended mid-decision; try to parse anyway.
            m = _FN_CALL_LINE_RE.match(buffer)
            if m and m.group(1) == "True":
                parsed = _parse_k2think_call(buffer[m.end():].lstrip())
                if parsed is not None:
                    yield ("tool_call", parsed)
            else:
                # Assume it's an answer, strip any leading markers.
                cleaned = buffer
                while True:
                    m2 = _OTHER_PROTOCOL_LINE_RE.match(cleaned)
                    if not m2:
                        break
                    cleaned = cleaned[m2.end():]
                if cleaned.strip():
                    yield ("answer", cleaned)

    for slot in sorted(tool_call_accum.keys()):
        yield ("tool_call", tool_call_accum[slot])

    logger.info(
        "chat stream done chunks=%d text_chars=%d tool_calls=%d state=%s",
        total_chunks, total_text, len(tool_call_accum), state,
    )


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
