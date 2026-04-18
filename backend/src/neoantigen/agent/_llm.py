"""Shared client for the medical reasoning model (MediX-R1-30B via vLLM).

The model is a Qwen3-VL-based VLM served by vLLM with an OpenAI-compatible
endpoint. It supports:

* text + image multimodal inputs (image_url content blocks, base64 data URIs)
* `<think>...</think>` reasoning blocks emitted before the final answer

Three call surfaces:

* `call_for_json(schema, system, user)` - single-shot JSON extraction.
* `call_with_vision(images, system, user, schema)` - same, but with image inputs.
* `stream_with_thinking(system, user)` - async iterator yielding
  `("thinking", chunk)` and `("answer", chunk)` tuples for live UI rendering.

Backend selection is env-driven so we can swap K2 → MediX without touching code:

* `K2_BASE_URL` (default `https://api.k2think.ai/v1`) - point at the SSH-tunneled
  vLLM endpoint, e.g. `http://localhost:8000/v1`.
* `KIMI_API_KEY` - required by the OpenAI client (vLLM ignores its value).
  Legacy `K2_API_KEY` is still read as a fallback.
* `NEOVAX_MODEL` - served model name, e.g. `medix-r1-30b`.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import types
import typing
from functools import lru_cache
from pathlib import Path
from typing import AsyncIterator, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from .audit import audit


K2_BASE_URL = os.environ.get("K2_BASE_URL", "https://api.k2think.ai/v1")
DEFAULT_MODEL = os.environ.get("NEOVAX_MODEL_DEFAULT", "MBZUAI-IFM/K2-Think-v2")

# MediX-R1-30B (Qwen3-VL-based) on the GH200 SSH tunnel - used for any call that
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


def _k2_api_key() -> str | None:
    # Single source of truth: prefer KIMI_API_KEY, fall back to legacy K2_API_KEY
    # so existing .env files keep working during the transition.
    return os.environ.get("KIMI_API_KEY") or os.environ.get("K2_API_KEY")


def has_api_key() -> bool:
    return bool(_k2_api_key())


def has_medix_key() -> bool:
    """Legacy name kept for callers that gate on "vision-capable model available".

    Everything - text and vision - now routes through K2-Think via
    ``KIMI_API_KEY``, so this collapses to the same check as ``has_api_key()``.
    """
    return has_api_key()


def _model_name() -> str:
    return os.environ.get("NEOVAX_MODEL", DEFAULT_MODEL)


def _medix_model_name() -> str:
    return os.environ.get("MEDIX_MODEL", MEDIX_DEFAULT_MODEL)


# Per-request timeouts (seconds). Without these, a dead SSH tunnel causes the
# orchestrator to hang indefinitely on stage 1.
K2_TIMEOUT_S = float(os.environ.get("NEOVAX_K2_TIMEOUT_S", "90"))
MEDIX_TIMEOUT_S = float(os.environ.get("NEOVAX_MEDIX_TIMEOUT_S", "60"))


@lru_cache(maxsize=1)
def _openai_client():
    """K2 cloud client - used for text reasoning (NCCN walker, JSON tasks)."""
    from openai import AsyncOpenAI

    api_key = _k2_api_key()
    if not api_key:
        raise RuntimeError("KIMI_API_KEY not set")
    return AsyncOpenAI(base_url=K2_BASE_URL, api_key=api_key, timeout=K2_TIMEOUT_S)


@lru_cache(maxsize=1)
def _medix_client():
    """MediX-R1-30B on the GH200 vLLM tunnel - used for vision (pathology slides)."""
    from openai import AsyncOpenAI

    api_key = os.environ.get("MEDIX_API_KEY")
    if not api_key:
        raise RuntimeError("MEDIX_API_KEY not set - bring up the GH200 tunnel first")
    return AsyncOpenAI(
        base_url=MEDIX_BASE_URL, api_key=api_key, timeout=MEDIX_TIMEOUT_S
    )


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
    """Pull the first valid top-level JSON object out of a model response.

    Handles four common model output patterns:
      1. Clean JSON (maybe after a ``<think>`` block).
      2. Markdown-fenced JSON (``` ```json ... ``` ```).
      3. JSON embedded inside prose (depth-scan for balanced braces).
      4. Truncated JSON - model hit ``max_tokens`` mid-object. We try to
         repair by closing unclosed strings, arrays, and objects at the end.

    Noisy-document pages used to trip (3) → ``ValueError`` which surfaced in
    the Documents tab as "(VLM call failed: ValueError)". The repair pass in
    (4) catches the truncation case before it gets there.
    """
    cleaned = strip_think(text).strip()
    # Strip markdown fences in a few common shapes.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    # Depth-scan for a balanced {...} somewhere in the prose.
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

    # Truncation repair. If the model started a JSON object but ran out of
    # tokens, close unclosed strings/arrays/objects and try to parse the
    # result. This recovers a partial but validly-typed object - Pydantic's
    # defaults then fill the unset fields.
    obj_start = cleaned.find("{")
    if obj_start != -1:
        repaired = _repair_truncated_json(cleaned[obj_start:])
        if repaired is not None:
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("no valid JSON object found in response", cleaned, 0)


def _repair_truncated_json(snippet: str) -> str | None:
    """Repair a truncated JSON snippet by rewinding to the last safe
    truncation point and closing any still-open containers.

    Safe truncation points (walked in one pass):
      * Right after ``{`` or ``[`` - empty container is always valid.
      * Right before a ``,`` at container depth - keeps all prior elements.
      * Right after ``}`` or ``]`` - closes a completed container.

    After rewinding, we re-walk the kept prefix to compute the still-open
    brace/bracket stack, then append matching closers.
    """
    # --- Pass 1: find the last safe truncation point ------------------------
    stack: list[str] = []
    in_str = False
    escape = False
    safe_len = 0  # Exclusive-end index; 0 means "nothing safe yet".

    for i, c in enumerate(snippet):
        if escape:
            escape = False
            continue
        if in_str:
            if c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
            continue
        if c in "{[":
            stack.append(c)
            safe_len = i + 1
        elif c in "}]":
            if not stack:
                return None
            opener = stack[-1]
            if (opener == "{" and c != "}") or (opener == "[" and c != "]"):
                return None
            stack.pop()
            safe_len = i + 1
        elif c == "," and stack:
            # Truncate BEFORE the comma, preserving prior elements.
            safe_len = i

    if safe_len == 0:
        return None

    # --- Pass 2: recompute stack depth at safe_len --------------------------
    d_stack: list[str] = []
    d_in_str = False
    d_escape = False
    for j in range(safe_len):
        c = snippet[j]
        if d_escape:
            d_escape = False
            continue
        if d_in_str:
            if c == "\\":
                d_escape = True
            elif c == '"':
                d_in_str = False
            continue
        if c == '"':
            d_in_str = True
            continue
        if c in "{[":
            d_stack.append(c)
        elif c in "}]":
            if d_stack:
                d_stack.pop()

    body = snippet[:safe_len].rstrip().rstrip(",").rstrip()
    while d_stack:
        opener = d_stack.pop()
        body += "}" if opener == "{" else "]"
    return body


# ─────────────────────────────────────────────────────────────
# Lenient pre-validation coercion + error formatting
#
# VLMs frequently paraphrase enum values ("Nodular Melanoma" vs "nodular"),
# return prose for booleans ("Yes", "not present"), or write "not applicable"
# in numeric fields. The hints in the system prompt help but don't fully fix
# this. These helpers normalize common drift before Pydantic sees the dict so
# the first attempt validates more often, and `_format_validation_errors`
# renders any remaining failures into a corrective message for one retry.
# ─────────────────────────────────────────────────────────────


_LITERAL_PUNCT = re.compile(r"[\s\-]+")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_NUMERIC_TOKEN = re.compile(r"-?\d+(?:\.\d+)?")

_BOOL_TRUE = {"yes", "true", "present", "positive", "ulcerated", "y"}
_BOOL_FALSE = {"no", "false", "absent", "not present", "negative", "none", "n"}
_NULL_STRINGS = {"not applicable", "n/a", "na", "unknown", "none", "null", ""}


def _normalize_literal(s: str) -> str:
    s = _PARENTHETICAL.sub("", s).strip().lower()
    s = _LITERAL_PUNCT.sub("_", s)
    return s.strip("_")


_UNKNOWN_PHRASES = {
    "unknown", "not_applicable", "not_assessable", "not_assessed",
    "not_present", "not_evaluated", "none", "na", "n_a", "not_specified",
    "not_reported", "indeterminate", "unclear",
}


def _match_literal(value, allowed: tuple) -> object:
    if value in allowed:
        return value
    if not isinstance(value, str):
        return value
    norm = _normalize_literal(value)
    if norm in allowed:
        return norm
    parts = norm.split("_")
    for n in (parts[0], parts[-1], "_".join(parts[:-1])):
        if n and n in allowed:
            return n
    candidates = [a for a in allowed if isinstance(a, str) and (a in norm or norm in a)]
    if len(candidates) == 1:
        return candidates[0]
    # "not applicable" / "not assessable" / "not present" → "unknown" when allowed
    if "unknown" in allowed and norm in _UNKNOWN_PHRASES:
        return "unknown"
    return value


def _annotation_alternatives(annotation):
    """Flatten a possibly-Union annotation into [(origin, args), ...].

    Handles both `typing.Union[X, Y]` and PEP-604 `X | Y` (types.UnionType).
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        out = []
        for a in typing.get_args(annotation):
            inner = typing.get_origin(a)
            out.append((inner if inner is not None else a, typing.get_args(a)))
        return out
    return [(origin if origin is not None else annotation, typing.get_args(annotation))]


