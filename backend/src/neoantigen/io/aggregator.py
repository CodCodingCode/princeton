"""Kimi K2 cross-document aggregator.

Per-PDF extraction produces a ``DocumentExtraction`` with per-page vision
findings. When a case has multiple PDFs, those N document extractions almost
always contain overlapping and sometimes contradictory fields
(pathology report says Breslow 2.1 mm, a separate addendum says 2.3 mm, etc.).
This module hands every per-doc finding to Kimi K2 and asks it to:

  1. Reconcile conflicts - pick the most authoritative value and list the
     others under ``conflicts``.
  2. Deduplicate mutations across reports.
  3. Emit a single canonical ``PathologyFindings`` + ``ClinicianIntake`` +
     ``list[Mutation]`` plus per-field ``provenance`` pointing to the source
     document and page.

Falls back cleanly when Kimi is unavailable - merges by first-non-null with a
placeholder provenance.
"""

from __future__ import annotations

import asyncio
import os
import re

from pydantic import BaseModel, Field, model_validator

from ..agent._llm import call_for_json, has_api_key
from ..agent.audit import audit
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
# Kimi K2 aggregator schema - the canonical patient record
# ─────────────────────────────────────────────────────────────


class _AggMutation(BaseModel):
    """Permissive mutation shape.

    Real oncogenic events don't always fit {gene, ref_aa, position, alt_aa}:
    exon deletions, fusions, amplifications, splice variants all lack a single
    residue-position substitution. Every structural field is optional; a
    free-form ``raw_label`` (e.g. "EGFR exon 19 deletion") survives when the
    model can't decompose it.

    We also accept the model's invented shape ``{"EGFR exon 19 deletion":
    "source.pdf_p2"}`` via ``model_validator``: coercing it into the proper
    fields instead of failing validation and silently dropping the mutation.
    """

    gene: str = ""
    ref_aa: str = ""
    position: int | None = None
    alt_aa: str = ""
    raw_label: str = ""
    source_filename: str = ""
    source_page: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_permissive(cls, data: object) -> object:
        """Be forgiving: MediX-R1 invents a new mutation schema every run.

        Seen in the wild:
          A.  {"gene": "EGFR", "ref_aa": "E", "position": 746, "alt_aa": "A"} ← spec shape, already valid
          B.  {"EGFR exon 19 deletion": "file.pdf_p2"}                        ← dict-as-key
          C.  {"name": "EGFR T790M", "value": "c.2369C>T",
               "source": "FILE: 15_hospital_discharge_summary.pdf (page 1)"}  ← name/value/source
          D.  {"mutation": "EGFR exon 19 deletion", ...}                      ← single "mutation" key

        We flatten all four into ``{raw_label, source_filename, source_page}``
        when the spec fields aren't already populated, so the downstream
        regex parser gets a shot at structural extraction.
        """
        if not isinstance(data, dict):
            return data
        spec_keys = {"gene", "ref_aa", "position", "alt_aa", "raw_label",
                     "source_filename", "source_page"}
        # Shape A: already compliant, let pydantic validate normally.
        if any(k in data and data[k] not in (None, "") for k in ("gene", "raw_label")):
            return data

        label = ""
        source_blob = ""
        # Shape C/D: common-name keys.
        for label_key in ("name", "mutation", "variant", "label", "description"):
            if label_key in data and isinstance(data[label_key], str):
                label = data[label_key]
                break
        # Append "value" (e.g. "p.E746_A750del") to the label when present.
        val = data.get("value")
        if isinstance(val, str) and val and val != label:
            label = f"{label} ({val})" if label else val
        # Source: try common keys.
        for src_key in ("source", "source_filename", "file", "filename", "cite"):
            if src_key in data and isinstance(data[src_key], str):
                source_blob = data[src_key]
                break

        # Shape B: single unknown key, value is source-like.
        if not label:
            unknown = {k: v for k, v in data.items() if k not in spec_keys}
            if len(unknown) == 1:
                k, v = next(iter(unknown.items()))
                if isinstance(k, str):
                    label = k
                if isinstance(v, str) and not source_blob:
                    source_blob = v

        if not label:
            return data  # pydantic will fail validation: fine.

        # Parse source blob. Patterns observed:
        #   "file.pdf_p2"                                    → (file.pdf, 2)
        #   "FILE: file.pdf (page 1)"                        → (file.pdf, 1)
        #   "file.pdf, page 3"                               → (file.pdf, 3)
        #   "file.pdf"                                       → (file.pdf, None)
        source_filename, source_page = "", None
        if source_blob:
            m = re.search(r"([\w.\-]+\.(?:pdf|txt|csv|json|png|jpg|jpeg))", source_blob, re.I)
            if m:
                source_filename = m.group(1)
            m = re.search(r"(?:page|_p)\s*(\d+)", source_blob, re.I)
            if m:
                try:
                    source_page = int(m.group(1))
                except ValueError:
                    pass
            if not source_filename:
                source_filename = source_blob  # best-effort fallback

        return {
            "raw_label": label,
            "source_filename": source_filename,
            "source_page": source_page,
        }


