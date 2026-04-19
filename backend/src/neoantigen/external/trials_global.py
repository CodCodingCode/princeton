"""Cancer-type-agnostic global trial search.

Regeneron matches (``regeneron_rules.evaluate_all``) stay as tier 1 because
we have hand-written predicate logic for their 29 NCTs. This module fills
tier 2: every other recruiting trial ClinicalTrials.gov returns for the
patient's cancer type. Each trial gets a heuristic eligibility verdict
scored from the CT.gov row + the patient case (age, ECOG, recruiting
status, phase, cancer-type match). The frontend then ranks them by
distance from the patient.

Entrypoint: :func:`search_global_trials`.
"""

from __future__ import annotations

import re

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
# Heuristic eligibility scoring
#
# We can't write trial-specific predicates for every CT.gov row (that would
# need a per-trial LLM pass), so we lean on the fields CT.gov gives us:
#   * minimum age (``eligibilityModule.minimumAge``, e.g. "18 Years")
#   * ECOG ceiling scraped from the free-text eligibility criteria
#   * recruiting status + phase
#   * cancer-type match (already enforced by the search)
# Verdict rules:
#   * any `failing` -> "ineligible"
#   * any `unknown` -> "needs_more_data"
#   * ≥3 dimensions passed -> "eligible"
#   * otherwise -> "needs_more_data"
# ─────────────────────────────────────────────────────────────


_AGE_YEARS_RE = re.compile(r"(\d{1,3})\s*Years?", re.IGNORECASE)

# ECOG pattern families - order matters, we try specific shapes first.
_ECOG_RANGE_RE = re.compile(r"ecog[^.\n]{0,120}?0\s*[-\u2013]\s*(\d)", re.IGNORECASE)
_ECOG_LTE_RE = re.compile(
    r"ecog[^.\n]{0,120}?(?:\u2264|<=|less\s+than\s+or\s+equal\s+to|at\s+most|not\s+(?:greater|higher|more)\s+than|\\bof\\b)\s*(\d)",
    re.IGNORECASE,
)


def _parse_min_age_years(min_age: str | None) -> int | None:
    """Parse CT.gov's minimumAge string into whole years."""
    if not min_age:
        return None
    m = _AGE_YEARS_RE.search(min_age)
    return int(m.group(1)) if m else None


def _parse_max_ecog(eligibility_text: str) -> int | None:
    """Best-effort: pull an ECOG ceiling from the free-text eligibility.

    Matches common shapes:
      * "ECOG performance status 0-1"
      * "ECOG performance status ≤ 1" / "<= 2" / "less than or equal to 2"
    Returns None if unclear so the caller can mark it as unknown rather
    than guess.
    """
    if not eligibility_text:
        return None
    m = _ECOG_RANGE_RE.search(eligibility_text)
    if m:
        return int(m.group(1))
    m = _ECOG_LTE_RE.search(eligibility_text)
    if m:
        return int(m.group(1))
    return None


def _score_trial(
    study: CTGovStudy, case: PatientCase, cancer_query: str,
) -> tuple[str, list[str], list[str], list[str]]:
    """Return ``(status, passing, failing, unknown)`` for a CT.gov study."""
    passing: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []

    # 1. Cancer-type match (search already filtered by condition).
    passing.append(f"Cancer type matches: {cancer_query}")

    # 2. Recruiting status.
    status_token = (study.overall_status or "").upper()
    if status_token == "RECRUITING":
        passing.append("Actively recruiting")
    elif status_token == "NOT_YET_RECRUITING":
        passing.append("Opening to enrollment soon")
    elif status_token:
        unknown.append(f"Site status: {status_token.replace('_', ' ').lower()}")

    # 3. Phase - informational pass when known.
    if study.phase:
        passing.append(f"Phase: {study.phase}")

    # 4. Age check.
    min_age = _parse_min_age_years(study.min_age)
    patient_age = case.intake.age_years
    if min_age is not None:
        if patient_age is None:
            unknown.append(f"Trial requires age ≥ {min_age}; patient age not captured")
        elif patient_age < min_age:
            failing.append(f"Requires age ≥ {min_age} (patient is {patient_age})")
        else:
            passing.append(f"Meets minimum age ({min_age}+)")

    # 5. ECOG ceiling.
    max_ecog = _parse_max_ecog(study.eligibility_text or "")
    patient_ecog = case.intake.ecog
    if max_ecog is not None:
        if patient_ecog is None:
            unknown.append(f"Trial requires ECOG ≤ {max_ecog}; patient ECOG not captured")
        elif patient_ecog > max_ecog:
            failing.append(f"Requires ECOG ≤ {max_ecog} (patient is {patient_ecog})")
        else:
            passing.append(f"Meets ECOG ≤ {max_ecog}")

    # Verdict.
    if failing:
        return "ineligible", passing, failing, unknown
    if unknown:
        return "needs_more_data", passing, failing, unknown
    if len(passing) >= 3:
        return "eligible", passing, failing, unknown
    return "needs_more_data", passing, failing, unknown


# ─────────────────────────────────────────────────────────────
# CTGovStudy → TrialMatch
# ─────────────────────────────────────────────────────────────


def _study_to_match(
    study: CTGovStudy, case: PatientCase, cancer_query: str,
) -> TrialMatch:
    status, passing, failing, unknown = _score_trial(study, case, cancer_query)
    return TrialMatch(
        nct_id=study.nct_id,
        title=study.brief_title or study.nct_id,
        sponsor=study.sponsor or "Unknown",
        phase=study.phase,
        status=status,
        passing_criteria=passing,
        failing_criteria=failing,
        unknown_criteria=unknown,
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
        matches.append(_study_to_match(s, case, query))
        if len(matches) >= limit:
            break
    return matches


__all__ = ["search_global_trials"]
