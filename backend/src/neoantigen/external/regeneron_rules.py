"""Regeneron melanoma trial registry + structured eligibility predicates.

Four trials (checked April 2026):
  NCT05352672 — Harmony Melanoma (Phase 3, 1L advanced, fianlimab + cemiplimab vs pembro)
  NCT06246916 — Harmony Head-to-Head (Phase 3, 1L advanced, vs nivo + rela)
  NCT06190951 — Neoadjuvant Phase 2 (fianlimab + cemiplimab, high-risk resectable)
  NCT04526899 — BNT111 + Libtayo (BioNTech partnership, fixed-antigen vaccine + PD-1)

Predicates are split into two buckets:
  * structured gates we CAN resolve from a `MelanomaCase` + (optional) TCGA
    clinical record: age, AJCC stage bucket, T-stage, driver mutations.
  * `never_in_tcga_gates`: things TCGA does not record (ECOG, prior systemic
    therapy, LAG-3 IHC, RECIST measurability). These stay as
    `unknown_criteria` — the UI surfaces them as "clinician to verify".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..cohort.tcga import TCGAPatient
from ..models import MelanomaCase, TrialMatch


# AJCC 8 T-stage buckets that suggest locally-advanced or high-risk disease.
# Used as a (necessary-but-not-sufficient) proxy for "advanced" when we only
# have pathology (no nodes / mets assessment).
ADVANCED_T_STAGES = {"T3a", "T3b", "T4a", "T4b"}
HIGH_RISK_RESECTABLE_T_STAGES = {"T2b", "T3a", "T3b", "T4a", "T4b"}


@dataclass
class TrialRule:
    nct_id: str
    title: str
    phase: str
    setting: str
    # Structured gates resolved from MelanomaCase + TCGAPatient
    requires_advanced_disease: bool = False
    requires_resectable_high_risk: bool = False
    requires_braf_v600: bool | None = None
    min_age_years: int | None = None
    eligible_stage_buckets: set[str] = field(default_factory=set)
    # Always unknown from our data (clinician verifies at enrollment)
    never_in_tcga_gates: list[str] = field(default_factory=list)


REGENERON_TRIALS: dict[str, TrialRule] = {
    "NCT05352672": TrialRule(
        nct_id="NCT05352672",
        title="Harmony Melanoma — fianlimab + cemiplimab vs pembrolizumab",
        phase="Phase 3",
        setting="1L unresectable Stage III / Stage IV melanoma",
        requires_advanced_disease=True,
        min_age_years=12,
        eligible_stage_buckets={"III", "IV"},
        never_in_tcga_gates=[
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
        min_age_years=18,
        eligible_stage_buckets={"III", "IV"},
        never_in_tcga_gates=[
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
        min_age_years=12,
        eligible_stage_buckets={"II", "III"},
        never_in_tcga_gates=[
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
        min_age_years=18,
        eligible_stage_buckets={"III", "IV"},
        never_in_tcga_gates=[
            "Prior anti-PD-1 therapy (progression on or after)",
            "Measurable disease per RECIST 1.1",
            "ECOG 0–1",
        ],
    ),
}


# ─────────────────────────────────────────────────────────────
# Derivers
# ─────────────────────────────────────────────────────────────


def _has_braf_v600(case: MelanomaCase) -> bool:
    return any(
        m.gene.upper() == "BRAF" and m.position == 600 and m.alt_aa.upper() == "E"
        for m in case.mutations
    )


def _advanced_verdict(case: MelanomaCase) -> tuple[str, str]:
    t = case.pathology.t_stage
    label = f"Advanced disease per T-stage ({t})"
    if t == "Tx":
        return "unknown", label
    if t in ADVANCED_T_STAGES:
        return "pass", label
    return "unknown", label  # T1–T2 can still be stage III/IV via nodes/mets


def _resectable_high_risk_verdict(case: MelanomaCase) -> tuple[str, str]:
    t = case.pathology.t_stage
    label = f"High-risk resectable per T-stage ({t})"
    if t == "Tx":
        return "unknown", label
    if t in HIGH_RISK_RESECTABLE_T_STAGES:
        return "pass", label
    return "fail", label


def _age_verdict(tcga: TCGAPatient | None, min_age: int) -> tuple[str, str]:
    if tcga is None or tcga.age_at_diagnosis is None:
        return "unknown", f"Age ≥ {min_age} years"
    age = tcga.age_at_diagnosis
    label = f"Age {age} ≥ {min_age} (TCGA clinical record)"
    return ("pass" if age >= min_age else "fail", label)


def _stage_verdict(tcga: TCGAPatient | None, eligible: set[str]) -> tuple[str, str]:
    pretty = "/".join(sorted(eligible))
    if tcga is None:
        return "unknown", f"AJCC stage in {{{pretty}}}"
    bucket = tcga.stage_bucket
    if bucket == "Unknown":
        return "unknown", f"AJCC stage in {{{pretty}}} (TCGA record: stage not listed)"
    label = f"AJCC stage {bucket} (TCGA clinical record) ∈ {{{pretty}}}"
    return ("pass" if bucket in eligible else "fail", label)


# ─────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────


def evaluate(
    case: MelanomaCase,
    rule: TrialRule,
    tcga: TCGAPatient | None = None,
) -> TrialMatch:
    """Apply `rule` to `case`, optionally refined by a TCGA clinical record."""
    passing: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []

    def _record(v: tuple[str, str]) -> None:
        verdict, label = v
        (passing if verdict == "pass" else failing if verdict == "fail" else unknown).append(label)

    if rule.requires_advanced_disease:
        _record(_advanced_verdict(case))
    if rule.requires_resectable_high_risk:
        _record(_resectable_high_risk_verdict(case))

    if rule.min_age_years is not None:
        _record(_age_verdict(tcga, rule.min_age_years))

    if rule.eligible_stage_buckets:
        _record(_stage_verdict(tcga, rule.eligible_stage_buckets))

    if rule.requires_braf_v600 is True:
        label = "BRAF V600 mutation present"
        (passing if _has_braf_v600(case) else failing).append(label)
    elif rule.requires_braf_v600 is False:
        label = "No BRAF V600 mutation (BRAF-wildtype arm)"
        (failing if _has_braf_v600(case) else passing).append(label)

    for gate in rule.never_in_tcga_gates:
        unknown.append(gate)

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
