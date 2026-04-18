"""A Study to See if Giving Fianlimab and Cemiplimab Together is Better Than Cemiplimab Alone at Treating Recurrent or Metastatic Head and Neck Squamous Cell Carcinoma

NCT: NCT06769698
Phase: Phase 2
CT.gov conditions: ['Head and Neck Squamous Cell Carcinoma (HNSCC)']
Mapped cancer_types: ['head_neck_scc']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06769698',
    title='A Study to See if Giving Fianlimab and Cemiplimab Together is Better Than Cemiplimab Alone at Treating Recurrent or Metastatic Head and Neck Squamous Cell Carcinoma',
    phase='Phase 2',
    setting='A Study to See if Giving Fianlimab and Cemiplimab Together is Better Than Cemiplimab Alone at Treating Recurrent or Metastatic Head and Neck Squamous Cell Carcinoma',
    cancer_types=frozenset(['head_neck_scc']),
    min_age_years=18,
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Have histologically confirmed (by local pathology) R/M HNSCC that is considered incurable by local therapies
2. Primary tumor location of oral cavity, oropharynx, larynx, or hypopharynx (patients with cervical neck node SCC with occult primary as described in the protocol
3. PD-L1 expression Combined Positive Score (CPS) ≥1 documented with a previously PD-L1 obtained Immunohistochemistry (IHC) result prior to screening, as described in protocol
4. Oropharynx cancer participants only: HPV status, based on a previously documented result prior to screening, must have been established in a surgical biopsy specimen or a core biopsy specimen as described in the protocol
5. At least 1 lesion that is measurable by Response Evaluation Criteria in Solid Tumors (RECIST) v1.1 as described in the protocol
6. Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1
7. Adequate organ and bone marrow function as described in the protocol

Key Exclusion Criteria:

Medical Conditions

1. Participants who have Progressive Disease (PD) within 6 months of completion of curatively intended systemic treatment for locoregionally advanced HNSCC as described in the protocol
2. Participants who have a primary tumor site of nasopharynx, paranasal sinus or salivary gland (any histology)
3. Head and neck SCC with unknown primary site as described in the protocol
4. Participants with active, known, or suspected autoimmune disease that has required systemic therapy within 5 years of the projected enrollment date as described in the protocol
5. History of interstitial lung disease (eg, idiopathic pulmonary fibrosis, organizing pneumonia) or active, noninfectious pneumonitis that required immune-suppressive doses of glucocorticoids to assist with management
6. History or current evidence of significant cardiovascular disease including, myocarditis, congestive heart failure (as defined by New York Heart Association Functional Classification III and IV), unstable angina, serious uncontrolled arrhythmia, and myocardial infarction 6 months prior to study enrollment.

   Prior/Concomitant Therapy
7. Participants who have received prior systemic anticancer therapy in the R/M HNSCC setting as described in the protocol
8. Participants with a condition requiring corticosteroid therapy (\>10 mg prednisone/prednisolone/day or equivalent) within 14 days of the first dose of study drug as described in the protocol

Note: Other protocol defined Inclusion/ Exclusion Criteria apply
"""
