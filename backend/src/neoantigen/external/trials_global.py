"""Cancer-type-agnostic global trial search.

Regeneron matches (``regeneron_rules.evaluate_all``) stay as tier 1 because
we have hand-written predicate logic for their 29 NCTs. This module fills
tier 2: every other recruiting trial ClinicalTrials.gov returns for the
patient's cancer type. Those come back as ``TrialMatch`` with
``status="unscored"`` since we don't have per-trial eligibility predicates
for the long tail. The frontend then ranks them by distance to the patient.

Entrypoint: :func:`search_global_trials`.
"""

from __future__ import annotations

from ..models import PatientCase, TrialMatch
from .trials import CTGovStudy, fetch_trials_by_condition


# ─────────────────────────────────────────────────────────────
# Cancer type → CT.gov condition query
#
# CT.gov's query.cond search is fuzzy-but-narrow, so we map our snake_case
# tokens to the clinical phrases that match the widest pool of relevant
# trials. "Melanoma" alone drags in 3k+ studies; "Lung Adenocarcinoma"
# narrows the corpus without missing the big ones.
# ─────────────────────────────────────────────────────────────

_CANCER_TYPE_QUERIES: dict[str, str] = {
    "cutaneous_melanoma": "Melanoma",
    "lung_adenocarcinoma": "Lung Adenocarcinoma",
    "lung_squamous": "Lung Squamous Cell Carcinoma",
    "breast_ductal_carcinoma": "Breast Cancer",
    "breast_carcinoma": "Breast Cancer",
    "colorectal_adenocarcinoma": "Colorectal Cancer",
    "colorectal_carcinoma": "Colorectal Cancer",
    "gastric_carcinoma": "Gastric Cancer",
    "pancreatic_carcinoma": "Pancreatic Cancer",
    "prostate_carcinoma": "Prostate Cancer",
    "ovarian_carcinoma": "Ovarian Cancer",
    "renal_cell_carcinoma": "Renal Cell Carcinoma",
    "hepatocellular_carcinoma": "Hepatocellular Carcinoma",
    "bladder_carcinoma": "Bladder Cancer",
    "head_neck_scc": "Head and Neck Squamous Cell Carcinoma",
    "glioblastoma": "Glioblastoma",
    "lymphoma_dlbcl": "Diffuse Large B-Cell Lymphoma",
    "multiple_myeloma": "Multiple Myeloma",
}


def _cancer_type_to_query(cancer_type: str | None) -> str | None:
    if not cancer_type:
        return None
    key = cancer_type.strip().lower()
    if key in ("", "unknown", "other"):
        return None
    return _CANCER_TYPE_QUERIES.get(key, cancer_type.replace("_", " "))


# ─────────────────────────────────────────────────────────────
# CTGovStudy → TrialMatch
# ─────────────────────────────────────────────────────────────


def _study_to_match(study: CTGovStudy, cancer_query: str) -> TrialMatch:
    """Minimal, non-judgmental TrialMatch from a CT.gov row.

    The long tail has no hand-written predicates, so we don't emit
    passing/failing/unknown verdicts. ``status="unscored"`` signals to the UI
    that this is an 'also consider' trial, not a vetted match.
    ``passing_criteria`` lists only the facts we know from the CT.gov row
    itself: matched cancer, recruiting status, trial phase.
    """
    passing: list[str] = []
    if study.conditions:
        passing.append(f"Condition matches: {cancer_query}")
    if study.overall_status:
        passing.append(f"Site status: {study.overall_status.lower().replace('_', ' ')}")
    if study.phase:
        passing.append(f"Phase: {study.phase}")

    return TrialMatch(
        nct_id=study.nct_id,
        title=study.brief_title or study.nct_id,
        sponsor=study.sponsor or "Unknown",
        phase=study.phase,
        status="unscored",
        passing_criteria=passing,
        failing_criteria=[],
        unknown_criteria=[],
        is_regeneron=False,
        url=study.url,
    )


# ─────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────


async def search_global_trials(
    case: PatientCase,
    *,
    exclude_nct_ids: set[str] | None = None,
    limit: int = 20,
) -> list[TrialMatch]:
    """Return up to ``limit`` recruiting trials for the case's cancer type.

    Filters out any NCT in ``exclude_nct_ids`` (the Regeneron tier already
    covers those with richer scoring). Returns ``[]`` when the cancer type
    can't be mapped, when CT.gov is unreachable, or when nothing recruiting
    came back.
    """
    cancer_type = case.primary_cancer_type or case.pathology.primary_cancer_type
    query = _cancer_type_to_query(cancer_type)
    if not query:
        return []

    excluded = {n.upper() for n in (exclude_nct_ids or set())}

    studies = await fetch_trials_by_condition(
        query,
        recruiting_only=True,
        page_size=max(50, limit * 3),  # overfetch so dedupe doesn't starve the list
    )

    matches: list[TrialMatch] = []
    seen: set[str] = set()
    for s in studies:
        nct = s.nct_id.upper()
        if nct in excluded or nct in seen:
            continue
        seen.add(nct)
        matches.append(_study_to_match(s, query))
        if len(matches) >= limit:
            break
    return matches


__all__ = ["search_global_trials"]
