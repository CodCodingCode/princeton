"""Pathology PDF → structured oncology fields.

Two-stage pipeline:
  1. ``extract_text(pdf_bytes)`` — pull text with ``pypdf``.
  2. ``extract_oncology_fields(text)`` — LLM-structured extraction via
     ``agent._llm.call_for_json`` into ``PathologyFindings`` + ``ClinicianIntake``
     + ``list[Mutation]``.

Scanned-PDF fallback: if pypdf returns < MIN_TEXT_CHARS, optionally rasterize
pages via ``pdf2image`` and pass to the vision model. Falls back to a blank
case if neither works — downstream modules then show `needs_more_data`.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from ..agent._llm import call_for_json, call_with_vision, has_api_key
from ..models import ClinicianIntake, MelanomaSubtype, Mutation, PathologyFindings


MIN_TEXT_CHARS = 200


@dataclass
class PDFExtraction:
    """What the PDF extractor hands back to the orchestrator."""

    pathology: PathologyFindings
    intake: ClinicianIntake
    mutations: list[Mutation]
    raw_text: str
    used_vision_fallback: bool = False


class _ExtractedMutation(BaseModel):
    gene: str
    ref_aa: str = Field(description="Single-letter wild-type amino acid, e.g. 'V'")
    position: int
    alt_aa: str = Field(description="Single-letter mutant amino acid, e.g. 'E'")


class _ExtractionPayload(BaseModel):
    """LLM output schema — flat and forgiving."""

    melanoma_subtype: MelanomaSubtype = "unknown"
    breslow_thickness_mm: float | None = None
    ulceration: bool | None = None
    mitotic_rate_per_mm2: float | None = None
    tils_present: str | None = None
    pdl1_estimate: str | None = None
    lag3_ihc_percent: float | None = None
    pathology_notes: str = ""

    ajcc_stage: str | None = None
    age_years: int | None = None
    ecog: int | None = None
    measurable_disease_recist: bool | None = None
    life_expectancy_months: int | None = None
    prior_systemic_therapy: bool | None = None
    prior_anti_pd1: bool | None = None

    mutations: list[_ExtractedMutation] = Field(default_factory=list)


SYSTEM_PROMPT = """You are an oncology data extractor. Read the pathology / clinical
PDF text and return a single JSON object with the fields below. Rules:

* Leave a field as null / None if the document does not state it — do NOT guess.
* For pathology fields, only populate if the PDF explicitly reports the value.
* For mutations, include only point mutations with gene name, wild-type amino
  acid, position, and mutant amino acid (e.g. BRAF V600E → gene="BRAF", ref_aa="V",
  position=600, alt_aa="E"). Skip fusions, indels, and copy-number events.
* tils_present must be one of: absent, non_brisk, brisk, unknown.
* pdl1_estimate must be one of: negative, low, high, unknown.
* ajcc_stage should be a string like "IIB", "IIIC", "IV".
* ecog is an integer 0-4.
* Output ONLY the JSON object — no prose, no <think> block, no markdown fences.
"""


def extract_text(pdf_bytes: bytes) -> str:
    """Pull concatenated text from a PDF byte stream via pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n\n".join(p.strip() for p in parts if p and p.strip())
    except Exception:
        return ""


def _rasterize_pdf(pdf_bytes: bytes, max_pages: int = 4) -> list[bytes]:
    """Convert up to ``max_pages`` PDF pages to JPEG byte-strings via pdf2image."""
    try:
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=max_pages)
    except Exception:
        return []
    out: list[bytes] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        out.append(buf.getvalue())
    return out


def _coerce_tils(v: str | None) -> str:
    if not v:
        return "unknown"
    v = v.lower().strip()
    if v in {"absent", "non_brisk", "brisk", "unknown"}:
        return v
    return "unknown"


def _coerce_pdl1(v: str | None) -> str:
    if not v:
        return "unknown"
    v = v.lower().strip()
    if v in {"negative", "low", "high", "unknown"}:
        return v
    return "unknown"


