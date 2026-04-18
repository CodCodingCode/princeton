"""A Study of ImmunoPet Imaging Using 89Zr-DFO-REGN5054 in Adult Participants With Solid Cancers Treated With Cemiplimab

NCT: NCT05259709
Phase: Phase 1
CT.gov conditions: ['Advanced Solid Tumor', 'Metastatic Solid Tumor']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05259709',
    title='A Study of ImmunoPet Imaging Using 89Zr-DFO-REGN5054 in Adult Participants With Solid Cancers Treated With Cemiplimab',
    phase='Phase 1',
    setting='A Study of ImmunoPet Imaging Using 89Zr-DFO-REGN5054 in Adult Participants With Solid Cancers Treated With Cemiplimab',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by carefully reading the problem and the user\'s instructions. The task is to fill out a specific JSON schema based on the provided clinical trial data. The user mentioned that the previous attempt failed validation, so I need to be extra careful to follow the rules exactly.\\n\\nFirst,"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

* Advanced or metastatic solid tumors that may respond to anti-programmed cell death 1 (PD-1) immunotherapy
* Measurable disease according to Response Evaluation Criteria in Solid Tumours (RECIST) 1.1 criteria
* Eastern Cooperative Oncology Group (ECOG) performance status of ≤1
* Adequate organ and bone marrow function as defined in the protocol
* Willing and able to comply with clinic visits and study-related procedures (including required tumor biopsy for Part B)

Key Exclusion Criteria:

* Currently receiving another cancer treatment or inadequate time since last therapy, as defined in the protocol
* Has not yet recovered from acute toxicities from prior therapy; exceptions defined in the protocol
* Prior treatment with a blocker of the PD-1/Programmed death ligand 1 (PD-L1) pathway
* Currently receiving or has received chimeric antigen receptor (CAR-T) cell therapy
* Symptomatic or untreated brain metastases, leptomeningeal disease, or spinal cord compression
* Known history of or any evidence of interstitial lung disease, active, noninfectious pneumonitis (past 5 years) or active tuberculosis

NOTE: Other protocol defined inclusion/exclusion criteria apply.
"""
