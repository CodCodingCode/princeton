"""Kimi K2 cross-document aggregator.

Per-PDF extraction produces a ``DocumentExtraction`` with per-page vision
findings. When a case has multiple PDFs, those N document extractions almost
always contain overlapping and sometimes contradictory fields
(pathology report says Breslow 2.1 mm, a separate addendum says 2.3 mm, etc.).
This module hands every per-doc finding to Kimi K2 and asks it to:

  1. Reconcile conflicts — pick the most authoritative value and list the
     others under ``conflicts``.
  2. Deduplicate mutations across reports.
  3. Emit a single canonical ``PathologyFindings`` + ``ClinicianIntake`` +
     ``list[Mutation]`` plus per-field ``provenance`` pointing to the source
     document and page.

Falls back cleanly when Kimi is unavailable — merges by first-non-null with a
placeholder provenance.
"""

from __future__ import annotations

import asyncio
import re

from pydantic import BaseModel, Field

from ..agent._llm import call_for_json, has_api_key
from ..agent.events import EventKind, emit
from ..models import (
    ClinicianIntake,
    DocumentExtraction,
    MelanomaSubtype,
    Mutation,
    PathologyFindings,
    ProvenanceEntry,
)


# ─────────────────────────────────────────────────────────────
# Kimi K2 aggregator schema — the canonical patient record
# ─────────────────────────────────────────────────────────────


class _AggMutation(BaseModel):
    gene: str
    ref_aa: str
    position: int
    alt_aa: str
    source_filename: str = ""
    source_page: int | None = None


class _AggField(BaseModel):
    value: str | None = None
    source_filename: str = ""
    source_page: int | None = None


class _AggPayload(BaseModel):
    """Schema Kimi K2 fills in when reconciling across PDFs."""

    melanoma_subtype: _AggField = Field(default_factory=_AggField)
    breslow_thickness_mm: _AggField = Field(default_factory=_AggField)
    ulceration: _AggField = Field(default_factory=_AggField)
    mitotic_rate_per_mm2: _AggField = Field(default_factory=_AggField)
    tils_present: _AggField = Field(default_factory=_AggField)
    pdl1_estimate: _AggField = Field(default_factory=_AggField)
    lag3_ihc_percent: _AggField = Field(default_factory=_AggField)

    ajcc_stage: _AggField = Field(default_factory=_AggField)
    age_years: _AggField = Field(default_factory=_AggField)
    ecog: _AggField = Field(default_factory=_AggField)
    measurable_disease_recist: _AggField = Field(default_factory=_AggField)
    life_expectancy_months: _AggField = Field(default_factory=_AggField)
    prior_systemic_therapy: _AggField = Field(default_factory=_AggField)
    prior_anti_pd1: _AggField = Field(default_factory=_AggField)

    mutations: list[_AggMutation] = Field(default_factory=list)

    overall_notes: str = ""
    conflicts: list[str] = Field(
        default_factory=list,
        description="One-line descriptions of any field where two sources disagreed",
    )