def _payload_to_models(payload: _ExtractionPayload) -> tuple[PathologyFindings, ClinicianIntake, list[Mutation]]:
    pathology = PathologyFindings(
        melanoma_subtype=payload.melanoma_subtype,
        breslow_thickness_mm=payload.breslow_thickness_mm,
        ulceration=payload.ulceration,
        mitotic_rate_per_mm2=payload.mitotic_rate_per_mm2,
        tils_present=_coerce_tils(payload.tils_present),  # type: ignore[arg-type]
        pdl1_estimate=_coerce_pdl1(payload.pdl1_estimate),  # type: ignore[arg-type]
        lag3_ihc_percent=payload.lag3_ihc_percent,
        notes=payload.pathology_notes,
        confidence=0.7,
    )
    intake = ClinicianIntake(
        ajcc_stage=payload.ajcc_stage,
        age_years=payload.age_years,
        ecog=payload.ecog,
        lag3_ihc_percent=payload.lag3_ihc_percent,
        measurable_disease_recist=payload.measurable_disease_recist,
        life_expectancy_months=payload.life_expectancy_months,
        prior_systemic_therapy=payload.prior_systemic_therapy,
        prior_anti_pd1=payload.prior_anti_pd1,
    )
    mutations = [
        Mutation(
            gene=m.gene.upper(),
            ref_aa=m.ref_aa.upper(),
            position=int(m.position),
            alt_aa=m.alt_aa.upper(),
        )
        for m in payload.mutations
        if m.gene and m.ref_aa and m.alt_aa
    ]
    return pathology, intake, mutations


_MUT_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s+([A-Z])(\d{1,4})([A-Z])\b")


def _regex_mutations(text: str) -> list[Mutation]:
    """Last-ditch heuristic for obvious point mutations when LLM is unavailable."""
    seen: set[tuple[str, str, int, str]] = set()
    out: list[Mutation] = []
    for m in _MUT_RE.finditer(text):
        gene, ref, pos, alt = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        key = (gene, ref, pos, alt)
        if key in seen:
            continue
        seen.add(key)
        out.append(Mutation(gene=gene, ref_aa=ref, position=pos, alt_aa=alt))
    return out


async def extract_oncology_fields(pdf_bytes: bytes) -> PDFExtraction:
    """End-to-end: PDF bytes → structured findings + intake + mutations."""
    text = extract_text(pdf_bytes)
    used_vision = False

    # Vision fallback for scanned PDFs (requires MediX tunnel)
    if len(text) < MIN_TEXT_CHARS:
        pages = _rasterize_pdf(pdf_bytes)
        if pages:
            used_vision = True
            try:
                payload = await call_with_vision(
                    schema=_ExtractionPayload,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt="Extract oncology fields from the attached pathology pages.",
                    images=pages,
                )
                pathology, intake, mutations = _payload_to_models(payload)
                return PDFExtraction(
                    pathology=pathology,
                    intake=intake,
                    mutations=mutations,
                    raw_text="",
                    used_vision_fallback=True,
                )
            except Exception:
                pass

    if not text:
        return PDFExtraction(
            pathology=PathologyFindings(confidence=0.0, notes="PDF contained no extractable text."),
            intake=ClinicianIntake(),
            mutations=[],
            raw_text="",
            used_vision_fallback=used_vision,
        )

    if not has_api_key():
        # LLM unavailable — fall back to regex-only mutation extraction and an empty pathology read.
        return PDFExtraction(
            pathology=PathologyFindings(
                confidence=0.1,
                notes="LLM extraction disabled (K2_API_KEY unset); regex-only mutation scan.",
            ),
            intake=ClinicianIntake(),
            mutations=_regex_mutations(text),
            raw_text=text,
            used_vision_fallback=False,
        )

    try:
        payload = await call_for_json(
            schema=_ExtractionPayload,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=(
                "PDF TEXT:\n----------\n"
                f"{text[:24000]}\n"
                "----------\n"
                "Return the JSON now."
            ),
        )
    except Exception as e:
        return PDFExtraction(
            pathology=PathologyFindings(
                confidence=0.1,
                notes=f"LLM extraction failed: {type(e).__name__}: {e}",
            ),
            intake=ClinicianIntake(),
            mutations=_regex_mutations(text),
            raw_text=text,
            used_vision_fallback=False,
        )

    pathology, intake, mutations = _payload_to_models(payload)
    if not mutations:
        mutations = _regex_mutations(text)
    return PDFExtraction(
        pathology=pathology,
        intake=intake,
        mutations=mutations,
        raw_text=text,
        used_vision_fallback=False,
    )


def to_dict(extraction: PDFExtraction) -> dict:
    return {
        "pathology": extraction.pathology.model_dump(),
        "intake": extraction.intake.model_dump(),
        "mutations": [m.model_dump() for m in extraction.mutations],
        "used_vision_fallback": extraction.used_vision_fallback,
        "text_len": len(extraction.raw_text),
    }


__all__ = [
    "PDFExtraction",
    "extract_text",
    "extract_oncology_fields",
    "to_dict",
]


def _extract_mutations_for_tests(text: str) -> list[Mutation]:
    return _regex_mutations(text)


_ = json  # silence unused import checker when regex-only path is used
