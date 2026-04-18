"""A Study of Cemiplimab Plus Chemotherapy Versus Cemiplimab Plus Chemotherapy Plus Other Cancer Treatments for Adult Patients With Operable Non-Small Cell Lung Cancer (NSCLC)

NCT: NCT06465329
Phase: Phase 2
CT.gov conditions: ['Non-Small Cell Lung Cancer']
Mapped cancer_types: ['lung_adenocarcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06465329',
    title='A Study of Cemiplimab Plus Chemotherapy Versus Cemiplimab Plus Chemotherapy Plus Other Cancer Treatments for Adult Patients With Operable Non-Small Cell Lung Cancer (NSCLC)',
    phase='Phase 2',
    setting='A Study of Cemiplimab Plus Chemotherapy Versus Cemiplimab Plus Chemotherapy Plus Other Cancer Treatments for Adult Patients With Operable Non-Small Cell Lung Cancer (NSCLC)',
    cancer_types=frozenset(['lung_adenocarcinoma']),
    min_age_years=18,
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
General Key Inclusion Criteria:

1. Histologically confirmed stage II through IIIB (N2) NSCLC, that is considered resectable with curative intent, as described in the protocol
2. Measurable disease per Response Evaluation Criteria In Solid Tumors (RECIST) criteria version 1.1
3. Available formalin-fixed paraffin-embedded (FFPE) tumor sample blocks for submission, as described in the protocol
4. Eastern Cooperative Oncology Group Performance Status scale (ECOG PS) of 0 to 1
5. Adequate organ and bone marrow function, as described in the protocol

General Key Exclusion Criteria:

1. Any systemic anti-cancer therapy or radiotherapy for the current tumor, as described in the protocol
2. Presence of known oncogenic alterations in epidermal growth factor receptor (EGFR) or anaplastic lymphoma kinase (ALK) in the tumor prior to randomization, as described in the protocol
3. Presence of grade≥ 2 peripheral neuropathy
4. Another malignancy that is progressing or requires active treatment, as described in the protocol

Arm Specific Exclusion Criteria:

Arm 1:

1. Grade ≥3 hypercalcemia, as defined in the protocol
2. Any central nervous system (CNS) pathology that could increase the risk of immune effector cell-associated neurotoxicity syndrome (ICANS), as described in the protocol
3. Has marked baseline prolongation of the time from the start of the Q wave to the end of the T wave in electrocardiogram (QT)/corrected QT interval (QTc) interval or risk factors for prolonged QTc, as described in the protocol

Note: Other protocol-defined Inclusion/Exclusion criteria apply.
"""