SYSTEM_PROMPT = """You are a melanoma-oncology chart reconciler. You will be
given the per-page findings extracted from a patient's full document folder
(pathology reports, IHC addenda, NGS reports, imaging reports, H&P notes).
Multiple pages and multiple PDFs often mention the same field with slightly
different values.

Field priority — NCCN-critical fields. These drive the NCCN cutaneous
melanoma railway, so getting them right matters more than the trial-eligibility
fields:

  melanoma_subtype, breslow_thickness_mm, ulceration, mitotic_rate_per_mm2,
  tils_present, pdl1_estimate, lag3_ihc_percent

For NCCN-critical fields, always prefer the primary pathology report or IHC
addendum over a clinical-note summary, even when the note is more recent. A
consult note saying "Breslow ~2 mm" must lose to the pathology report saying
"Breslow 2.1 mm". An IHC addendum must win over a consult note that says
"PD-L1 pending".

Secondary fields (trial-eligibility — prefer the most recent clinical note,
since these change over time): ajcc_stage, age_years, ecog,
measurable_disease_recist, life_expectancy_months, prior_systemic_therapy,
prior_anti_pd1.

Your job:
  * Pick ONE authoritative value per field following the priority above.
  * For every field you emit, record the source filename and page_number.
  * Deduplicate mutations — if BRAF V600E appears on pages 2 and 7 of the
    NGS report and again in a summary, emit it once with the most specific
    source (prefer the NGS report over a summary).
  * When two sources truly contradict, pick the most authoritative per the
    priority above, emit that value, and add a one-line entry to `conflicts`
    describing the disagreement (e.g. "Breslow: path report 2.1 mm vs consult
    note 'approx 2 mm' — used path report").
  * Leave a field's value null if NONE of the pages mentioned it. Do not guess.
  * Enum fields:
      - melanoma_subtype ∈ {superficial_spreading, nodular, lentigo_maligna,
        acral_lentiginous, desmoplastic, other, unknown}
      - tils_present ∈ {absent, non_brisk, brisk, unknown}
      - pdl1_estimate ∈ {negative, low, high, unknown}
  * Numeric fields: return as strings so you can include units ("2.1", "2.1 mm"
    are both fine — we parse them). For booleans, return "true" or "false".
  * Output ONLY the JSON object. No prose. No markdown.
"""


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_float(s: str | None) -> float | None:
    if not s:
        return None
    m = _NUM_RE.search(str(s))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_int(s: str | None) -> int | None:
    f = _parse_float(s)
    if f is None:
        return None
    return int(f)


def _parse_bool(s: str | None) -> bool | None:
    if s is None:
        return None
    lo = str(s).strip().lower()
    if lo in {"true", "yes", "present", "positive", "ulcerated", "y", "1"}:
        return True
    if lo in {"false", "no", "absent", "negative", "none", "n", "0"}:
        return False
    return None


def _coerce_enum(s: str | None, allowed: tuple[str, ...], default: str) -> str:
    if not s:
        return default
    lo = str(s).strip().lower().replace(" ", "_").replace("-", "_")
    if lo in allowed:
        return lo
    for a in allowed:
        if a in lo or lo in a:
            return a
    return default


def _prov(field: str, v: _AggField) -> ProvenanceEntry | None:
    if v.value is None or str(v.value).strip() == "":
        return None
    return ProvenanceEntry(
        field=field,
        value=str(v.value),
        filename=v.source_filename or "unknown",
        page_number=v.source_page,
    )


def _payload_to_models(
    payload: _AggPayload,
) -> tuple[PathologyFindings, ClinicianIntake, list[Mutation], list[ProvenanceEntry]]:
    provenance: list[ProvenanceEntry] = []

    for name in [
        "melanoma_subtype", "breslow_thickness_mm", "ulceration", "mitotic_rate_per_mm2",
        "tils_present", "pdl1_estimate", "lag3_ihc_percent",
        "ajcc_stage", "age_years", "ecog", "measurable_disease_recist",
        "life_expectancy_months", "prior_systemic_therapy", "prior_anti_pd1",
    ]:
        p = _prov(name, getattr(payload, name))
        if p is not None:
            provenance.append(p)

    subtype: MelanomaSubtype = _coerce_enum(
        payload.melanoma_subtype.value,
        ("superficial_spreading", "nodular", "lentigo_maligna", "acral_lentiginous",
         "desmoplastic", "other", "unknown"),
        "unknown",
    )  # type: ignore[assignment]
    tils = _coerce_enum(
        payload.tils_present.value,
        ("absent", "non_brisk", "brisk", "unknown"),
        "unknown",
    )
    pdl1 = _coerce_enum(
        payload.pdl1_estimate.value,
        ("negative", "low", "high", "unknown"),
        "unknown",
    )

    pathology = PathologyFindings(
        melanoma_subtype=subtype,
        breslow_thickness_mm=_parse_float(payload.breslow_thickness_mm.value),
        ulceration=_parse_bool(payload.ulceration.value),
        mitotic_rate_per_mm2=_parse_float(payload.mitotic_rate_per_mm2.value),
        tils_present=tils,  # type: ignore[arg-type]
        pdl1_estimate=pdl1,  # type: ignore[arg-type]
        lag3_ihc_percent=_parse_float(payload.lag3_ihc_percent.value),
        notes=payload.overall_notes,
        confidence=0.8,
    )

    intake = ClinicianIntake(
        ajcc_stage=payload.ajcc_stage.value or None,
        age_years=_parse_int(payload.age_years.value),
        ecog=_parse_int(payload.ecog.value),
        lag3_ihc_percent=_parse_float(payload.lag3_ihc_percent.value),
        measurable_disease_recist=_parse_bool(payload.measurable_disease_recist.value),
        life_expectancy_months=_parse_int(payload.life_expectancy_months.value),
        prior_systemic_therapy=_parse_bool(payload.prior_systemic_therapy.value),
        prior_anti_pd1=_parse_bool(payload.prior_anti_pd1.value),
    )

    mutations: list[Mutation] = []
    seen: set[tuple[str, str, int, str]] = set()
    for m in payload.mutations:
        try:
            key = (m.gene.upper(), m.ref_aa.upper(), int(m.position), m.alt_aa.upper())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        mutations.append(Mutation(
            gene=key[0], ref_aa=key[1], position=key[2], alt_aa=key[3],
        ))
        if m.source_filename:
            provenance.append(ProvenanceEntry(
                field=f"mutation:{key[0]} {key[1]}{key[2]}{key[3]}",
                value=f"{key[0]} {key[1]}{key[2]}{key[3]}",
                filename=m.source_filename,
                page_number=m.source_page,
            ))

    return pathology, intake, mutations, provenance


