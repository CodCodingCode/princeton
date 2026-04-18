"""A Study to Find Out How Safe REGN5668 is and How Well it Works In Adult Women When Given With Either Cemiplimab, or Cemiplimab + Fianlimab, or Ubamatamab

NCT: NCT04590326
Phase: Phase 1/Phase 2
CT.gov conditions: ['Ovarian Cancer', 'Fallopian Tube Cancer', 'Primary Peritoneal Cancer', 'Endometrial Cancer']
Mapped cancer_types: ['other', 'ovarian_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT04590326',
    title='A Study to Find Out How Safe REGN5668 is and How Well it Works In Adult Women When Given With Either Cemiplimab, or Cemiplimab + Fianlimab, or Ubamatamab',
    phase='Phase 1/Phase 2',
    setting='A Study to Find Out How Safe REGN5668 is and How Well it Works In Adult Women When Given With Either Cemiplimab, or Cemiplimab + Fianlimab, or Ubamatamab',
    cancer_types=frozenset(['other', 'ovarian_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: \'Okay, let\\\'s go through the eligibility criteria step by step to fill in the JSON fields.\\n\\nFirst, the required flags. Let\\\'s check each one:\\n\\n1. requires_advanced_disease: The key inclusion criteria mention "advanced epithelial ovarian cancer" and endometrial cancer after anti-PD-1. So yes, it\\\'s requi\''],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Ovarian Cancer Cohorts Only: Has histologically or cytologically confirmed diagnosis of advanced epithelial ovarian cancer (except carcinosarcoma), primary peritoneal, or fallopian tube cancer that has received at least 1 line of platinum-based systemic therapy as defined in the protocol
2. Expansion cohorts only: Has at least 1 lesion that is measurable by RECIST 1.1 as described in the protocol.
3. Has a serum CA-125 level ≥2x ULN (in screening, not applicable to endometrial cohorts)
4. Has adequate organ and bone marrow function as defined in the protocol
5. Has an Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1.
6. Has a life expectancy of at least 3 months
7. Endometrial Cancer Cohorts Only: histologically confirmed endometrial cancer that has progressed or recurrent after prior anti-PD-1 therapy and platinum-based chemotherapy as described in the protocol

Key Exclusion Criteria:

1. Current or recent (as defined in the protocol) treatment with an investigational agent, systemic biologic therapy, or anti-cancer immunotherapy
2. Has had another malignancy within the last 5 years that is progressing, requires active treatment, or has a high likelihood of recurrence as defined in the protocol
3. Prior treatment with a Mucin 16 (MUC16)-targeted therapy
4. Ovarian Expansion cohorts only: More than 5 prior lines of systemic therapy
5. Has any condition that requires ongoing/continuous corticosteroid therapy as defined in the protocol within 1 week prior to the first dose of study drug
6. Has ongoing or recent (within 5 years) evidence of significant autoimmune disease that required treatment with systemic immunosuppressive treatments as defined in the protocol
7. Has untreated or active primary brain tumor, CNS metastases, leptomeningeal disease, or spinal cord compression as defined in the protocol
8. Has history of clinically significant cardiovascular disease as defined in the protocol
9. Has known allergy or hypersensitivity to cemiplimab and/or components of study drug(s).

Note: Other protocol-defined Inclusion/Exclusion criteria apply
"""
