"""Study of REGN4018 (Ubamatamab) Administered Alone or in Combination With Cemiplimab in Adult Patients With Recurrent Ovarian Cancer or Other Recurrent Mucin-16 Expressing (MUC16+) Cancers

NCT: NCT03564340
Phase: Phase 1/Phase 2
CT.gov conditions: ['Recurrent Ovarian Cancer', 'Recurrent Fallopian Tube Cancer', 'Recurrent Primary Peritoneal Cancer', 'Recurrent Endometrial Cancer', 'Endometrial Cancer', 'Low-grade Serous Ovarian Cancer']
Mapped cancer_types: ['other', 'ovarian_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT03564340',
    title='Study of REGN4018 (Ubamatamab) Administered Alone or in Combination With Cemiplimab in Adult Patients With Recurrent Ovarian Cancer or Other Recurrent Mucin-16 Expressing (MUC16+) Cancers',
    phase='Phase 1/Phase 2',
    setting='Study of REGN4018 (Ubamatamab) Administered Alone or in Combination With Cemiplimab in Adult Patients With Recurrent Ovarian Cancer or Other Recurrent Mucin-16 Expressing (MUC16+) Cancers',
    cancer_types=frozenset(['other', 'ovarian_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start analyzing the user\'s query. They provided the trial details for NCT03564340, which is a Regeneron-sponsored study. The task is to structure the eligibility criteria into a specific JSON format. I need to go through each part carefully.\\n\\nFirst, check the required fields. The schema "'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Ovarian Cancer Cohorts Only: Patients with histologically or cytologically confirmed diagnosis of advanced, epithelial ovarian cancer (except carcinosarcoma), primary peritoneal, or fallopian tube cancer who have all of the following:

   1. serum CA-125 level ≥2 x upper limit of normal (ULN) (in screening, not required for low-grade serous carcinoma)
   2. has received at least 1 line of platinum-containing therapy or must be platinum-intolerant (applicable for dose escalation and non-randomized dose expansion cohorts)
   3. documented relapse or progression on or after the most recent line of therapy
   4. no standard therapy options likely to convey clinical benefit
2. Adequate organ and bone marrow function as defined in the protocol
3. Life expectancy of at least 3 months
4. Randomized phase 2 expansion cohort (Ovarian Cancer only): Platinum-resistant ovarian cancer patients who have had 2 to 4 lines of platinum-based therapy as defined in the protocol.
5. Endometrial Cancer Cohorts Only: histologically confirmed endometrial cancer that has progressed or recurrent after prior anti-Programmed Cell Death Ligand 1 (PD-1) therapy and platinum-based chemotherapy:

   1. MUC16 positivity of tumor cells ≥25% by immunohistochemistry (IHC), as defined in the protocol
   2. 1-4 prior lines of systemic therapy, as described in the protocol

Key Exclusion Criteria:

1. Prior treatment with anti-Programmed Cell Death (PD-1)/PD-L1 therapy, as described in the protocol
2. Ovarian Cancer Expansion cohorts only: More than 4 prior lines of cytotoxic chemotherapy (does not apply to low-grade serous ovarian cancer cohort)
3. Prior treatment with a MUC16 - targeted therapy
4. Untreated or active primary brain tumor, central nervous system (CNS) metastases, or spinal cord compression, as described in the protocol
5. History and/or current cardiovascular disease, as defined in the protocol
6. Severe and/or uncontrolled hypertension at screening. Patients taking anti-hypertensive medication must be on a stable anti-hypertensive regimen

Note: Other protocol-defined Inclusion/Exclusion Criteria apply
"""