# ─────────────────────────────────────────────────────────────
# Fallback aggregator (no LLM) — first-non-null merge
# ─────────────────────────────────────────────────────────────


_MUT_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s+([A-Z])(\d{1,4})([A-Z])\b")


def _heuristic_aggregate(
    docs: list[DocumentExtraction],
) -> tuple[PathologyFindings, ClinicianIntake, list[Mutation], list[ProvenanceEntry]]:
    pathology = PathologyFindings(confidence=0.3, notes="Heuristic merge — Kimi unavailable.")
    intake = ClinicianIntake()
    provenance: list[ProvenanceEntry] = []
    mutations: list[Mutation] = []
    seen_muts: set[tuple[str, str, int, str]] = set()

    def _set(obj, field: str, value, fname: str, page: int | None) -> None:
        if value is None:
            return
        current = getattr(obj, field, None)
        if current in (None, "unknown", ""):
            setattr(obj, field, value)
            provenance.append(ProvenanceEntry(
                field=field, value=str(value), filename=fname, page_number=page,
            ))

    for doc in docs:
        for page in doc.pages:
            _set(pathology, "melanoma_subtype", page.melanoma_subtype, doc.filename, page.page_number)
            _set(pathology, "breslow_thickness_mm", page.breslow_thickness_mm, doc.filename, page.page_number)
            _set(pathology, "ulceration", page.ulceration, doc.filename, page.page_number)
            _set(pathology, "mitotic_rate_per_mm2", page.mitotic_rate_per_mm2, doc.filename, page.page_number)
            _set(pathology, "tils_present", page.tils_present, doc.filename, page.page_number)
            _set(pathology, "pdl1_estimate", page.pdl1_estimate, doc.filename, page.page_number)
            _set(pathology, "lag3_ihc_percent", page.lag3_ihc_percent, doc.filename, page.page_number)
            _set(intake, "ajcc_stage", page.ajcc_stage, doc.filename, page.page_number)
            _set(intake, "age_years", page.age_years, doc.filename, page.page_number)
            _set(intake, "ecog", page.ecog, doc.filename, page.page_number)
            _set(intake, "measurable_disease_recist", page.measurable_disease_recist, doc.filename, page.page_number)
            _set(intake, "life_expectancy_months", page.life_expectancy_months, doc.filename, page.page_number)
            _set(intake, "prior_systemic_therapy", page.prior_systemic_therapy, doc.filename, page.page_number)
            _set(intake, "prior_anti_pd1", page.prior_anti_pd1, doc.filename, page.page_number)

            for mtxt in page.mutations_text:
                m = _MUT_RE.search(mtxt)
                if not m:
                    continue
                key = (m.group(1), m.group(2), int(m.group(3)), m.group(4))
                if key in seen_muts:
                    continue
                seen_muts.add(key)
                mutations.append(Mutation(
                    gene=key[0], ref_aa=key[1], position=key[2], alt_aa=key[3],
                ))
                provenance.append(ProvenanceEntry(
                    field=f"mutation:{key[0]} {key[1]}{key[2]}{key[3]}",
                    value=f"{key[0]} {key[1]}{key[2]}{key[3]}",
                    filename=doc.filename,
                    page_number=page.page_number,
                ))

    return pathology, intake, mutations, provenance


