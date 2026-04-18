"""A First-In Human (FIH) Study to Find Out How Well REGN10597 Medicine Given Alone or in Combination With Cemiplimab Works in Adult Participants Who Have Cancer With Tumors That Have Spread in Their Body

NCT: NCT06413680
Phase: Phase 1/Phase 2
CT.gov conditions: ['Melanoma', 'Clear-Cell Renal-Cell Carcinoma (ccRCC)', 'Advanced Solid Tumors']
Mapped cancer_types: ['cutaneous_melanoma', 'renal_cell_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06413680',
    title='A First-In Human (FIH) Study to Find Out How Well REGN10597 Medicine Given Alone or in Combination With Cemiplimab Works in Adult Participants Who Have Cancer With Tumors That Have Spread in Their Body',
    phase='Phase 1/Phase 2',
    setting='A First-In Human (FIH) Study to Find Out How Well REGN10597 Medicine Given Alone or in Combination With Cemiplimab Works in Adult Participants Who Have Cancer With Tumors That Have Spread in Their Body',
    cancer_types=frozenset(['cutaneous_melanoma', 'renal_cell_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by breaking down the user\'s request. They want me to act as an oncology clinical-trial eligibility normalizer. The task is to take the raw text from ClinicalTrials.gov for a specific trial and fill out a JSON schema based on the provided data.\\n\\nFirst, I\'ll look at the trial details"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

Dose escalation cohorts:

1. Histologically or cytologically confirmed diagnosis of solid malignancy (locally advanced or metastatic) with confirmed progression on standard-of-care therapy
2. Participants are required to submit archival tissue if it is available

Dose expansion cohorts:

1. Histologically of cytologically confirmed diagnosis of one of the following tumors with criteria, as defined in the protocol:

   * Module 1, Cohort 1: anti-PD-(L)1 Progressed Melanoma or
   * Module 1, Cohort 2: anti-PD-(L)1 Progressed RCC or
   * Module 2, Cohort 1: 1L Melanoma
2. ALL Participants ARE REQUIRED to submit fresh pretreatment biopsy during screening, with an additional exploratory biopsy at other time points

Key Exclusion Criteria:

1. Prior treatment with Interleukin 2 (IL2)/IL15/IL-7 given outside the context of concurrent administration with adoptive cell therapy
2. Prior treatment with anti-PD1/PD-L1, or an approved systemic therapy or any previous systemic non-immunomodulatory biologic therapy within 4 weeks, as defined in the protocol
3. Has received radiation therapy or major surgery within 14 days prior to first dose of study drug or has not yet recovered from AEs
4. Has had prior anti-cancer immunotherapy within 4 weeks prior to study intervention, and discontinuation due to grade 3 or 4 toxicities
5. Has ongoing immune-related AEs prior to initiation of study intervention, as defined in the protocol
6. Has known allergy or hypersensitivity to components of the study drug(s)
7. Has any condition requiring ongoing/continuous corticosteroid therapy (\>10 mg prednisone/day or anti-inflammatory equivalent) within 1-2 weeks to the first dose of study intervention
8. Has ongoing or recent (within 5 years) evidence of significant autoimmune disease or any other condition that required treatment with systemic immunosuppressive treatments

NOTE: Other Protocol Defined Inclusion / Exclusion Criteria Apply.
"""
