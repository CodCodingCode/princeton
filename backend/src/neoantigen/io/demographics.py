"""Patient demographics extractor.

Runs AFTER per-document extraction (``io/pdf_extract``) and cross-doc
oncology aggregation (``io/aggregator``). Looks at the already-extracted
documents, finds whichever one is a demographics / registration sheet
(``document_kind == "demographics"`` or filename hint), and pulls a flat
``PatientDemographics`` record out of the document's text. Falls back to
regex when no LLM is available, and returns ``None`` when nothing
demographics-shaped was uploaded — the card on the frontend then degrades
to "Not documented" per field.
"""

from __future__ import annotations

import re

from ..agent._llm import call_for_json, has_api_key
from ..agent.audit import audit
from ..models import DocumentExtraction, PatientDemographics


# ─────────────────────────────────────────────────────────────
# LLM extraction
# ─────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """You are a medical records clerk reading one patient
registration / demographics / face sheet document. Extract a flat JSON of
the patient's identity and contact fields.

Every field is OPTIONAL — if the document does not state the field, leave
it null. Do NOT guess and do NOT fabricate. Rules:

  * full_name — legal name exactly as written. "Last, First Middle" and
    "First Middle Last" are both acceptable; keep the form shown.
  * sex — "Female", "Male", or whatever the form states (may be "F"/"M").
  * date_of_birth — ISO 8601 when possible ("1962-04-17"). If the form
    uses MM/DD/YYYY or similar, convert.
  * mrn — medical record number / chart number. Digits/letters, preserve
    any leading zeros.
  * race, ethnicity, preferred_language, marital_status — as stated.
  * phone — primary phone. Keep the form's punctuation.
  * email — primary email, lowercased.
  * address — mailing address as one comma-separated line.
  * insurance — payer + plan + member id, joined as one string (e.g.
    "Aetna PPO · member 12345"). Omit anything that isn't stated.
  * emergency_contact — "Name (relationship) · phone" when all three are
    available. Trim what's missing.
  * primary_care_provider — name of the PCP as stated on the form.

Output ONLY a single JSON object. No prose, no markdown, no <think>.
Start with `{` and end with `}`. Every field you can't find stays null.
"""


async def _llm_extract(text: str, filename: str) -> PatientDemographics | None:
    """Single LLM pass on the demographics doc's text."""
    excerpt = (text or "")[:8000]
    if not excerpt.strip():
        return None
    try:
        result = await call_for_json(
            schema=PatientDemographics,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=(
                f"Source file: {filename}\n\n"
                f"Document text:\n{excerpt}\n\n"
                "Emit the PatientDemographics JSON now."
            ),
            max_tokens=1200,
        )
    except Exception as e:
        audit("demographics", "llm_fail", error=str(e)[:300], filename=filename)
        return None
    result.source_filename = filename
    return result


# ─────────────────────────────────────────────────────────────
# Regex fallback (used when no LLM is available)
# ─────────────────────────────────────────────────────────────


# Registration forms commonly place labels and values on SEPARATE lines:
#
#     DOB:
#     03/15/1975
#
# `\s*` already matches newlines so `label\s*:\s*(...)` works even when the
# value sits on the next line — but the value regex must NOT include `\n` in
# its character class or the first newline is the terminator.
_VALUE = r"([^\n\r]{2,120})"
_RE_FLAGS = re.IGNORECASE

