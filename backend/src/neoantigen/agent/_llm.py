"""Shared client for the medical reasoning model (MediX-R1-30B via vLLM).

The model is a Qwen3-VL-based VLM served by vLLM with an OpenAI-compatible
endpoint. It supports:

* text + image multimodal inputs (image_url content blocks, base64 data URIs)
* `<think>...</think>` reasoning blocks emitted before the final answer

Three call surfaces:

* `call_for_json(schema, system, user)` — single-shot JSON extraction.
* `call_with_vision(images, system, user, schema)` — same, but with image inputs.
* `stream_with_thinking(system, user)` — async iterator yielding
  `("thinking", chunk)` and `("answer", chunk)` tuples for live UI rendering.

Backend selection is env-driven so we can swap K2 → MediX without touching code:

* `K2_BASE_URL` (default `https://api.k2think.ai/v1`) — point at the SSH-tunneled
  vLLM endpoint, e.g. `http://localhost:8000/v1`.
* `K2_API_KEY` — required by the OpenAI client (vLLM ignores its value).
* `NEOVAX_MODEL` — served model name, e.g. `medix-r1-30b`.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import AsyncIterator, Literal, TypeVar

from pydantic import BaseModel, ValidationError


K2_BASE_URL = os.environ.get("K2_BASE_URL", "https://api.k2think.ai/v1")
DEFAULT_MODEL = os.environ.get("NEOVAX_MODEL_DEFAULT", "MBZUAI-IFM/K2-Think-v2")

# MediX-R1-30B (Qwen3-VL-based) on the GH200 SSH tunnel — used for any call that
# needs vision (pathology slide reading). Defaults assume the tunnel is up at
# localhost:8000 (set up via `ssh -L 8000:localhost:8000 gh200-vm`).
MEDIX_BASE_URL = os.environ.get("MEDIX_BASE_URL", "http://localhost:8000/v1")
MEDIX_DEFAULT_MODEL = "medix-r1-30b"

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    """File-only logger for every model call. Path overridable via NEOVAX_LOG_PATH."""
    logger = logging.getLogger("neoantigen.llm")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers:
        return logger

    default_log_path = Path(__file__).resolve().parents[3] / "out" / "k2.log"
    log_path = Path(os.environ.get("NEOVAX_LOG_PATH", default_log_path))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.info("LLM logger initialized (path=%s, base_url=%s)", log_path, K2_BASE_URL)
    return logger


def has_api_key() -> bool:
    return bool(os.environ.get("K2_API_KEY"))


def has_medix_key() -> bool:
    """MediX (vLLM on GH200) accepts any non-empty key string.

    We treat ``MEDIX_API_KEY`` being set (even to ``"dummy"``) as the operator's
    intent to route vision calls to the GH200 tunnel.
    """
    return bool(os.environ.get("MEDIX_API_KEY"))


def _model_name() -> str:
    return os.environ.get("NEOVAX_MODEL", DEFAULT_MODEL)


def _medix_model_name() -> str:
    return os.environ.get("MEDIX_MODEL", MEDIX_DEFAULT_MODEL)


@lru_cache(maxsize=1)
def _openai_client():
    """K2 cloud client — used for text reasoning (NCCN walker, JSON tasks)."""
    from openai import AsyncOpenAI

    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise RuntimeError("K2_API_KEY not set")
    return AsyncOpenAI(base_url=K2_BASE_URL, api_key=api_key)


@lru_cache(maxsize=1)
def _medix_client():
    """MediX-R1-30B on the GH200 vLLM tunnel — used for vision (pathology slides)."""
    from openai import AsyncOpenAI

    api_key = os.environ.get("MEDIX_API_KEY")
    if not api_key:
        raise RuntimeError("MEDIX_API_KEY not set — bring up the GH200 tunnel first")
    return AsyncOpenAI(base_url=MEDIX_BASE_URL, api_key=api_key)


# ─────────────────────────────────────────────────────────────
# Reasoning-block parsing
# ─────────────────────────────────────────────────────────────

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def strip_think(text: str) -> str:
    """Drop the model's reasoning prefix and return only the post-`</think>` text."""
    if _THINK_CLOSE in text:
        text = text.rsplit(_THINK_CLOSE, 1)[1]
    return text.strip()


def split_thinking(text: str) -> tuple[str, str]:
    """Split a complete response into (thinking, answer).

    If `<think>` is absent, returns ("", text). If `</think>` is missing, treats
    the entire text as thinking with empty answer.
    """
    if _THINK_OPEN not in text and _THINK_CLOSE not in text:
        return "", text.strip()
    after_open = text.split(_THINK_OPEN, 1)[-1]
    if _THINK_CLOSE in after_open:
        thinking, answer = after_open.split(_THINK_CLOSE, 1)
        return thinking.strip(), answer.strip()
    return after_open.strip(), ""


