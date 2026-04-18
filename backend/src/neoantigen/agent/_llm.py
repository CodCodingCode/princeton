"""Shared K2 Think V2 model factory.

All PydanticAI agents in the project (pathology, emails, explain) share a single
model instance pointed at MBZUAI's K2 Think V2 API (OpenAI-compatible).
"""

from __future__ import annotations

import os
from functools import lru_cache


K2_BASE_URL = "https://api.k2think.ai/v1"
DEFAULT_MODEL = "MBZUAI-IFM/K2-Think-v2"


def has_api_key() -> bool:
    return bool(os.environ.get("K2_API_KEY"))


@lru_cache(maxsize=1)
def build_model():
    """Build a PydanticAI OpenAIModel pointing at K2 Think V2.

    Raises RuntimeError if K2_API_KEY is not set. Callers should check
    `has_api_key()` first and fall back to heuristic paths when absent.
    """
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    api_key = os.environ.get("K2_API_KEY")
    if not api_key:
        raise RuntimeError("K2_API_KEY not set")

    model_name = os.environ.get("NEOVAX_MODEL", DEFAULT_MODEL)
    return OpenAIModel(
        model_name,
        provider=OpenAIProvider(base_url=K2_BASE_URL, api_key=api_key),
    )