# Each entry: (field_name, regex). First capture group wins.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("date_of_birth", re.compile(
        r"(?:date\s*of\s*birth|dob|birth\s*date)\s*[:#\-]\s*([0-9./\-]{6,20})",
        _RE_FLAGS,
    )),
    ("sex", re.compile(
        r"(?:legal\s*sex|sex|gender)\s*[:#\-]\s*(male|female|m|f|other|non[- ]binary)\b",
        _RE_FLAGS,
    )),
    ("mrn", re.compile(
        r"(?:mrn|medical\s*record\s*(?:number|#)|chart\s*#?|patient\s*id)\s*[:#\-]?\s*([A-Za-z0-9\-]{4,20})",
        _RE_FLAGS,
    )),
    ("race", re.compile(r"race\s*[:#\-]\s*" + _VALUE, _RE_FLAGS)),
    ("ethnicity", re.compile(r"ethnicit(?:y|ies)\s*[:#\-]\s*" + _VALUE, _RE_FLAGS)),
    ("preferred_language", re.compile(
        # "Preferred Lang", "Preferred Language", "Language" all map here.
        r"(?:preferred\s*lang(?:uage)?|language)\s*[:#\-]\s*([^\n\r]{2,40})",
        _RE_FLAGS,
    )),
    ("marital_status", re.compile(r"marital\s*status\s*[:#\-]\s*([^\n\r]{2,30})", _RE_FLAGS)),
    ("phone", re.compile(
        # Prefer "Home Phone" / "Mobile" / "Cell" / plain "Phone"; any works.
        r"(?:home\s*phone|mobile|cell|tel|phone)\s*[:#\-]?\s*(\+?[\d().\- ]{7,25})",
        _RE_FLAGS,
    )),
    ("email", re.compile(
        r"(?:email|e-mail)\s*[:#\-]\s*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
        _RE_FLAGS,
    )),
    ("primary_care_provider", re.compile(
        r"(?:primary\s*care\s*(?:provider|physician)|pcp)\s*[:#\-]\s*([^\n\r]{3,80})",
        _RE_FLAGS,
    )),
    ("emergency_contact", re.compile(
        r"emergency\s*contact\s*[:#\-]\s*([^\n\r]{3,120})",
        _RE_FLAGS,
    )),
]

# Name + address are composite — multiple labels concatenate into one value.
_RE_LAST = re.compile(r"last\s*name\s*[:#\-]\s*([^\n\r]{1,60})", _RE_FLAGS)
_RE_FIRST = re.compile(r"first\s*name\s*[:#\-]\s*([^\n\r]{1,60})", _RE_FLAGS)
_RE_MIDDLE = re.compile(r"middle(?:\s*name)?\s*[:#\-]\s*([^\n\r]{1,60})", _RE_FLAGS)
_RE_FULL = re.compile(
    r"(?:patient\s*name|legal\s*name|^name)\s*[:#\-]\s*([^\n\r]{3,80})",
    _RE_FLAGS | re.MULTILINE,
)

_RE_ADDRESS_STREET = re.compile(
    r"(?:address|home\s*address|street\s*address)\s*[:#\-]\s*([^\n\r]{5,120})",
    _RE_FLAGS,
)
_RE_CITY_LINE = re.compile(
    # \b before city/ so we don't match the tail of "Ethnicity:".
    r"\b(?:city\s*/?\s*state\s*/?\s*zip|city)\s*[:#\-]\s*([^\n\r]{3,120})",
    _RE_FLAGS,
)

# "Primary: <payer>\nMember ID: <id>" — typical for two-tier insurance blocks.
_RE_PAYER = re.compile(
    r"(?:insurance|primary\s*insurance|payer|plan|primary)\s*[:#\-]\s*([^\n\r]{3,80})",
    _RE_FLAGS,
)
_RE_MEMBER = re.compile(
    r"member\s*(?:id|#|number)\s*[:#\-]\s*([A-Za-z0-9\-]{3,40})",
    _RE_FLAGS,
)