def _extract_json(text: str) -> str:
    """Pull the first valid top-level JSON object out of a model response."""
    cleaned = strip_think(text)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)

    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    depth = 0
    start = -1
    for i, c in enumerate(cleaned):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = cleaned[start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    start = -1
    raise json.JSONDecodeError("no valid JSON object found in response", cleaned, 0)


# ─────────────────────────────────────────────────────────────
# Image encoding
# ─────────────────────────────────────────────────────────────


def _encode_image(image: Path | bytes, mime_hint: str | None = None) -> str:
    """Return a `data:image/...;base64,...` URI suitable for OpenAI image_url."""
    if isinstance(image, Path):
        mime = mime_hint or mimetypes.guess_type(image.name)[0] or "image/jpeg"
        data = image.read_bytes()
    else:
        mime = mime_hint or "image/jpeg"
        data = image
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _user_content_with_images(
    text: str, images: list[Path | bytes] | None
) -> list[dict] | str:
    if not images:
        return text
    parts: list[dict] = []
    for img in images:
        parts.append({"type": "image_url", "image_url": {"url": _encode_image(img)}})
    parts.append({"type": "text", "text": text})
    return parts


# ─────────────────────────────────────────────────────────────
# Public call surfaces
# ─────────────────────────────────────────────────────────────


async def call_for_json(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 2000,
) -> T:
    """Single-turn structured response on K2 (text only)."""
    return await _call_json_impl(
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=None,
        max_tokens=max_tokens,
        client=_openai_client(),
        model=_model_name(),
    )


async def call_with_vision(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    images: list[Path | bytes] | None = None,
    max_tokens: int = 2000,
) -> T:
    """Vision-capable JSON call routed to MediX-R1-30B on the GH200 tunnel.

    K2 has no vision; this is the only call surface that handles ``image_url``
    content blocks. Requires ``MEDIX_API_KEY`` and an open SSH tunnel
    (default ``MEDIX_BASE_URL=http://localhost:8000/v1``).
    """
    return await _call_json_impl(
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=images,
        max_tokens=max_tokens,
        client=_medix_client(),
        model=_medix_model_name(),
    )


async def _call_json_impl(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    images: list[Path | bytes] | None,
    max_tokens: int,
    client,
    model: str,
) -> T:
    """Shared JSON-extracting call. Routed by caller to K2 or MediX."""
    log = get_logger()
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    augmented_system = (
        system_prompt.rstrip()
        + "\n\nYou MUST respond with a single JSON object matching this schema:\n"
        + schema_json
        + "\n\nReturn ONLY the JSON object after your reasoning. No markdown, no prose."
    )
    user_content = _user_content_with_images(user_prompt, images)
    log.info(
        "call schema=%s images=%d user_len=%d",
        schema.__name__, len(images or []), len(user_prompt),
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": augmented_system},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as e:
        log.error("call HTTP error schema=%s model=%s err=%s: %s",
                  schema.__name__, model, type(e).__name__, e)
        raise

    raw = resp.choices[0].message.content or ""
    log.info("call response schema=%s len=%d", schema.__name__, len(raw))
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as e:
        log.error("JSON parse failed schema=%s raw=%r", schema.__name__, raw[:600])
        raise ValueError(f"model did not return valid JSON: {raw[:300]!r}") from e
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        log.error("validation failed schema=%s err=%s data=%s", schema.__name__, e, data)
        raise ValueError(f"model JSON failed {schema.__name__} validation: {e}") from e


async def stream_with_thinking(
    system_prompt: str,
    user_prompt: str,
    *,
    images: list[Path | bytes] | None = None,
    max_tokens: int = 2000,
) -> AsyncIterator[tuple[Literal["thinking", "answer"], str]]:
    """Stream the model's response, tagging each chunk as 'thinking' or 'answer'.

    The model emits `<think>...</think>` then the answer. We track which region
    we're currently in across chunk boundaries and yield `(region, delta_text)`.
    """
    log = get_logger()
    client = _openai_client()
    user_content = _user_content_with_images(user_prompt, images)
    log.info("stream_with_thinking start user_len=%d images=%d", len(user_prompt), len(images or []))

    state: Literal["pre", "thinking", "answer"] = "pre"
    buffer = ""

    try:
        stream = await client.chat.completions.create(
            model=_model_name(),
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as e:
        log.error("stream HTTP error: %s: %s", type(e).__name__, e)
        raise

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        buffer += delta

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
    log.info("stream_with_thinking done")
