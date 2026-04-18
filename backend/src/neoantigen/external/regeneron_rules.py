"""Regeneron melanoma trial registry + structured eligibility predicates.

Four trials (checked April 2026):
  NCT05352672 — Harmony Melanoma (Phase 3, 1L advanced, fianlimab + cemiplimab vs pembro)
  NCT06246916 — Harmony Head-to-Head (Phase 3, 1L advanced, vs nivo + rela)
  NCT06190951 — Neoadjuvant Phase 2 (fianlimab + cemiplimab, high-risk resectable)
  NCT04526899 — BNT111 + Libtayo (BioNTech partnership, fixed-antigen vaccine + PD-1)

Predicates are split into three buckets:

  * Structured gates resolved from a ``MelanomaCase`` + optional
    ``TCGAPatient`` clinical record: age, AJCC stage bucket, T-stage,
    driver mutations.
  * Structured predicates resolved from :class:`ClinicianIntake` (primary
    source) + :class:`EnrichedBiomarkers` (fallback for prior-therapy when
    cBioPortal yielded a hit): ECOG, prior systemic therapy, prior
    anti-PD-1, RECIST measurability, LAG-3 IHC, life expectancy.
  * ``never_in_tcga_gates``: text labels for criteria that still lack a
    structured predicate. These always land in ``unknown_criteria``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..cohort.tcga import TCGAPatient
from ..models import ClinicianIntake, EnrichedBiomarkers, MelanomaCase, TrialMatch


# AJCC 8 T-stage buckets that suggest locally-advanced or high-risk disease.
# Used as a (necessary-but-not-sufficient) proxy for "advanced" when we only
# have pathology (no nodes / mets assessment).
ADVANCED_T_STAGES = {"T3a", "T3b", "T4a", "T4b"}
HIGH_RISK_RESECTABLE_T_STAGES = {"T2b", "T3a", "T3b", "T4a", "T4b"}

# BNT111 (NCT04526899) is a fixed-antigen vaccine targeting these four shared
# melanoma antigens. Patients whose personalised neoantigens include any of
# them are combination candidates — surfaced as a *bonus* passing criterion,
# not a hard eligibility gate.
BNT111_ANTIGENS: frozenset[str] = frozenset({"TYR", "MAGEA3", "CTAG1B", "TPTE"})


@dataclass
class TrialRule:
    nct_id: str
    title: str
    phase: str
    setting: str
    # Case/TCGA-resolved gates
    requires_advanced_disease: bool = False
    requires_resectable_high_risk: bool = False
    requires_braf_v600: bool | None = None
    min_age_years: int | None = None
    eligible_stage_buckets: set[str] = field(default_factory=set)
    # Intake + enrichment-resolved gates
    requires_ecog_0_1: bool = False
    requires_no_prior_systemic_advanced: bool = False
    requires_prior_anti_pd1: bool = False
    requires_measurable_disease: bool = False
    requires_lag3_ihc_result: bool = False
    min_life_expectancy_months: int | None = None
    # BNT111 bonus (overlap → added to passing_criteria)
    surfaces_bnt111_antigen_overlap: bool = False
    # Residual free-text gates
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
        surfaces_bnt111_antigen_overlap=True,
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


def bnt111_overlap_genes(case: MelanomaCase) -> list[str]:
    """Genes in the candidate peptide list that are in the BNT111 antigen set."""
    if case.pipeline is None:
        return []
    return sorted({
        c.peptide.mutation.gene.upper()
        for c in case.pipeline.candidates
        if c.peptide.mutation.gene.upper() in BNT111_ANTIGENS
    })


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


def _ecog_verdict(intake: ClinicianIntake | None) -> tuple[str, str]:
    if intake is None or intake.ecog is None:
        return "unknown", "ECOG 0–1"
    verdict = "pass" if intake.ecog <= 1 else "fail"
    return verdict, f"ECOG {intake.ecog} (clinician intake)"


def _no_prior_systemic_verdict(
    intake: ClinicianIntake | None, enrichment: EnrichedBiomarkers | None
) -> tuple[str, str]:
    prior = _resolve_prior_systemic(intake, enrichment)
    if prior is None:
        return "unknown", "No prior systemic therapy for advanced disease"
    if prior:
        src = "clinician intake" if intake and intake.prior_systemic_therapy is not None else "cBioPortal"
        return "fail", f"Prior systemic therapy recorded ({src})"
    return "pass", "No prior systemic therapy for advanced disease"


def _prior_pd1_verdict(
    intake: ClinicianIntake | None, enrichment: EnrichedBiomarkers | None
) -> tuple[str, str]:
    pd1 = _resolve_prior_pd1(intake, enrichment)
    if pd1 is None:
        return "unknown", "Prior anti-PD-1 therapy (progression on or after)"
    if pd1:
        return "pass", "Prior anti-PD-1 therapy confirmed"
    return "fail", "No prior anti-PD-1 therapy"


def _measurable_verdict(intake: ClinicianIntake | None) -> tuple[str, str]:
    if intake is None or intake.measurable_disease_recist is None:
        return "unknown", "Measurable disease per RECIST 1.1"
    if intake.measurable_disease_recist:
        return "pass", "Measurable disease per RECIST 1.1 (clinician)"
    return "fail", "No measurable disease per RECIST 1.1"


def _lag3_verdict(intake: ClinicianIntake | None) -> tuple[str, str]:
    if intake is None or intake.lag3_ihc_percent is None:
        return "unknown", "LAG-3 IHC expression result available"
    return "pass", f"LAG-3 IHC {intake.lag3_ihc_percent:.0f}% (clinician)"


def _life_expectancy_verdict(intake: ClinicianIntake | None, min_months: int) -> tuple[str, str]:
    if intake is None or intake.life_expectancy_months is None:
        return "unknown", f"Life expectancy ≥ {min_months} months"
    if intake.life_expectancy_months >= min_months:
        return "pass", f"Life expectancy {intake.life_expectancy_months} mo ≥ {min_months}"
    return "fail", f"Life expectancy {intake.life_expectancy_months} mo < {min_months}"


def _resolve_prior_systemic(
    intake: ClinicianIntake | None, enrichment: EnrichedBiomarkers | None
) -> bool | None:
    if intake is not None and intake.prior_systemic_therapy is not None:
        return intake.prior_systemic_therapy
    if enrichment is not None and enrichment.prior_systemic_therapies:
        return True
    return None


def _resolve_prior_pd1(
    intake: ClinicianIntake | None, enrichment: EnrichedBiomarkers | None
) -> bool | None:
    if intake is not None and intake.prior_anti_pd1 is not None:
        return intake.prior_anti_pd1
    if enrichment is not None and enrichment.prior_anti_pd1 is not None:
        return enrichment.prior_anti_pd1
    return None


# ─────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────


def evaluate(
    case: MelanomaCase,
    rule: TrialRule,
    tcga: TCGAPatient | None = None,
    intake: ClinicianIntake | None = None,
    enrichment: EnrichedBiomarkers | None = None,
) -> TrialMatch:
    """Apply `rule` to `case`, refined by optional TCGA/intake/enrichment data."""
    # Backwards-compat: if the caller didn't pass intake/enrichment, pull
    # them off the case (orchestrator attaches them there).
    if intake is None:
        intake = case.intake
    if enrichment is None:
        enrichment = case.enrichment

    passing: list[str] = []
    failing: list[str] = []
    unknown: list[str] = []

    def _record(v: tuple[str, str]) -> None:
        verdict, label = v
        (passing if verdict == "pass" else failing if verdict == "fail" else unknown).append(label)

    # Pathology / T-stage
    if rule.requires_advanced_disease:
        _record(_advanced_verdict(case))
    if rule.requires_resectable_high_risk:
        _record(_resectable_high_risk_verdict(case))

    # TCGA clinical
    if rule.min_age_years is not None:
        _record(_age_verdict(tcga, rule.min_age_years))
    if rule.eligible_stage_buckets:
        _record(_stage_verdict(tcga, rule.eligible_stage_buckets))

    # BRAF driver
    if rule.requires_braf_v600 is True:
        label = "BRAF V600 mutation present"
        (passing if _has_braf_v600(case) else failing).append(label)
    elif rule.requires_braf_v600 is False:
        label = "No BRAF V600 mutation (BRAF-wildtype arm)"
        (failing if _has_braf_v600(case) else passing).append(label)

    # Intake + enrichment predicates
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

    # BNT111 bonus — overlap surfaces as a passing criterion when any shared
    # antigen is in the personalised peptide list. Never a gate.
    if rule.surfaces_bnt111_antigen_overlap:
        overlap = bnt111_overlap_genes(case)
        if overlap:
            passing.append(
                "Neoantigens overlap BNT111 shared-antigen set: " + ", ".join(overlap)
            )

    # Residual free-text gates
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
