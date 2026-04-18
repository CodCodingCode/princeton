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
    max_age_years: int | None = None
    eligible_stage_buckets: set[str] = field(default_factory=set)
    requires_ecog_0_1: bool = False
    requires_no_prior_systemic_advanced: bool = False
    requires_prior_anti_pd1: bool = False
    requires_measurable_disease: bool = False
    requires_lag3_ihc_result: bool = False
    min_life_expectancy_months: int | None = None
    never_in_tcga_gates: list[str] = field(default_factory=list)

    # Multi-cancer routing + biomarker gates (added for the cancer-agnostic pivot).
    cancer_types: frozenset[str] = field(default_factory=frozenset)
    # Supported biomarker_gates keys: BRAF_V600, EGFR_mutation, EGFR_T790M,
    # ALK_fusion, ROS1_fusion, MET_exon14, KRAS_G12C, HER2_positive, HER2_low,
    # BRCA_mutation, MSI_high, PDL1_positive. Values: "required" | "excluded" | "any".
    biomarker_gates: dict[str, str] = field(default_factory=dict)
    pdl1_min_tps: int | None = None
    scraped_at: str = ""                  # ISO date the scraper wrote this record
    raw_source: str = "ClinicalTrials.gov v2"


def _load_trials() -> dict[str, TrialRule]:
    """Import the per-trial registry from the ``regeneron`` subpackage.

    Each trial lives in its own ``nct<id>.py`` file under
    ``external/regeneron/``. Regenerate with
    ``scripts/scrape_regeneron_trials.py``.
    """
    from .regeneron import REGENERON_TRIALS as _loaded
    return _loaded


REGENERON_TRIALS: dict[str, TrialRule] = _load_trials()


def _has_braf_v600(case: PatientCase) -> bool:
    return any(
        m.gene.upper() == "BRAF" and m.position == 600 and m.alt_aa.upper() == "E"
        for m in case.mutations
    )


# ─────────────────────────────────────────────────────────────
# Biomarker gate resolvers — one per supported key. Each returns
# (verdict, label) where verdict ∈ {"pass","fail","unknown"}.
# Verdict is with respect to the `required` flag:
#   required=True  → pass if biomarker present
#   required=False → pass if biomarker absent  (for "excluded" gates)
# ─────────────────────────────────────────────────────────────


def _gene_present(case: PatientCase, gene: str) -> bool:
    return any(m.gene.upper() == gene.upper() for m in case.mutations)


def _mutation_text_match(case: PatientCase, pattern: str) -> bool:
    """Scan raw mutation text strings captured per-page."""
    needle = pattern.lower()
    for doc in case.documents:
        for page in doc.pages:
            for mtxt in page.mutations_text:
                if needle in mtxt.lower():
                    return True
    return False