# ─────────────────────────────────────────────────────────────
# Prompt building
# ─────────────────────────────────────────────────────────────


def _render_docs_for_prompt(docs: list[DocumentExtraction]) -> str:
    blocks: list[str] = []
    for doc in docs:
        blocks.append(f"=== FILE: {doc.filename} ({doc.document_kind}, {doc.page_count} pages) ===")
        for page in doc.pages:
            blocks.append(f"--- page {page.page_number} ---")
            blocks.append(f"description: {page.description}")
            shown_fields = {
                "melanoma_subtype": page.melanoma_subtype,
                "breslow_thickness_mm": page.breslow_thickness_mm,
                "ulceration": page.ulceration,
                "mitotic_rate_per_mm2": page.mitotic_rate_per_mm2,
                "tils_present": page.tils_present,
                "pdl1_estimate": page.pdl1_estimate,
                "lag3_ihc_percent": page.lag3_ihc_percent,
                "ajcc_stage": page.ajcc_stage,
                "age_years": page.age_years,
                "ecog": page.ecog,
                "measurable_disease_recist": page.measurable_disease_recist,
                "life_expectancy_months": page.life_expectancy_months,
                "prior_systemic_therapy": page.prior_systemic_therapy,
                "prior_anti_pd1": page.prior_anti_pd1,
            }
            for k, v in shown_fields.items():
                if v is not None:
                    blocks.append(f"{k}: {v}")
            if page.mutations_text:
                blocks.append("mutations_text: " + "; ".join(page.mutations_text))
            if page.notes:
                blocks.append(f"notes: {page.notes}")
        blocks.append("")
    return "\n".join(blocks)


# ─────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────


async def aggregate_documents(
    docs: list[DocumentExtraction],
) -> tuple[PathologyFindings, ClinicianIntake, list[Mutation], list[ProvenanceEntry], list[str]]:
    """Reconcile N DocumentExtractions into one canonical record.

    Returns (pathology, intake, mutations, provenance, conflicts).
    """
    await emit(
        EventKind.AGGREGATION_START,
        f"Aggregating {len(docs)} documents with Kimi K2",
        {"doc_count": len(docs)},
    )

    if not has_api_key() or not docs:
        pathology, intake, muts, provenance = _heuristic_aggregate(docs)
        await emit(
            EventKind.AGGREGATION_DONE,
            f"Heuristic merge · {len(muts)} mutations · {len(provenance)} provenance entries",
            {"fallback": True},
        )
        return pathology, intake, muts, provenance, []

    prompt_body = _render_docs_for_prompt(docs)
    user_prompt = (
        "Reconcile the following per-page findings into a single canonical JSON "
        "record. Use the per-field source_filename + source_page to cite where "
        "each value came from. List any conflicts.\n\n"
        f"{prompt_body}\n"
        "Return the JSON now."
    )

    try:
        payload = await call_for_json(
            schema=_AggPayload,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=3000,
        )
    except Exception as e:
        pathology, intake, muts, provenance = _heuristic_aggregate(docs)
        await emit(
            EventKind.AGGREGATION_DONE,
            f"Kimi aggregator failed ({type(e).__name__}) — used heuristic merge",
            {"fallback": True, "error": str(e)},
        )
        return pathology, intake, muts, provenance, [f"aggregator_error: {e}"]

    pathology, intake, muts, provenance = _payload_to_models(payload)
    await emit(
        EventKind.AGGREGATION_DONE,
        f"{len(muts)} mutations · {len(provenance)} provenance entries · "
        f"{len(payload.conflicts)} conflicts",
        {
            "conflicts": list(payload.conflicts),
            "mutation_count": len(muts),
        },
    )
    return pathology, intake, muts, provenance, list(payload.conflicts)


__all__ = ["aggregate_documents"]


_ = asyncio  # silence unused-import linter when no concurrency is used here
