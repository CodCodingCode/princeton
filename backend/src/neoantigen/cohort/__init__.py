"""TCGA-SKCM cohort loading + twin matching + Kaplan-Meier survival.

Datasets are produced by ``backend/scripts/fetch_tcga_skcm.py``. If the data
folder is missing the loaders return an empty cohort and the caller falls back
to a "no twins available" branch.
"""

from .tcga import TCGAPatient, load_cohort, has_cohort, demo_patient_id, mutations_for_patient
from .twins import find_twins, TwinMatch
from .survival import kaplan_meier, KMPoint

__all__ = [
    "TCGAPatient",
    "load_cohort",
    "has_cohort",
    "demo_patient_id",
    "mutations_for_patient",
    "find_twins",
    "TwinMatch",
    "kaplan_meier",
    "KMPoint",
]