def _gate_braf_v600(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = _has_braf_v600(case)
    label = "BRAF V600 mutation"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_egfr_mutation(case: PatientCase, *, required: bool) -> tuple[str, str]:
    # EGFR in structured mutations list (covers L858R etc.) OR free-text
    # "exon 19 del" / "exon 19 deletion" / "exon 20 ins" on any page.
    present = (
        _gene_present(case, "EGFR")
        or _mutation_text_match(case, "egfr exon 19")
        or _mutation_text_match(case, "egfr exon 20")
        or _mutation_text_match(case, "egfr l858r")
    )
    label = "EGFR activating mutation"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_egfr_t790m(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = any(
        m.gene.upper() == "EGFR" and m.position == 790 and m.alt_aa.upper() == "M"
        for m in case.mutations
    ) or _mutation_text_match(case, "t790m")
    label = "EGFR T790M"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_alk_fusion(case: PatientCase, *, required: bool) -> tuple[str, str]:
    # Fusions rarely appear as a clean AA change — rely on text and gene presence.
    present = (
        _gene_present(case, "ALK")
        or _mutation_text_match(case, "alk fusion")
        or _mutation_text_match(case, "alk rearrangement")
        or _mutation_text_match(case, "eml4-alk")
    )
    label = "ALK fusion / rearrangement"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_ros1_fusion(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _gene_present(case, "ROS1")
        or _mutation_text_match(case, "ros1 fusion")
        or _mutation_text_match(case, "ros1 rearrangement")
    )
    label = "ROS1 fusion / rearrangement"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_met_exon14(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _mutation_text_match(case, "met exon 14")
        or _mutation_text_match(case, "metex14")
    )
    label = "MET exon 14 skipping"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_kras_g12c(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = any(
        m.gene.upper() == "KRAS" and m.position == 12 and m.alt_aa.upper() == "C"
        for m in case.mutations
    )
    label = "KRAS G12C"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_her2_positive(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _mutation_text_match(case, "her2 amplification")
        or _mutation_text_match(case, "her2 positive")
        or _mutation_text_match(case, "erbb2 amplification")
    )
    label = "HER2 positive (amplified / 3+)"
    # When absent we can't tell whether the test was simply not done — return unknown.
    if not present:
        return ("unknown", f"{label} (status not extracted)")
    return ("pass" if required else "fail", label)


def _gate_her2_low(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _mutation_text_match(case, "her2 low")
        or _mutation_text_match(case, "her2 1+")
        or _mutation_text_match(case, "her2 2+")
    )
    label = "HER2 low (IHC 1+/2+, ISH non-amplified)"
    if not present:
        return ("unknown", f"{label} (status not extracted)")
    return ("pass" if required else "fail", label)


def _gate_brca_mutation(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _gene_present(case, "BRCA1")
        or _gene_present(case, "BRCA2")
        or _mutation_text_match(case, "brca1")
        or _mutation_text_match(case, "brca2")
    )
    label = "BRCA1/2 pathogenic variant"
    return ("pass" if present == required else "fail", f"{label} ({'present' if present else 'absent'})")


def _gate_msi_high(case: PatientCase, *, required: bool) -> tuple[str, str]:
    present = (
        _mutation_text_match(case, "msi-h")
        or _mutation_text_match(case, "msi high")
        or _mutation_text_match(case, "mmr-deficient")
        or _mutation_text_match(case, "dmmr")
    )
    label = "MSI-H / dMMR"
    if not present:
        return ("unknown", f"{label} (status not extracted)")
    return ("pass" if required else "fail", label)


def _gate_pdl1_positive(case: PatientCase, *, required: bool) -> tuple[str, str]:
    level = (case.pathology.pdl1_estimate or "unknown").lower()
    label = f"PD-L1 expression ({level})"
    if level == "unknown":
        return ("unknown", label)
    positive = level in {"low", "high"}
    return ("pass" if positive == required else "fail", label)


def _pdl1_min_tps_gate(case: PatientCase, min_tps: int) -> tuple[str, str]:
    """Numeric PD-L1 threshold. We only have a coarse {negative/low/high} bucket,
    so we map conservatively: high → TPS≥50, low → TPS≥1, negative → TPS<1."""
    level = (case.pathology.pdl1_estimate or "unknown").lower()
    label = f"PD-L1 TPS ≥ {min_tps}% (extracted bucket: {level})"
    if level == "unknown":
        return ("unknown", label)
    if level == "high":
        return ("pass" if min_tps <= 50 else "unknown", label)
    if level == "low":
        return ("pass" if min_tps <= 49 else "fail", label)
    return ("fail", label)


_BIOMARKER_RESOLVERS = {
    "BRAF_V600": _gate_braf_v600,
    "EGFR_mutation": _gate_egfr_mutation,
    "EGFR_T790M": _gate_egfr_t790m,
    "ALK_fusion": _gate_alk_fusion,
    "ROS1_fusion": _gate_ros1_fusion,
    "MET_exon14": _gate_met_exon14,
    "KRAS_G12C": _gate_kras_g12c,
    "HER2_positive": _gate_her2_positive,
    "HER2_low": _gate_her2_low,
    "BRCA_mutation": _gate_brca_mutation,
    "MSI_high": _gate_msi_high,
    "PDL1_positive": _gate_pdl1_positive,
}


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

    if rule.max_age_years is not None and intake.age_years is not None:
        if intake.age_years <= rule.max_age_years:
            passing.append(f"Age {intake.age_years} ≤ {rule.max_age_years}")
        else:
            failing.append(f"Age {intake.age_years} > {rule.max_age_years}")

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

    # Biomarker gates — dispatch via the resolver table. "any" is a no-op;
    # "required" / "excluded" resolve through their gate function.
    for key, mode in rule.biomarker_gates.items():
        if mode == "any":
            continue
        resolver = _BIOMARKER_RESOLVERS.get(key)
        if resolver is None:
            unknown.append(f"Biomarker gate {key}={mode} (resolver not implemented)")
            continue
        _record(resolver(case, required=(mode == "required")))

    if rule.pdl1_min_tps is not None:
        _record(_pdl1_min_tps_gate(case, rule.pdl1_min_tps))

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
    """Run every Regeneron rule against a case, returning ranked matches.

    Pre-filters trials by ``case.primary_cancer_type`` — a lung case only
    evaluates lung-bucketed trials. ``cancer_types`` is treated as a wildcard
    when empty (basket trials, unscoped legacy rules) or when the case's
    primary cancer type is ``unknown`` (let the predicate verdicts decide).
    """
    ct = (case.primary_cancer_type or "unknown").strip()
    matches: list[TrialMatch] = []
    for rule in REGENERON_TRIALS.values():
        if rule.cancer_types and ct != "unknown" and ct not in rule.cancer_types:
            continue
        matches.append(evaluate(case, rule))
    status_order = {"eligible": 0, "needs_more_data": 1, "ineligible": 2, "unscored": 3}
    matches.sort(key=lambda m: (status_order.get(m.status, 9), m.nct_id))
    return matches
