"""Hand-curated ``ClinicianIntake`` for a small set of TCGA-SKCM demo patients.

GDC's open-access SKCM clinical export doesn't carry ECOG, LAG-3 IHC,
RECIST measurability, life expectancy, or prior-therapy fields. Without
them every Regeneron trial rulebook lands in ``needs_more_data``. For
hackathon demos we hand-author those fields for three submitter ids
so the trial matcher produces real Eligible / Ineligible verdicts
covering each Regeneron arm:

  * TCGA-D3-A3MR — Harmony Melanoma + Harmony H2H candidate (BRAF V600E, III)
  * TCGA-EE-A2MI — Neoadjuvant Phase 2 candidate (stage IIB, resectable)
  * TCGA-FS-A1Z3 — BNT111 + Libtayo candidate (PD-1-refractory stage IV)

The orchestrator falls back to :func:`get` when no clinician-entered
intake is supplied; chips from this source render with a distinct
``curated_demo`` provenance badge in the UI so nothing looks like real
patient data.
"""

from __future__ import annotations

from ..models import ClinicianIntake


DEMO_INTAKE: dict[str, ClinicianIntake] = {
    # Patient A — BRAF V600E Stage III, age 42.
    # Drives: Harmony Melanoma (NCT05352672) + Harmony H2H (NCT06246916) Eligible.
    #         BNT111+Libtayo Ineligible (no prior anti-PD-1).
    "TCGA-D3-A3MR": ClinicianIntake(
        ecog=0,
        lag3_ihc_percent=35.0,
        measurable_disease_recist=True,
        life_expectancy_months=18,
        prior_systemic_therapy=False,
        prior_anti_pd1=False,
    ),
    # Patient B — Stage IIB non-BRAF, age 43.
    # Drives: Neoadjuvant Phase 2 (NCT06190951) — clinician gates all pass,
    #         two residual free-text never_in_tcga_gates keep it at "needs_more_data"
    #         (far fewer ? chips than the uncurated default).
    #         Harmony variants Ineligible (stage bucket II not in {III,IV}).
    "TCGA-EE-A2MI": ClinicianIntake(
        ecog=1,
        measurable_disease_recist=True,
        life_expectancy_months=24,
        prior_systemic_therapy=False,
        prior_anti_pd1=False,
    ),
    # Patient C — Stage IV NRAS Q61 + NF1, age 72, PD-1-refractory.
    # Drives: BNT111 + Libtayo (NCT04526899) Eligible.
    #         Harmony Melanoma + Harmony H2H Ineligible (prior systemic Rx).
    "TCGA-FS-A1Z3": ClinicianIntake(
        ecog=0,
        measurable_disease_recist=True,
        life_expectancy_months=9,
        prior_systemic_therapy=True,
        prior_anti_pd1=True,
    ),
}


def get(submitter_id: str | None) -> ClinicianIntake | None:
    """Return curated intake for a known demo patient, else ``None``."""
    if not submitter_id:
        return None
    return DEMO_INTAKE.get(submitter_id)


def is_curated(intake: ClinicianIntake | None) -> bool:
    """True iff ``intake`` is one of the registry objects (identity check)."""
    if intake is None:
        return False
    return any(intake is v for v in DEMO_INTAKE.values())
