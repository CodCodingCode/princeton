"""A Study to Investigate Ubamatamab With and Without REGN7075 in Adult Participants With Advanced/Metastatic Non-Small Cell Lung Cancer (NSCLC)

NCT: NCT07154290
Phase: Phase 2
CT.gov conditions: ['Advanced/Metastatic Non-Small Cell Lung Cancer']
Mapped cancer_types: ['lung_adenocarcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07154290',
    title='A Study to Investigate Ubamatamab With and Without REGN7075 in Adult Participants With Advanced/Metastatic Non-Small Cell Lung Cancer (NSCLC)',
    phase='Phase 2',
    setting='A Study to Investigate Ubamatamab With and Without REGN7075 in Adult Participants With Advanced/Metastatic Non-Small Cell Lung Cancer (NSCLC)',
    cancer_types=frozenset(['lung_adenocarcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: \'Okay, let\\\'s go through each part of the problem carefully. The user provided the trial details and the raw eligibility criteria. I need to map all that into the specified JSON structure.\\n\\nStarting with requires_advanced_disease. The key inclusion criteria mention "advanced (stage IIIB not amenable t\''],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Has histologically or cytologically confirmed diagnosis of advanced (stage IIIB not amenable to definitive chemoradiotherapy or stage IIIC) or metastatic (stage IV) NSCLC
2. Has received appropriate first line standard of care treatment for advanced or metastatic NSCLC, as described in the protocol
3. If platinum doublet chemotherapy was not administered as first line therapy, it is required in a later line of therapy prior to enrollment unless there is a documented reason why it is not appropriate
4. Has tumor tissue (archival or fresh) available for testing MUC16 expression by immunohistochemistry inclusion (IHC), as described in the protocol
5. Has at least 1 radiographically measurable lesion by Computed Tomography (CT) or Magnetic Resonance Imaging (MRI) per RECIST v1.1 criteria. Target lesions may be located in a previously irradiated field if there is documented (radiographic) disease progression in that site
6. Has an Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1

Key Exclusion Criteria:

1. Has progression of disease fewer than 84 days from starting initial anti-Programmed Cell Death (PD)-(L) 1 therapy
2. Experienced toxicity related to prior treatment that has not resolved to grade 1 prior to initiation of study intervention (except alopecia, hearing loss, grade 2 neuropathy, or endocrinopathy managed with hormone replacement therapy)
3. Has untreated or active primary brain tumor, Central Nervous System (CNS) metastases, leptomeningeal disease, or spinal cord compression, as described in the protocol
4. Current participation OR past participation in another investigational study in which an investigational intervention (eg, drug, vaccine, invasive device) was administered within 4 weeks before planned first dose of study intervention in this clinical study
5. Has received prior monoclonal antibody against PD-(L)1 within 21 days of the first dose of study intervention
6. Has had other prior anti-cancer immunotherapy within 21 days prior to study intervention, as described in the protocol
7. Has received prior cytotoxic chemotherapy within 21 days of the first dose of study intervention
8. Has received an anti-EGFR antibody therapy within the following drug-specific window prior to first dose of study intervention (approximately 5 half-lives), as described in the protocol

NOTE: Other protocol defined inclusion / exclusion criteria apply
"""
