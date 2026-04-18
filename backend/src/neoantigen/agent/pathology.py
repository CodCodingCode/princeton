"""PDF → PathologyReport extraction.

Uses pypdf for text extraction, then K2 Think V2 (prompted-JSON mode via
`_llm.call_for_json`) to fill a typed PathologyReport. K2-Think's tool calls
are unreliable so we prompt for JSON in the response text and post-process.
Falls back to heuristic regex parsing if K2_API_KEY is not set.
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from ..models import PathologyReport
from ._llm import call_for_json, get_k2_logger, has_api_key


SYSTEM_PROMPT = """You are a veterinary pathology report parser. Extract structured fields from the report text.

Reason step-by-step about what each field should be, then produce the final structured output.

If a field is not stated in the report, use null (or an empty list for array fields). Be precise and concise.
"""


def _extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(chunks)


def _heuristic_parse(text: str) -> dict:
    """Regex-based fallback parser for when no LLM is available.

    Handles both inline (`Name: Luna`) and table-style (`Name:\nLuna`) layouts.
    """

    def _after(label_pattern: str) -> str | None:
        """Match a label followed by a value on the same or next line."""
        m = re.search(
            rf"{label_pattern}[:\s]*\n?\s*([^\n]+)",
            text,
            re.IGNORECASE,
        )
        return m.group(1).strip() if m else None

    name_val = _after(r"Patient\s*Name") or _after(r"\bName\b")
    breed_val = _after(r"Breed")
    age_raw = _after(r"Age")
    weight_raw = _after(r"Weight")
    cancer_val = _after(r"Diagnosis") or _after(r"Cancer\s*type")
    grade_val = None
    if cancer_val:
        g = re.search(r"Grade\s+([IVX0-9]+)", cancer_val, re.IGNORECASE)
        if g:
            grade_val = g.group(1)
    if not grade_val:
        g2 = re.search(r"Grade\s+([IVX0-9]+)", text, re.IGNORECASE)
        grade_val = g2.group(1) if g2 else None
    owner_loc_val = _after(r"Owner\s*Location") or _after(r"City") or _after(r"Region")
    location_val = _after(r"Location") or _after(r"Site")
    dla_match = re.findall(r"DLA-[0-9]+\*[0-9]+", text)

    # Parse numeric values
    age_num = None
    if age_raw:
        m = re.search(r"(\d+(?:\.\d+)?)", age_raw)
        if m:
            age_num = float(m.group(1))
    weight_num = None
    if weight_raw:
        m = re.search(r"(\d+(?:\.\d+)?)", weight_raw)
        if m:
            weight_num = float(m.group(1))

    # Prior treatments: look for "Prior Treatments" section
    prior = []
    pt = re.search(r"Prior\s*Treatments[:\s]*\n?([^\n]+(?:\n[^\n]+)*)", text, re.IGNORECASE)
    if pt:
        prior = [s.strip() for s in re.split(r"[;,]|\n", pt.group(1)) if s.strip() and len(s.strip()) < 200][:5]

    return {
        "patient_name": name_val or "Unknown",
        "species": "canine",
        "breed": breed_val,
        "age_years": age_num,
        "weight_kg": weight_num,
        "sex": None,
        "cancer_type": cancer_val or "mast cell tumor",
        "grade": grade_val,
        "stage": None,
        "location": location_val or "unknown",
        "owner_location": owner_loc_val,
        "prior_treatments": prior,
        "clinical_notes": text[:800],
        "dla_alleles": list(set(dla_match)),
    }


async def _llm_parse(text: str) -> PathologyReport:
    """Call K2 Think V2 and parse the response into a typed PathologyReport."""
    return await call_for_json(
        schema=PathologyReport,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Parse this pathology report:\n\n{text}",
    )


async def extract_pathology(pdf_path: Path) -> PathologyReport:
    """Extract a PathologyReport from a PDF. Uses K2 Think V2 if available, falls back to regex."""
    text = _extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError(f"No extractable text in {pdf_path}")

    if has_api_key():
        try:
            return await _llm_parse(text)
        except Exception as e:
            get_k2_logger().warning(
                "extract_pathology fallback to heuristic: err=%s: %s",
                type(e).__name__, e,
            )

    return PathologyReport(**_heuristic_parse(text))
