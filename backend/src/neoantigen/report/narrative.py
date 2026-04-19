"""Narrative prose for the oncologist consult-note PDF.

Exposes two helpers:

* ``assessment_paragraphs(case)``     → list[str]: clinical impression.
* ``treatment_plan_paragraphs(case)`` → list[str]: recommended plan.

Both prefer a single K2 call ([agent/_llm.call_for_json]) when
``has_api_key()`` is True, and fall back to deterministic templates when the
key is missing, the call fails, or the response doesn't parse. Generation is
designed to be run inside a running asyncio loop (PDF route is async), with a
threaded fallback for rare sync callers.

Both functions are synchronous on purpose: ReportLab's document build loop is
sync, so the PDF builder shouldn't have to be rewritten as a coroutine just
for this.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from ..models import Mutation, PatientCase, RailwayStep


class _Paragraphs(BaseModel):
    paragraphs: list[str] = Field(default_factory=list)


def _mut_summary(mutations: list[Mutation], limit: int = 6) -> str:
    if not mutations:
        return "no point mutations reported"
    labels = [m.full_label for m in mutations[:limit]]
    more = len(mutations) - limit
    tail = f" (+{more} more)" if more > 0 else ""
    return ", ".join(labels) + tail


def _chosen_path(steps: list[RailwayStep], limit: int = 6) -> str:
    if not steps:
        return ""
    parts = []
    for s in steps[:limit]:
        label = s.chosen_option_label.strip() or s.title.strip()
        if label:
            parts.append(label)
    return " → ".join(parts)


def _stage_phrase(case: PatientCase) -> str:
    stage = (case.intake.ajcc_stage or "").strip() or "unstaged"
    ctype = (case.primary_cancer_type or case.pathology.primary_cancer_type or "cancer").replace("_", " ")
    return f"{stage} {ctype}"


def _age_phrase(case: PatientCase) -> str:
    age = case.intake.age_years
    if age is None:
        return "an adult patient"
    return f"a {age}-year-old patient"


def _ecog_phrase(case: PatientCase) -> str:
    e = case.intake.ecog
    return f"ECOG {e}" if e is not None else "ECOG not documented"


def _prior_therapy_phrase(case: PatientCase) -> str:
    enr = case.enrichment
    if enr and enr.prior_systemic_therapies:
        return "prior systemic therapy including " + ", ".join(enr.prior_systemic_therapies)
    if case.intake.prior_systemic_therapy is True:
        return "prior systemic therapy (agents not specified)"
    if case.intake.prior_systemic_therapy is False:
        return "treatment-naive"
    return "prior therapy history not documented"


def _assessment_template(case: PatientCase) -> list[str]:
    path = case.pathology
    mut_phrase = _mut_summary(case.mutations)
    hist_bits = []
    if path.histology:
        hist_bits.append(path.histology.replace("_", " "))
    if path.primary_site:
        hist_bits.append(f"arising from {path.primary_site}")
    if path.breslow_thickness_mm is not None:
        hist_bits.append(f"Breslow {path.breslow_thickness_mm:.1f} mm")
    if path.ulceration is True:
        hist_bits.append("ulcerated")
    if path.mitotic_rate_per_mm2 is not None:
        hist_bits.append(f"mitotic rate {path.mitotic_rate_per_mm2}/mm²")
    hist_str = ", ".join(hist_bits) or "histologic detail limited on the submitted material"

    biomarker_bits = []
    if path.pdl1_estimate and path.pdl1_estimate != "unknown":
        biomarker_bits.append(f"PD-L1 {path.pdl1_estimate.replace('_', ' ')}")
    if path.lag3_ihc_percent is not None:
        biomarker_bits.append(f"LAG-3 {path.lag3_ihc_percent:.0f}%")
    if path.tils_present and path.tils_present != "unknown":
        biomarker_bits.append(f"TILs {path.tils_present.replace('_', ' ')}")
    if case.enrichment and case.enrichment.tmb_mut_per_mb is not None:
        biomarker_bits.append(f"TMB {case.enrichment.tmb_mut_per_mb:.1f} mut/Mb")
    biomarker_str = ", ".join(biomarker_bits) or "biomarker panel limited"

    p1 = (
        f"{_age_phrase(case).capitalize()} presents with {_stage_phrase(case)}, "
        f"{_ecog_phrase(case)}, and {_prior_therapy_phrase(case)}. "
        f"Disease is {'measurable' if case.intake.measurable_disease_recist else 'not clearly measurable'} "
        f"by RECIST on the available records."
    )
    p2 = (
        f"Pathology demonstrates {hist_str}. Molecular profiling identifies {mut_phrase}. "
        f"Supporting biomarkers: {biomarker_str}."
    )
    conflicts = [c for c in (case.conflicts or []) if c]
    if conflicts:
        conf = "; ".join(conflicts[:3])
        p3 = (
            f"Note: the following data-quality issues were flagged during intake and should "
            f"be reconciled before finalizing the plan: {conf}."
        )
        return [p1, p2, p3]
    return [p1, p2]


def _plan_template(case: PatientCase) -> list[str]:
    steps = case.railway.steps if case.railway else []
    path = _chosen_path(steps)
    final_step: RailwayStep | None = steps[-1] if steps else None
    final_rec = (
        (case.final_recommendation or "")
        or (case.railway.final_recommendation if case.railway else "")
        or ""
    ).strip()

    if not steps and not final_rec:
        return [
            "No NCCN railway was walked for this case. Recommend multidisciplinary review "
            "before initiating systemic therapy."
        ]

    p1_bits: list[str] = []
    if path:
        p1_bits.append(f"The NCCN-aligned path walked for this patient is: {path}.")
    if final_rec:
        p1_bits.append(f"The final recommendation on that path is {final_rec}.")
    elif final_step and final_step.chosen_rationale:
        p1_bits.append(
            f"The terminal decision favors {final_step.chosen_option_label}: "
            f"{final_step.chosen_rationale}"
        )
    p1 = " ".join(p1_bits) or "Treatment plan under active review."

    p2_bits: list[str] = [
        "Next steps for the treating team:",
    ]
    # Gather any still-unresolved intake fields
    missing: list[str] = []
    if case.intake.ecog is None:
        missing.append("ECOG performance status")
    if case.intake.measurable_disease_recist is None:
        missing.append("RECIST measurability")
    if case.intake.prior_systemic_therapy is None:
        missing.append("prior systemic therapy history")
    if missing:
        p2_bits.append("• Confirm " + ", ".join(missing) + ".")
    if case.trial_matches:
        eligible = [m for m in case.trial_matches if m.status == "eligible"]
        if eligible:
            p2_bits.append(
                f"• Review {len(eligible)} clinical trial(s) flagged as eligible (see next section)."
            )
        else:
            p2_bits.append(
                "• Review clinical-trial options below; none scored as outright eligible on the current intake."
            )
    p2_bits.append(
        "• Re-stage per institutional protocol and schedule multidisciplinary tumor board review."
    )
    return [p1, "\n".join(p2_bits)]


def _case_context_blob(case: PatientCase) -> str:
    """Compact, LLM-friendly case summary: keep under ~1.5k tokens."""
    lines: list[str] = []
    lines.append(f"Case ID: {case.case_id}")
    lines.append(f"Primary cancer type: {case.primary_cancer_type or 'unknown'}")
    lines.append(f"Stage: {case.intake.ajcc_stage or 'unstaged'}")
    lines.append(f"Age: {case.intake.age_years or 'unknown'}")
    lines.append(f"ECOG: {case.intake.ecog if case.intake.ecog is not None else 'unknown'}")
    lines.append(
        f"Measurable disease (RECIST): "
        f"{case.intake.measurable_disease_recist if case.intake.measurable_disease_recist is not None else 'unknown'}"
    )
    lines.append(
        f"Prior systemic therapy: "
        f"{case.intake.prior_systemic_therapy if case.intake.prior_systemic_therapy is not None else 'unknown'}"
    )
    lines.append(
        f"Prior anti-PD-1: "
        f"{case.intake.prior_anti_pd1 if case.intake.prior_anti_pd1 is not None else 'unknown'}"
    )
    p = case.pathology
    lines.append(
        "Pathology: histology="
        + (p.histology or "-")
        + f"; site={p.primary_site or '-'}"
        + f"; subtype={p.melanoma_subtype}"
        + f"; Breslow={p.breslow_thickness_mm}"
        + f"; ulceration={p.ulceration}"
        + f"; mitoses/mm²={p.mitotic_rate_per_mm2}"
        + f"; TILs={p.tils_present}"
        + f"; PD-L1={p.pdl1_estimate}"
        + f"; LAG-3%={p.lag3_ihc_percent}"
    )
    if p.notes:
        lines.append(f"Path notes: {p.notes[:400]}")
    if case.enrichment:
        e = case.enrichment
        lines.append(
            f"Enrichment: TMB={e.tmb_mut_per_mb}; UV_sig={e.uv_signature_fraction}; "
            f"SNVs={e.total_snvs_scored}; prior_therapies={e.prior_systemic_therapies}"
        )
    if case.mutations:
        lines.append("Mutations: " + _mut_summary(case.mutations, limit=10))
    if case.railway and case.railway.steps:
        lines.append("Railway path:")
        for s in case.railway.steps[:12]:
            rationale = (s.chosen_rationale or "").strip().replace("\n", " ")
            if len(rationale) > 260:
                rationale = rationale[:257] + "..."
            lines.append(
                f"  - [{s.phase_title or s.phase_id or '?'}] {s.title}: "
                f"chose {s.chosen_option_label}. {rationale}"
            )
    final_rec = (
        (case.final_recommendation or "")
        or (case.railway.final_recommendation if case.railway else "")
    )
    if final_rec:
        lines.append(f"Final recommendation: {final_rec}")
    if case.conflicts:
        lines.append("Conflicts: " + "; ".join(case.conflicts[:5]))
    return "\n".join(lines)


_ASSESSMENT_SYSTEM = (
    "You are a board-certified medical oncologist writing the ASSESSMENT section "
    "of a written consult note. Tone: formal, chart-note register: NOT patient-facing "
    "speech. Use standard oncology shorthand where appropriate (ECOG, RECIST, TMB, PD-L1). "
    "Do not hedge with 'I think'. Do not greet the reader. No markdown, no headings, "
    "no bullet points. 2–3 tight paragraphs summarizing: (1) patient and disease at "
    "presentation, (2) pathology and molecular drivers, (3) any data-quality caveats."
)

_PLAN_SYSTEM = (
    "You are a board-certified medical oncologist writing the TREATMENT PLAN section "
    "of a written consult note. Tone: formal, chart-note register. Ground your plan in "
    "the NCCN-aligned railway path and final recommendation provided. No markdown, no "
    "headings. Two short paragraphs: (1) the proposed first-line treatment and its "
    "rationale, citing the railway decision; (2) concrete next steps as a simple list "
    "using '• ' bullets inside the paragraph: staging, labs, outstanding data, trial "
    "referral, tumor-board timing."
)


def _run_coro_sync(coro) -> Any:
    """Run a coroutine from a possibly-async caller without blocking a running loop.

    ReportLab builds the PDF synchronously, but the FastAPI report route is async,
    so there IS a running loop when we get here. We offload the coroutine to a
    fresh event loop on a worker thread and block the caller until it returns.
    If we're not inside a loop at all, just asyncio.run it.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import threading

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=120)
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _llm_paragraphs(system_prompt: str, case: PatientCase) -> list[str] | None:
    """Call K2 for a ``{paragraphs: [...]}`` blob. Returns None on any failure."""
    try:
        from ..agent._llm import call_for_json, has_api_key
    except Exception:
        return None
    if not has_api_key():
        return None

    user = (
        "Case context for the consult note:\n\n"
        + _case_context_blob(case)
        + "\n\nReturn a JSON object with key 'paragraphs' whose value is a list of "
        "plain-text paragraphs (strings). No markdown. No leading labels like "
        "'Assessment:': the section heading is added separately."
    )

    try:
        result: _Paragraphs = _run_coro_sync(
            call_for_json(_Paragraphs, system_prompt, user, max_tokens=1200)
        )
    except Exception:
        return None
    paragraphs = [p.strip() for p in (result.paragraphs or []) if p and p.strip()]
    return paragraphs or None


def assessment_paragraphs(case: PatientCase) -> list[str]:
    """Return 2–3 paragraphs of clinical assessment prose."""
    llm = _llm_paragraphs(_ASSESSMENT_SYSTEM, case)
    if llm:
        return llm
    return _assessment_template(case)


def treatment_plan_paragraphs(case: PatientCase) -> list[str]:
    """Return 2 paragraphs of treatment-plan prose with inline bullets."""
    llm = _llm_paragraphs(_PLAN_SYSTEM, case)
    if llm:
        return llm
    return _plan_template(case)


__all__ = [
    "assessment_paragraphs",
    "treatment_plan_paragraphs",
]