def _coerce_field(value, annotation):
    if value is None:
        return value
    alts = _annotation_alternatives(annotation)
    accepts_none = any(a is type(None) for a, _ in alts)

    for a, args in alts:
        if a is Literal and args and all(isinstance(x, str) for x in args):
            return _match_literal(value, args)

    if any(a is bool for a, _ in alts):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lo = value.strip().lower()
            if lo in _BOOL_TRUE:
                return True
            if lo in _BOOL_FALSE:
                return False
            if accepts_none and lo in _NULL_STRINGS:
                return None
        return value

    if any(a in (int, float) for a, _ in alts):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            lo = value.strip().lower()
            if accepts_none and lo in _NULL_STRINGS:
                return None
            m = _NUMERIC_TOKEN.search(value)
            if m:
                try:
                    num = float(m.group(0))
                except ValueError:
                    return value
                return num if any(a is float for a, _ in alts) else int(num)
        return value

    return value


def _coerce_to_schema(data: dict, schema: type[BaseModel]) -> dict:
    """Apply lenient coercions to common VLM-output mismatches before Pydantic validates."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    for name, field in schema.model_fields.items():
        if name in out:
            try:
                out[name] = _coerce_field(out[name], field.annotation)
            except Exception:
                pass
    return out


def _format_validation_errors(err: BaseException) -> str:
    cause = err
    if isinstance(err, ValueError) and isinstance(err.__cause__, ValidationError):
        cause = err.__cause__
    if isinstance(cause, ValidationError):
        lines = []
        for e in cause.errors():
            loc = ".".join(str(p) for p in e.get("loc", ())) or "(root)"
            msg = e.get("msg", "")
            inp = e.get("input")
            lines.append(f"  - {loc}: {msg} (got: {inp!r})")
        return "\n".join(lines) or f"  - {cause}"
    return f"  - {type(err).__name__}: {err}"


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
    """Vision-capable JSON call routed to K2-Think via ``KIMI_API_KEY``.

    This is the only call surface that handles ``image_url`` content blocks.
    Uses the same K2-Think endpoint as text calls - one model, one key.
    """
    findings, _raw = await call_with_vision_raw(
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=images,
        max_tokens=max_tokens,
    )
    return findings


async def call_with_vision_raw(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    images: list[Path | bytes] | None = None,
    max_tokens: int = 2000,
) -> tuple[T, str]:
    """Like ``call_with_vision`` but also returns the raw model response text.

    Used by UI layers that want to render the model's ``<think>`` reasoning
    alongside the parsed structured output.
    """
    return await _call_json_impl(
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=images,
        max_tokens=max_tokens,
        client=_openai_client(),
        model=_model_name(),
        return_raw=True,
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
    return_raw: bool = False,
):
    """Shared JSON-extracting call. Routed by caller to K2 or MediX.

    Returns ``T`` by default, or ``(T, raw_text)`` when ``return_raw=True`` so
    callers can surface the model's reasoning alongside the parsed object.
    """
    log = get_logger()
    raw_schema = schema.model_json_schema()
    # Build compact per-field hints so VL models don't pattern-match the JSON
    # Schema envelope and echo {description, properties: {...}} back at us.
    # Critically, we keep enum/literal values so the model knows the allowed
    # strings - dropping them made it return free-form answers like
    # "Nodular Melanoma" (which fail Pydantic literal_error validation).
    defs = raw_schema.get("$defs") or raw_schema.get("definitions") or {}

    def _hint_for(prop: dict) -> str:
        # Inline a $ref into the referenced schema definition
        if "$ref" in prop:
            ref_name = prop["$ref"].rsplit("/", 1)[-1]
            prop = defs.get(ref_name, prop)
        if "enum" in prop:
            return "one of " + " | ".join(repr(v) for v in prop["enum"])
        if "anyOf" in prop:
            return " OR ".join(_hint_for(sub) for sub in prop["anyOf"])
        t = prop.get("type", "any")
        return t

    props = raw_schema.get("properties", {})
    field_hints = {name: _hint_for(p) for name, p in props.items()}
    required = raw_schema.get("required", list(field_hints.keys()))
    hint_lines = "\n".join(f"  - {k}: {v}" for k, v in field_hints.items())
    augmented_system = (
        system_prompt.rstrip()
        + "\n\nRespond with a single JSON object whose keys are EXACTLY these fields "
        + "(do NOT wrap them under 'properties' or add a 'description' envelope):\n"
        + hint_lines
        + f"\n\nRequired: {', '.join(required)}."
        + "\nFor enum fields, use one of the literal strings shown above - do not "
        + "paraphrase (e.g. write 'nodular', not 'Nodular Melanoma')."
        + "\nReturn ONLY the JSON object after your reasoning. No markdown, no prose, no schema echo."
    )
    user_content = _user_content_with_images(user_prompt, images)
    log.info(
        "call schema=%s images=%d user_len=%d",
        schema.__name__, len(images or []), len(user_prompt),
    )
    audit(
        "llm_call", "start",
        schema=schema.__name__, model=model, max_tokens=max_tokens,
        user_len=len(user_prompt), has_images=bool(images and len(images) > 0),
        image_count=len(images or []),
        user_slice=user_prompt[:2000],
    )
    import time as _time
    async def _attempt(messages: list[dict]) -> tuple[T, str]:
        t0 = _time.time()
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except Exception as e:
            log.error("call HTTP error schema=%s model=%s err=%s: %s",
                      schema.__name__, model, type(e).__name__, e)
            audit(
                "llm_call", "http_error",
                schema=schema.__name__, model=model, max_tokens=max_tokens,
                error_type=type(e).__name__, error=str(e),
                latency_ms=int((_time.time() - t0) * 1000),
            )
            raise
        raw = resp.choices[0].message.content or ""
        finish_reason = getattr(resp.choices[0], "finish_reason", None)
        log.info("call response schema=%s len=%d", schema.__name__, len(raw))
        audit(
            "llm_call", "done",
            schema=schema.__name__, model=model,
            raw_len=len(raw), finish_reason=finish_reason,
            latency_ms=int((_time.time() - t0) * 1000),
            raw_response_slice=raw,
        )
        try:
            data = json.loads(_extract_json(raw))
        except json.JSONDecodeError as e:
            log.error("JSON parse failed schema=%s raw=%r", schema.__name__, raw[:600])
            audit(
                "llm_call", "parse_fail",
                schema=schema.__name__, raw_len=len(raw),
                error=str(e),
                raw_full=raw,
            )
            raise ValueError(f"model did not return valid JSON: {raw[:300]!r}") from e
        # Unwrap JSON-Schema envelope if the model echoed `{description, properties: {...}}`
        # instead of a flat instance (common failure mode on VL models).
        if isinstance(data, dict) and isinstance(data.get("properties"), dict):
            wanted = set(schema.model_json_schema().get("properties", {}).keys())
            inner_keys = set(data["properties"].keys())
            if inner_keys & wanted:
                log.info("unwrapped schema envelope schema=%s", schema.__name__)
                data = data["properties"]
        coerced = _coerce_to_schema(data, schema) if isinstance(data, dict) else data
        try:
            validated = schema.model_validate(coerced)
        except ValidationError as e:
            log.error("validation failed schema=%s err=%s data=%s", schema.__name__, e, coerced)
            audit(
                "llm_call", "validation_fail",
                schema=schema.__name__,
                error=str(e),
                coerced_slice=json.dumps(coerced, default=str)[:3000] if isinstance(coerced, (dict, list)) else str(coerced)[:3000],
            )
            raise
        return validated, raw

    messages: list[dict] = [
        {"role": "system", "content": augmented_system},
        {"role": "user", "content": user_content},
    ]
    try:
        validated, raw = await _attempt(messages)
    except (ValidationError, ValueError) as first_err:
        err_text = _format_validation_errors(first_err)
        log.warning(
            "retrying schema=%s after first-attempt failure:\n%s",
            schema.__name__, err_text,
        )
        messages.append({
            "role": "assistant",
            "content": "(previous response omitted - failed validation)",
        })
        messages.append({
            "role": "user",
            "content": (
                f"Your previous JSON failed validation:\n{err_text}\n\n"
                "Return a corrected JSON object using the literal values listed in the "
                "schema above. Output ONLY the JSON object - no <think> block, no "
                "markdown, no prose."
            ),
        })
        try:
            validated, raw = await _attempt(messages)
        except (ValidationError, ValueError) as second_err:
            log.error("retry failed schema=%s err=%s", schema.__name__, second_err)
            raise ValueError(
                f"model JSON failed {schema.__name__} validation after retry: {second_err}"
            ) from second_err
    if return_raw:
        return validated, raw
    return validated


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
    import time as _time
    t0 = _time.time()
    model_name = _model_name()
    audit(
        "llm_call", "stream_start",
        model=model_name, max_tokens=max_tokens,
        user_len=len(user_prompt), image_count=len(images or []),
        user_slice=user_prompt[:2000],
    )
    # Accumulate both buffers for the final audit line so we can see exactly
    # what the model produced even when no caller saved the chunks.
    think_accum: list[str] = []
    answer_accum: list[str] = []

    state: Literal["pre", "thinking", "answer"] = "pre"
    buffer = ""

    try:
        stream = await client.chat.completions.create(
            model=model_name,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as e:
        log.error("stream HTTP error: %s: %s", type(e).__name__, e)
        audit(
            "llm_call", "stream_error",
            model=model_name, error_type=type(e).__name__, error=str(e),
            latency_ms=int((_time.time() - t0) * 1000),
        )
        raise

    finish_reason: str | None = None
    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
            delta = choice.delta.content or ""
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
                                answer_accum.append(emit_text)
                                yield ("answer", emit_text)
                        break
                    pre_text = buffer[:idx]
                    buffer = buffer[idx + len(_THINK_OPEN):]
                    state = "thinking"
                    if pre_text:
                        answer_accum.append(pre_text)
                        yield ("answer", pre_text)
                    continue

                if state == "thinking":
                    idx = buffer.find(_THINK_CLOSE)
                    if idx == -1:
                        safe_len = max(0, len(buffer) - (len(_THINK_CLOSE) - 1))
                        if safe_len > 0:
                            emit_text, buffer = buffer[:safe_len], buffer[safe_len:]
                            think_accum.append(emit_text)
                            yield ("thinking", emit_text)
                        break
                    think_text = buffer[:idx]
                    buffer = buffer[idx + len(_THINK_CLOSE):]
                    state = "answer"
                    if think_text:
                        think_accum.append(think_text)
                        yield ("thinking", think_text)
                    continue

                if state == "answer":
                    if buffer:
                        emit_text, buffer = buffer, ""
                        answer_accum.append(emit_text)
                        yield ("answer", emit_text)
                    break

        if buffer:
            tail_kind = state if state != "pre" else "answer"
            (think_accum if tail_kind == "thinking" else answer_accum).append(buffer)
            yield (tail_kind, buffer)
    finally:
        think_full = "".join(think_accum)
        answer_full = "".join(answer_accum)
        audit(
            "llm_call", "stream_done",
            model=model_name, max_tokens=max_tokens,
            think_len=len(think_full), answer_len=len(answer_full),
            finish_reason=finish_reason,
            latency_ms=int((_time.time() - t0) * 1000),
            think_slice=think_full,
            answer_slice=answer_full,
        )
    log.info("stream_with_thinking done")
