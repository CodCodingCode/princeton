"""Regeneron melanoma trial registry + structured eligibility predicates.

Four trials (checked April 2026):
  NCT05352672 — Harmony Melanoma (Phase 3, 1L advanced, fianlimab + cemiplimab vs pembro)
  NCT06246916 — Harmony Head-to-Head (Phase 3, 1L advanced, vs nivo + rela)
  NCT06190951 — Neoadjuvant Phase 2 (fianlimab + cemiplimab, high-risk resectable)
  NCT04526899 — BNT111 + Libtayo (BioNTech partnership, fixed-antigen vaccine + PD-1)

Predicates resolve from a :class:`PatientCase` — its `pathology`, `intake`,
`enrichment`, and `mutations`. Unresolvable gates land in ``unknown_criteria``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    ClinicianIntake,
    EnrichedBiomarkers,
    PatientCase,
    TrialMatch,
)


ADVANCED_T_STAGES = {"T3a", "T3b", "T4a", "T4b"}
HIGH_RISK_RESECTABLE_T_STAGES = {"T2b", "T3a", "T3b", "T4a", "T4b"}


@dataclass
class TrialRule:
    nct_id: str
    title: str
    phase: str
    setting: str
    requires_advanced_disease: bool = False
    requires_resectable_high_risk: bool = False
    requires_braf_v600: bool | None = None
    min_age_years: int | None = None
    eligible_stage_buckets: set[str] = field(default_factory=set)
    requires_ecog_0_1: bool = False
    requires_no_prior_systemic_advanced: bool = False
    requires_prior_anti_pd1: bool = False
    requires_measurable_disease: bool = False
    requires_lag3_ihc_result: bool = False
    min_life_expectancy_months: int | None = None
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
        requires_ecog_0_1=True,
        requires_no_prior_systemic_advanced=True,
        requires_measurable_disease=True,
        requires_lag3_ihc_result=True,
        min_life_expectancy_months=3,
    ),
    "NCT06246916": TrialRule(
        nct_id="NCT06246916",
        title="Harmony Head-to-Head — fianlimab + cemiplimab vs nivo + relatlimab",
        phase="Phase 3",
        setting="1L unresectable Stage III / Stage IV melanoma",
        requires_advanced_disease=True,
        min_age_years=18,
        eligible_stage_buckets={"III", "IV"},
        requires_ecog_0_1=True,
        requires_no_prior_systemic_advanced=True,
        requires_measurable_disease=True,
        requires_lag3_ihc_result=True,
    ),
    "NCT06190951": TrialRule(
        nct_id="NCT06190951",
        title="Neoadjuvant fianlimab + cemiplimab in high-risk resectable melanoma",
        phase="Phase 2",
        setting="High-risk clinically-detectable Stage II/III, surgically resectable",
        requires_resectable_high_risk=True,
        min_age_years=12,
        eligible_stage_buckets={"II", "III"},
        requires_ecog_0_1=True,
        never_in_tcga_gates=[
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
        requires_ecog_0_1=True,
        requires_prior_anti_pd1=True,
        requires_measurable_disease=True,
    ),
}


def _has_braf_v600(case: PatientCase) -> bool:
    return any(
        m.gene.upper() == "BRAF" and m.position == 600 and m.alt_aa.upper() == "E"
        for m in case.mutations
    )


def _stage_bucket(intake: ClinicianIntake) -> str | None:
    stage = (intake.ajcc_stage or "").strip().upper()
    if not stage:
        return None
    for bucket in ("IV", "III", "II", "I"):
        if stage.startswith(bucket):
            return bucket
    return None


def _advanced_verdict(case: PatientCase) -> tuple[str, str]:
    t = case.pathology.t_stage
    bucket = _stage_bucket(case.intake)
    label = f"Advanced disease (T-stage {t}, AJCC {case.intake.ajcc_stage or 'unknown'})"
    if bucket in {"III", "IV"}:
        return "pass", label
    if t in ADVANCED_T_STAGES:
        return "pass", label
    if t == "Tx" and bucket is None:
        return "unknown", label
    return "unknown", label


def _resectable_high_risk_verdict(case: PatientCase) -> tuple[str, str]:
    t = case.pathology.t_stage
    label = f"High-risk resectable per T-stage ({t})"
    if t == "Tx":
        return "unknown", label
    if t in HIGH_RISK_RESECTABLE_T_STAGES:
        return "pass", label
    return "fail", label


def _age_verdict(intake: ClinicianIntake, min_age: int) -> tuple[str, str]:
    if intake.age_years is None:
        return "unknown", f"Age ≥ {min_age} years"
    return (
        "pass" if intake.age_years >= min_age else "fail",
        f"Age {intake.age_years} {'≥' if intake.age_years >= min_age else '<'} {min_age}",
    )


def _stage_verdict(intake: ClinicianIntake, eligible: set[str]) -> tuple[str, str]:
    pretty = "/".join(sorted(eligible))
    bucket = _stage_bucket(intake)
    if bucket is None:
        return "unknown", f"AJCC stage in {{{pretty}}}"
    label = f"AJCC {intake.ajcc_stage} ∈ {{{pretty}}}"
    return ("pass" if bucket in eligible else "fail", label)


def _ecog_verdict(intake: ClinicianIntake) -> tuple[str, str]:
    if intake.ecog is None:
        return "unknown", "ECOG 0–1"
    verdict = "pass" if intake.ecog <= 1 else "fail"
    return verdict, f"ECOG {intake.ecog}"


def _resolve_prior_systemic(
    intake: ClinicianIntake, enrichment: EnrichedBiomarkers | None
) -> bool | None:
    if intake.prior_systemic_therapy is not None:
        return intake.prior_systemic_therapy
    if enrichment is not None and enrichment.prior_systemic_therapies:
        return True
    return None


def _resolve_prior_pd1(
    intake: ClinicianIntake, enrichment: EnrichedBiomarkers | None
) -> bool | None:
    if intake.prior_anti_pd1 is not None:
        return intake.prior_anti_pd1
    if enrichment is not None and enrichment.prior_anti_pd1 is not None:
        return enrichment.prior_anti_pd1
    return None


def _no_prior_systemic_verdict(
    intake: ClinicianIntake, enrichment: EnrichedBiomarkers | None
) -> tuple[str, str]:
    prior = _resolve_prior_systemic(intake, enrichment)
    if prior is None:
        return "unknown", "No prior systemic therapy for advanced disease"
    if prior:
        return "fail", "Prior systemic therapy recorded"
    return "pass", "No prior systemic therapy for advanced disease"


def _prior_pd1_verdict(
    intake: ClinicianIntake, enrichment: EnrichedBiomarkers | None
) -> tuple[str, str]:
    pd1 = _resolve_prior_pd1(intake, enrichment)
    if pd1 is None:
        return "unknown", "Prior anti-PD-1 therapy (progression on or after)"
    if pd1:
        return "pass", "Prior anti-PD-1 therapy confirmed"
    return "fail", "No prior anti-PD-1 therapy"


def _measurable_verdict(intake: ClinicianIntake) -> tuple[str, str]:
    if intake.measurable_disease_recist is None:
        return "unknown", "Measurable disease per RECIST 1.1"
    if intake.measurable_disease_recist:
        return "pass", "Measurable disease per RECIST 1.1"
    return "fail", "No measurable disease per RECIST 1.1"


def _lag3_verdict(intake: ClinicianIntake) -> tuple[str, str]:
    if intake.lag3_ihc_percent is None:
        return "unknown", "LAG-3 IHC expression result available"
    return "pass", f"LAG-3 IHC {intake.lag3_ihc_percent:.0f}%"


def _life_expectancy_verdict(intake: ClinicianIntake, min_months: int) -> tuple[str, str]:
    if intake.life_expectancy_months is None:
        return "unknown", f"Life expectancy ≥ {min_months} months"
    if intake.life_expectancy_months >= min_months:
        return "pass", f"Life expectancy {intake.life_expectancy_months} mo ≥ {min_months}"
    return "fail", f"Life expectancy {intake.life_expectancy_months} mo < {min_months}"


def evaluate(case: PatientCase, rule: TrialRule) -> TrialMatch:
    """Apply `rule` to `case`, resolving structured + intake/enrichment gates."""
    intake = case.intake
    enrichment = case.enrichment

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
        _record(_age_verdict(intake, rule.min_age_years))
    if rule.eligible_stage_buckets:
        _record(_stage_verdict(intake, rule.eligible_stage_buckets))

    if rule.requires_braf_v600 is True:
        label = "BRAF V600 mutation present"
        (passing if _has_braf_v600(case) else failing).append(label)
    elif rule.requires_braf_v600 is False:
        label = "No BRAF V600 mutation (BRAF-wildtype arm)"
        (failing if _has_braf_v600(case) else passing).append(label)

    if rule.requires_ecog_0_1:
        _record(_ecog_verdict(intake))
    if rule.requires_no_prior_systemic_advanced:
        _record(_no_prior_systemic_verdict(intake, enrichment))
    if rule.requires_prior_anti_pd1:
        _record(_prior_pd1_verdict(intake, enrichment))
    if rule.requires_measurable_disease:
        _record(_measurable_verdict(intake))
    if rule.requires_lag3_ihc_result:
        _record(_lag3_verdict(intake))
    if rule.min_life_expectancy_months is not None:
        _record(_life_expectancy_verdict(intake, rule.min_life_expectancy_months))

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


def evaluate_all(case: PatientCase) -> list[TrialMatch]:
    """Run every Regeneron rule against a case, returning ranked matches."""
    matches = [evaluate(case, rule) for rule in REGENERON_TRIALS.values()]
    status_order = {"eligible": 0, "needs_more_data": 1, "ineligible": 2, "unscored": 3}
    matches.sort(key=lambda m: (status_order.get(m.status, 9), m.nct_id))
    return matches
