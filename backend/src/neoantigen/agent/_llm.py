"""Shared K2 Think V2 client + model factory.

K2 Think V2 is a reasoning model — it emits `<think>...</think>` blocks in its
response and does NOT reliably produce OpenAI-style tool calls (MBZUAI's own
docs: "not yet tuned for agentic tasks"). We therefore use two client surfaces:

* `build_model()` returns a PydanticAI `OpenAIModel` for free-form `str` outputs
  (used by `explain.py`). PydanticAI's tool-call path for structured outputs is
  unreliable with K2-Think.
* `call_for_json(prompt, schema)` calls K2 via the plain openai SDK, strips the
  `<think>` block, extracts the first JSON object, and validates it against a
  Pydantic model. Used by `pathology.py` + `emails.py`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError


K2_BASE_URL = os.environ.get("K2_BASE_URL", "https://api.k2think.ai/v1")
DEFAULT_MODEL = os.environ.get("NEOVAX_MODEL_DEFAULT", "MBZUAI-IFM/K2-Think-v2")

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def get_k2_logger() -> logging.Logger:
    """File-only logger that records every K2 call + outcome to out/k2.log.

    Does NOT propagate to root, so terminal stays clean. Path is overridable
    via `NEOVAX_LOG_PATH`; default is `out/k2.log` relative to the CWD.
    """
    logger = logging.getLogger("neoantigen.k2")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers:
        return logger  # already configured

    log_path = Path(os.environ.get("NEOVAX_LOG_PATH", "out/k2.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.info("K2 logger initialized (path=%s)", log_path)
    return logger


def has_api_key() -> bool:
    return bool(os.environ.get("K2_API_KEY"))


def _model_name() -> str:
    return os.environ.get("NEOVAX_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=1)
def build_model():
    """Build a PydanticAI OpenAIModel pointing at K2 Think V2."""
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise RuntimeError("K2_API_KEY not set")
    return OpenAIModel(
        _model_name(),
        provider=OpenAIProvider(base_url=K2_BASE_URL, api_key=api_key),
    )


@lru_cache(maxsize=1)
def _openai_client():
    """Lazy-built raw AsyncOpenAI client pointed at K2 Think V2."""
    from openai import AsyncOpenAI

    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise RuntimeError("K2_API_KEY not set")
    return AsyncOpenAI(base_url=K2_BASE_URL, api_key=api_key)


def strip_think(text: str) -> str:
    """Strip K2-Think reasoning.

    K2's output pattern: `...reasoning prose...</think>\\n{actual output}`. The
    reasoning often echoes JSON-schema fragments, so a greedy `{...}` regex
    over the full text matches the wrong block. Splitting on the LAST `</think>`
    isolates the payload. If no think marker is present, returns the stripped
    input unchanged.
    """
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def _extract_json(text: str) -> str:
    """Extract a single top-level JSON object from K2's response.

    Strategy: strip <think> reasoning, strip markdown fences, try direct parse;
    fall back to balanced-brace scanning for the first valid top-level `{...}`.
    """
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
    raise json.JSONDecodeError("no valid JSON object found in K2 response", cleaned, 0)


async def call_for_json(
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 2000,
) -> T:
    """Call K2 Think V2 asking for JSON matching `schema`, parse, and validate.

    Works around K2's unreliable tool-calling by prompting for JSON in the text
    response and post-processing out the <think>...</think> block.
    """
    client = _openai_client()
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    augmented_system = (
        system_prompt.rstrip()
        + "\n\nYou MUST respond with a single JSON object matching this schema:\n"
        + schema_json
        + "\n\nReturn ONLY the JSON object after your reasoning. No markdown, no prose."
    )
    resp = await client.chat.completions.create(
        model=_model_name(),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"K2 did not return valid JSON: {raw[:300]!r}") from e
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"K2 JSON failed {schema.__name__} validation: {e}") from e
