"""Vision-language analysis of an H&E pathology slide image.

Replaces the older PDF-text-only `pathology.py`. The MediX-R1-30B model is
Qwen3-VL-based, so we feed the slide image as a base64 data URI in an
`image_url` content block and ask for a typed `PathologyFindings` JSON object.

Falls back to a low-confidence placeholder if no API key is configured.
"""

from __future__ import annotations

from pathlib import Path

from ..models import PathologyFindings
from ._llm import call_with_vision, has_medix_key
from .events import EventKind, emit


SYSTEM_PROMPT = (
    "You are a dermatopathologist examining an H&E-stained skin biopsy slide. "
    "Identify melanoma if present and report the standard descriptors a "
    "pathology report would include: melanoma subtype, Breslow thickness in "
    "millimetres (estimate from morphology), ulceration, mitotic rate per mm², "
    "tumour-infiltrating lymphocytes, and an approximate PD-L1 estimate if "
    "discernible. Be honest about uncertainty — set the `confidence` field "
    "between 0 and 1 to reflect how clearly the slide supports each call."
)

USER_PROMPT = (
    "Examine the attached histopathology image and produce the structured "
    "findings JSON. Use the `notes` field to mention anything notable that "
    "doesn't fit the schema (regression, perineural invasion, satellitosis, "
    "etc.)."
)


async def analyze_slide(image_path: Path) -> PathologyFindings:
    await emit(
        EventKind.TOOL_START,
        f"🔬 VLM reading pathology slide ({image_path.name})",
        {"path": str(image_path)},
    )

    if not has_medix_key() or not image_path.exists():
        findings = _placeholder()
        await emit(
            EventKind.VLM_FINDING,
            "🔬 VLM unavailable (MEDIX_API_KEY unset or slide missing) — placeholder findings",
            {"findings": findings.model_dump()},
        )
        return findings

    try:
        findings = await call_with_vision(
            schema=PathologyFindings,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
            images=[image_path],
            max_tokens=2500,
        )
    except Exception as e:
        await emit(EventKind.LOG, f"VLM call failed ({type(e).__name__}: {e}); using placeholder")
        findings = _placeholder()

    await emit(
        EventKind.VLM_FINDING,
        f"🔬 {findings.melanoma_subtype} · Breslow {findings.breslow_thickness_mm}mm · "
        f"{'ulcerated' if findings.ulceration else 'no ulceration'} · stage {findings.t_stage}",
        {"findings": findings.model_dump()},
    )
    return findings


def _placeholder() -> PathologyFindings:
    """Reasonable mid-risk demo case so downstream NCCN walker has something to chew on."""
    return PathologyFindings(
        melanoma_subtype="superficial_spreading",
        breslow_thickness_mm=2.4,
        ulceration=True,
        mitotic_rate_per_mm2=4.0,
        tils_present="non_brisk",
        pdl1_estimate="low",
        confidence=0.3,
        notes="Placeholder: no slide image or VLM available. Defaults chosen to drive a Stage IIIish demo path.",
    )