_NULL_STRINGS = {"", "null", "none", "n/a", "na", "unknown", "not applicable", "-"}


class _AggField(BaseModel):
    """One extracted field + its source. Every subfield is lenient about the
    model's inventive null-equivalents so validation doesn't drop the whole
    payload over cosmetic "n/a" strings where a real int / null was expected.
    """

    value: str | None = None
    source_filename: str = ""
    source_page: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_nulls(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        # value: accepts str | None. Normalize string null-equivalents to None.
        v = out.get("value")
        if isinstance(v, str) and v.strip().lower() in _NULL_STRINGS:
            out["value"] = None
        elif isinstance(v, (int, float, bool)):
            # Some models emit native numbers/bools; stringify so downstream
            # parsers (_parse_float, _parse_bool) can consume uniformly.
            out["value"] = str(v).lower() if isinstance(v, bool) else str(v)
        # source_filename: required str, default "". None or null-strings → "".
        sf = out.get("source_filename")
        if sf is None:
            out["source_filename"] = ""
        elif isinstance(sf, str) and sf.strip().lower() in _NULL_STRINGS:
            out["source_filename"] = ""
        elif not isinstance(sf, str):
            out["source_filename"] = str(sf)
        # source_page: str|int|None. Coerce "n/a"/"null"/"" → None; parse ints.
        sp = out.get("source_page")
        if isinstance(sp, str):
            lo = sp.strip().lower()
            if lo in _NULL_STRINGS:
                out["source_page"] = None
            else:
                try:
                    out["source_page"] = int(lo)
                except (ValueError, TypeError):
                    out["source_page"] = None
        elif isinstance(sp, float):
            out["source_page"] = int(sp)
        # None is already fine for source_page.
        return out


class _AggPayload(BaseModel):
    """Schema Kimi K2 fills in when reconciling across PDFs."""

    primary_cancer_type: _AggField = Field(default_factory=_AggField)
    histology: _AggField = Field(default_factory=_AggField)
    primary_site: _AggField = Field(default_factory=_AggField)
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


SYSTEM_PROMPT = """You are an oncology chart reconciler. You will be given the
per-page findings extracted from a patient's full document folder (pathology
reports, IHC addenda, NGS reports, imaging reports, H&P notes). Multiple pages
and multiple PDFs often mention the same field with slightly different values.
The patient may have any cancer type - melanoma, lung, breast, colorectal,
etc. - so do NOT force fields into a melanoma frame.

Field priority tier 1 - cancer identity. These drive downstream literature
retrieval, so a wrong value here poisons the whole railway:

  primary_cancer_type, histology, primary_site

Always prefer the primary pathology report for these. `primary_cancer_type`
must be a stable snake_case token (cutaneous_melanoma, lung_adenocarcinoma,
lung_squamous, breast_ductal_carcinoma, colorectal_adenocarcinoma, gastric_carcinoma,
pancreatic_carcinoma, prostate_carcinoma, ovarian_carcinoma, renal_cell_carcinoma,
hepatocellular_carcinoma, bladder_carcinoma, head_neck_scc, glioblastoma,
lymphoma_dlbcl, multiple_myeloma, other).

Field priority tier 2 - clinical pathology fields used by the melanoma
NCCN-style reasoning path when applicable:

  melanoma_subtype, breslow_thickness_mm, ulceration, mitotic_rate_per_mm2,
  tils_present, pdl1_estimate, lag3_ihc_percent

For these, prefer the primary pathology report or IHC addendum over a
clinical-note summary, even when the note is more recent. A consult note
saying "Breslow ~2 mm" must lose to the pathology report saying "Breslow
2.1 mm". An IHC addendum must win over a consult note that says "PD-L1
pending". For non-melanoma cases most of these stay null - that is fine.

Field priority tier 3 - trial-eligibility, prefer the most recent clinical
note since these change over time: ajcc_stage, age_years, ecog,
measurable_disease_recist, life_expectancy_months, prior_systemic_therapy,
prior_anti_pd1.

Your job:
  * Pick ONE authoritative value per field following the priority above.
  * For every field you emit, record the source filename and page_number.
  * Deduplicate mutations - if BRAF V600E appears on pages 2 and 7 of the
    NGS report and again in a summary, emit it once with the most specific
    source (prefer the NGS report over a summary).
  * When two sources truly contradict, pick the most authoritative per the
    priority above, emit that value, and add a one-line entry to `conflicts`
    describing the disagreement (e.g. "Breslow: path report 2.1 mm vs consult
    note 'approx 2 mm' - used path report").
  * Leave a field's value null if NONE of the pages mentioned it. Do not guess.
  * Enum fields:
      - melanoma_subtype ∈ {superficial_spreading, nodular, lentigo_maligna,
        acral_lentiginous, desmoplastic, other, unknown}
      - tils_present ∈ {absent, non_brisk, brisk, unknown}
      - pdl1_estimate ∈ {negative, low, high, unknown}
  * Numeric fields: return as strings so you can include units ("2.1", "2.1 mm"
    are both fine - we parse them). For booleans, return "true" or "false".
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
        "primary_cancer_type", "histology", "primary_site",
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
        primary_cancer_type=(payload.primary_cancer_type.value or "unknown"),
        histology=(payload.histology.value or ""),
        primary_site=(payload.primary_site.value or ""),
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
    seen_keys: set[tuple[str, str, int, str]] = set()
    seen_labels: set[str] = set()
    for m in payload.mutations:
        # 1. Try structural: if the model populated gene/ref/pos/alt directly.
        if m.gene and m.ref_aa and m.position is not None and m.alt_aa:
            key = (m.gene.upper(), m.ref_aa.upper(), int(m.position), m.alt_aa.upper())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            mut = Mutation(
                gene=key[0], ref_aa=key[1], position=key[2], alt_aa=key[3],
                raw_label=f"{key[0]} {key[1]}{key[2]}{key[3]}",
            )
            mutations.append(mut)
            prov_value = mut.full_label
        else:
            # 2. Fall back to raw_label. Regex-extract structural fields when
            # the label matches a point-mutation pattern; otherwise store as
            # free-form (exon deletions, fusions, amplifications, etc.).
            label = (m.raw_label or "").strip()
            if not label:
                continue
            canonical_label = label.upper()
            if canonical_label in seen_labels:
                continue
            seen_labels.add(canonical_label)
            hit = _MUT_RE.search(label)
            if hit:
                gene, ref_aa, position, alt_aa = (
                    hit.group(1), hit.group(2), int(hit.group(3)), hit.group(4),
                )
                key = (gene.upper(), ref_aa.upper(), position, alt_aa.upper())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                mutations.append(Mutation(
                    gene=gene.upper(), ref_aa=ref_aa.upper(), position=position,
                    alt_aa=alt_aa.upper(), raw_label=label,
                ))
            else:
                # Free-form event (EGFR exon 19 deletion, MET amplification, ...)
                # Best-effort gene extraction: first all-caps token.
                gene_guess = ""
                for token in label.split():
                    t = token.strip(",.;:()[]")
                    if t.isupper() and 2 <= len(t) <= 10 and t.isalnum():
                        gene_guess = t
                        break
                mutations.append(Mutation(gene=gene_guess, raw_label=label))
            prov_value = label
        if m.source_filename:
            provenance.append(ProvenanceEntry(
                field=f"mutation:{prov_value}",
                value=prov_value,
                filename=m.source_filename,
                page_number=m.source_page,
            ))

    return pathology, intake, mutations, provenance


# ─────────────────────────────────────────────────────────────
# Fallback aggregator (no LLM) - first-non-null merge
# ─────────────────────────────────────────────────────────────


_MUT_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\s+([A-Z])(\d{1,4})([A-Z])\b")


def _heuristic_aggregate(
    docs: list[DocumentExtraction],
    reason: str = "Heuristic merge - reason unspecified.",
) -> tuple[PathologyFindings, ClinicianIntake, list[Mutation], list[ProvenanceEntry]]:
    pathology = PathologyFindings(confidence=0.3, notes=reason)
    intake = ClinicianIntake()
    provenance: list[ProvenanceEntry] = []
    mutations: list[Mutation] = []
    seen_muts: set[tuple[str, str, int, str]] = set()
    seen_free: set[str] = set()

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
            _set(pathology, "primary_cancer_type", page.primary_cancer_type, doc.filename, page.page_number)
            _set(pathology, "histology", page.histology, doc.filename, page.page_number)
            _set(pathology, "primary_site", page.primary_site, doc.filename, page.page_number)
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
                label = (mtxt or "").strip()
                if not label:
                    continue
                m = _MUT_RE.search(label)
                if m:
                    key = (m.group(1), m.group(2), int(m.group(3)), m.group(4))
                    if key in seen_muts:
                        continue
                    seen_muts.add(key)
                    mutations.append(Mutation(
                        gene=key[0], ref_aa=key[1], position=key[2],
                        alt_aa=key[3], raw_label=label,
                    ))
                    prov_value = f"{key[0]} {key[1]}{key[2]}{key[3]}"
                else:
                    # Free-form event (exon deletion, amplification, fusion).
                    canonical = label.upper()
                    if canonical in seen_free:
                        continue
                    seen_free.add(canonical)
                    gene_guess = ""
                    for token in label.split():
                        t = token.strip(",.;:()[]")
                        if t.isupper() and 2 <= len(t) <= 10 and t.isalnum():
                            gene_guess = t
                            break
                    mutations.append(Mutation(gene=gene_guess, raw_label=label))
                    prov_value = label
                provenance.append(ProvenanceEntry(
                    field=f"mutation:{prov_value}",
                    value=prov_value,
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
                "primary_cancer_type": page.primary_cancer_type,
                "histology": page.histology,
                "primary_site": page.primary_site,
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
        if not docs:
            reason = "Heuristic merge: no documents extracted."
        else:
            reason = "Heuristic merge: no API key configured (set KIMI_API_KEY)."
        pathology, intake, muts, provenance = _heuristic_aggregate(docs, reason=reason)
        audit(
            "aggregator", "fallback",
            reason=reason, doc_count=len(docs),
            had_api_key=has_api_key(),
        )
        await emit(
            EventKind.AGGREGATION_DONE,
            f"Heuristic merge · {len(muts)} mutations · {len(provenance)} provenance entries",
            {"fallback": True, "reason": reason},
        )
        return pathology, intake, muts, provenance, []

    prompt_body = _render_docs_for_prompt(docs)
    user_prompt = (
        "Reconcile the following per-page findings into a single canonical JSON "
        "record. Use the per-field source_filename + source_page to cite where "
        "each value came from. List any conflicts.\n\n"
        f"{prompt_body}\n"
        "Keep your reasoning brief - at most one short paragraph - then emit the "
        "JSON. If your thinking starts running long, cut it short and return the "
        "JSON; a partial JSON is useless."
    )

    # K2-Think's reasoning budget scales with document count. Seventeen docs
    # with ~20 fields each can burn 4-8k tokens on thinking alone before the
    # JSON block starts. 3000 was enough for single-doc cases and nothing else -
    # the model would truncate mid-reasoning and the caller saw "model did not
    # return valid JSON" with prose tail. Cap sits below the 8192 max_total
    # ceiling of the current vLLM server so we don't 400 on BadRequestError;
    # bump via NEOVAX_AGG_MAX_TOKENS if the backend is swapped to a larger
    # context window.
    # Aggregator input prompt for a typical case runs ~2500 tokens; with the
    # 8192-token ceiling on the vLLM-served model, leave safe headroom for
    # output. 6000 was observed to 400 on larger prompts.
    agg_max_tokens = int(os.environ.get("NEOVAX_AGG_MAX_TOKENS", "3500"))
    import time as _time
    t0 = _time.time()
    audit(
        "aggregator", "call_start",
        doc_count=len(docs), user_len=len(user_prompt),
        max_tokens=agg_max_tokens,
    )
    try:
        payload = await call_for_json(
            schema=_AggPayload,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=agg_max_tokens,
        )
    except Exception as e:
        err_msg = str(e)[:400]
        reason = f"Heuristic merge: LLM call failed: {type(e).__name__}: {err_msg}"
        pathology, intake, muts, provenance = _heuristic_aggregate(docs, reason=reason)
        audit(
            "aggregator", "fallback",
            reason=reason, doc_count=len(docs),
            user_len=len(user_prompt), max_tokens=agg_max_tokens,
            error_type=type(e).__name__, error=str(e),
            latency_ms=int((_time.time() - t0) * 1000),
        )
        await emit(
            EventKind.AGGREGATION_DONE,
            f"Kimi aggregator failed ({type(e).__name__}) - used heuristic merge",
            {"fallback": True, "error": str(e), "reason": reason},
        )
        return pathology, intake, muts, provenance, [f"aggregator_error: {e}"]

    pathology, intake, muts, provenance = _payload_to_models(payload)
    audit(
        "aggregator", "done",
        mutations=len(muts), provenance=len(provenance),
        conflicts=len(payload.conflicts),
        latency_ms=int((_time.time() - t0) * 1000),
    )
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
