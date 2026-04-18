"""Regeneron melanoma trial registry + structured eligibility predicates.

Four trials (checked April 2026):
  NCT05352672 — Harmony Melanoma (Phase 3, 1L advanced, fianlimab + cemiplimab vs pembro)
  NCT06246916 — Harmony Head-to-Head (Phase 3, 1L advanced, vs nivo + rela)
  NCT06190951 — Neoadjuvant Phase 2 (fianlimab + cemiplimab, high-risk resectable)
  NCT04526899 — BNT111 + Libtayo (BioNTech partnership, fixed-antigen vaccine + PD-1)

Predicates are intentionally thin: we only assert what the pipeline's
`MelanomaCase` can actually prove. Everything else (ECOG, prior therapy, LAG-3
IHC, measurable disease per RECIST, etc.) is surfaced as `unknown_criteria` so
the clinician can fill in the gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import MelanomaCase, TrialMatch


# AJCC 8 T-stage buckets that suggest locally-advanced or high-risk disease.
# Used as a (necessary-but-not-sufficient) proxy for "advanced" since we don't
# have N/M from the pathology slide.
ADVANCED_T_STAGES = {"T3a", "T3b", "T4a", "T4b"}
HIGH_RISK_RESECTABLE_T_STAGES = {"T2b", "T3a", "T3b", "T4a", "T4b"}


@dataclass
class TrialRule:
    nct_id: str
    title: str
    phase: str
    setting: str  # plain-English one-liner for UI
    requires_advanced_disease: bool = False
    requires_resectable_high_risk: bool = False
    requires_braf_v600: bool | None = None  # None = irrelevant to eligibility
    unknown_gates: list[str] = field(default_factory=list)  # always-unknown fields


REGENERON_TRIALS: dict[str, TrialRule] = {
    "NCT05352672": TrialRule(
        nct_id="NCT05352672",
        title="Harmony Melanoma — fianlimab + cemiplimab vs pembrolizumab",
        phase="Phase 3",
        setting="1L unresectable Stage III / Stage IV melanoma",
        requires_advanced_disease=True,
        unknown_gates=[
            "Age ≥ 12 years",
            "ECOG 0–1 (or Karnofsky ≥ 70)",
            "No prior systemic therapy for advanced disease (≥ 6 mo washout if adjuvant)",
            "Measurable disease per RECIST 1.1",
            "LAG-3 expression result available",
            "Life expectancy ≥ 3 months",
        ],
    ),
    "NCT06246916": TrialRule(
        nct_id="NCT06246916",
        title="Harmony Head-to-Head — fianlimab + cemiplimab vs nivo + relatlimab",
        phase="Phase 3",
        setting="1L unresectable Stage III / Stage IV melanoma",
        requires_advanced_disease=True,
        unknown_gates=[
            "Age ≥ 18 years",
            "ECOG 0–1",
            "No prior systemic therapy for advanced disease",
            "Measurable disease per RECIST 1.1",
            "LAG-3 expression result available",
        ],
    ),
    "NCT06190951": TrialRule(
        nct_id="NCT06190951",
        title="Neoadjuvant fianlimab + cemiplimab in high-risk resectable melanoma",
        phase="Phase 2",
        setting="High-risk clinically-detectable Stage II/III, surgically resectable",
        requires_resectable_high_risk=True,
        unknown_gates=[
            "Age ≥ 12 years",
            "ECOG 0–1",
            "Clinically-detectable, surgically resectable disease",
            "No prior immunotherapy for melanoma",
        ],
    ),
    "NCT04526899": TrialRule(
        nct_id="NCT04526899",
        title="BNT111 + Libtayo (cemiplimab) — fixed-antigen mRNA vaccine combination",
        phase="Phase 2",
        setting="Anti-PD-1-refractory / relapsed unresectable Stage III or IV melanoma",
        requires_advanced_disease=True,
        unknown_gates=[
            "Age ≥ 18 years",
            "Prior anti-PD-1 therapy (progression on or after)",
            "Measurable disease per RECIST 1.1",
            "ECOG 0–1",
        ],
    ),
}


# ─────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────


def _has_braf_v600(case: MelanomaCase) -> bool:
    return any(
        m.gene.upper() == "BRAF" and m.position == 600 and m.alt_aa.upper() == "E"
        for m in case.mutations
    )


def _advanced_verdict(case: MelanomaCase) -> tuple[str, str]:
    """Return (verdict, criterion_text) where verdict is 'pass' | 'fail' | 'unknown'."""
    t = case.pathology.t_stage
    label = f"Locally advanced disease (T-stage: {t})"
    if t == "Tx":
        return "unknown", label
    if t in ADVANCED_T_STAGES:
        return "pass", label
    # T1–T2 → we can't rule out Stage III/IV from nodes/mets, so say unknown.
    return "unknown", label


def _resectable_high_risk_verdict(case: MelanomaCase) -> tuple[str, str]:
    t = case.pathology.t_stage
    label = f"High-risk resectable (T-stage: {t})"
    if t == "Tx":
        return "unknown", label
    if t in HIGH_RISK_RESECTABLE_T_STAGES:
        return "pass", label
    return "fail", label


def evaluate(case: MelanomaCase, rule: TrialRule) -> TrialMatch:
    """Apply `rule` to `case` and return a `TrialMatch` verdict."""
    passing: list[str] = []
    failing: list[str] = []
    unknown: list[str] = list(rule.unknown_gates)

    if rule.requires_advanced_disease:
        verdict, crit = _advanced_verdict(case)
        (passing if verdict == "pass" else unknown if verdict == "unknown" else failing).append(crit)

    if rule.requires_resectable_high_risk:
        verdict, crit = _resectable_high_risk_verdict(case)
        (passing if verdict == "pass" else unknown if verdict == "unknown" else failing).append(crit)

    if rule.requires_braf_v600 is True:
        crit = "BRAF V600 mutation present"
        (passing if _has_braf_v600(case) else failing).append(crit)
    elif rule.requires_braf_v600 is False:
        crit = "No BRAF V600 mutation (BRAF-wildtype arm)"
        (failing if _has_braf_v600(case) else passing).append(crit)

    if failing:
        status: str = "ineligible"
    elif unknown:
        status = "needs_more_data"
    else:
        status = "eligible"

    return TrialMatch(
        nct_id=rule.nct_id,
        title=rule.title,
        sponsor="Regeneron Pharmaceuticals",
        phase=rule.phase,
        status=status,  # type: ignore[arg-type]
        passing_criteria=passing,
        failing_criteria=failing,
        unknown_criteria=unknown,
        is_regeneron=True,
        url=f"https://clinicaltrials.gov/study/{rule.nct_id}",
    )