def _grab(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    v = m.group(1).strip().rstrip(",.;:")
    return v or None


def _compose_full_name(text: str) -> str | None:
    """Prefer a single-line ``Name: ...`` when present, otherwise compose from
    Last / First / Middle tokens."""
    single = _grab(_RE_FULL, text)
    if single:
        return single
    last = _grab(_RE_LAST, text)
    first = _grab(_RE_FIRST, text)
    middle = _grab(_RE_MIDDLE, text)
    parts = [p for p in (first, middle, last) if p]
    return " ".join(parts) if parts else None


def _compose_address(text: str) -> str | None:
    street = _grab(_RE_ADDRESS_STREET, text)
    city = _grab(_RE_CITY_LINE, text)
    if street and city:
        return f"{street}, {city}"
    return street or city


def _compose_insurance(text: str) -> str | None:
    payer = _grab(_RE_PAYER, text)
    member = _grab(_RE_MEMBER, text)
    if payer and member:
        return f"{payer} · member {member}"
    return payer or (f"member {member}" if member else None)


def _regex_extract(text: str, filename: str) -> PatientDemographics | None:
    if not text.strip():
        return None
    out = PatientDemographics(source_filename=filename)
    found_any = False

    for field, pattern in _PATTERNS:
        value = _grab(pattern, text)
        if value is None:
            continue
        if field == "sex":
            lower = value.lower()
            if lower in {"m", "male"}:
                value = "Male"
            elif lower in {"f", "female"}:
                value = "Female"
        setattr(out, field, value)
        found_any = True

    composed = {
        "full_name": _compose_full_name(text),
        "address": _compose_address(text),
        "insurance": _compose_insurance(text),
    }
    for field, value in composed.items():
        if value:
            setattr(out, field, value)
            found_any = True

    return out if found_any else None


def _merge(
    primary: PatientDemographics | None,
    fallback: PatientDemographics | None,
) -> PatientDemographics | None:
    """Merge two demographics records field-by-field, preferring ``primary``
    when it has a non-null value, otherwise filling from ``fallback``."""
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    merged = primary.model_copy()
    for field in PatientDemographics.model_fields:
        pv = getattr(merged, field)
        if pv in (None, ""):
            fv = getattr(fallback, field)
            if fv not in (None, ""):
                setattr(merged, field, fv)
    return merged


# ─────────────────────────────────────────────────────────────
# Doc selection
# ─────────────────────────────────────────────────────────────


def _is_demographics_doc(doc: DocumentExtraction) -> bool:
    if doc.document_kind == "demographics":
        return True
    name = doc.filename.lower()
    return "demograph" in name or "registration" in name or "face sheet" in name


def _pick_demographics_doc(
    docs: list[DocumentExtraction],
) -> DocumentExtraction | None:
    candidates = [d for d in docs if _is_demographics_doc(d)]
    if not candidates:
        return None
    # Prefer longer text excerpts — more likely to contain a real form.
    candidates.sort(key=lambda d: len(d.text_excerpt or ""), reverse=True)
    return candidates[0]


# ─────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────


async def extract_demographics(
    docs: list[DocumentExtraction],
) -> PatientDemographics | None:
    """Return a filled ``PatientDemographics`` when one of the uploaded docs
    is a demographics/registration sheet, otherwise ``None``.

    Runs the regex extractor unconditionally and the LLM extractor when a
    key is configured, then merges the two field-by-field. The LLM is
    authoritative when both produce a value, but a field the LLM leaves
    null is backfilled from regex — so an "all nulls" LLM response no
    longer hides the labeled data a registration form clearly shows.
    """
    doc = _pick_demographics_doc(docs)
    if doc is None:
        return None

    text = doc.text_excerpt or "\n".join(
        (p.description or "") + " " + (p.notes or "") for p in doc.pages
    )

    regex_result = _regex_extract(text, doc.filename)
    llm_result: PatientDemographics | None = None
    if has_api_key():
        llm_result = await _llm_extract(text, doc.filename)

    merged = _merge(llm_result, regex_result)
    if merged is not None:
        audit(
            "demographics", "done",
            filename=doc.filename,
            llm=_count_filled(llm_result) if llm_result else 0,
            regex=_count_filled(regex_result) if regex_result else 0,
            merged=_count_filled(merged),
        )
    else:
        audit("demographics", "empty", filename=doc.filename)
    return merged


def _count_filled(d: PatientDemographics) -> int:
    return sum(
        1
        for v in d.model_dump().values()
        if v is not None and str(v).strip() != ""
    )


__all__ = ["extract_demographics"]
