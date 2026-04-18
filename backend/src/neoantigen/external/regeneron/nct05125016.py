"""A Trial to Find Out if REGN4336 is Safe and How Well it Works Alone and in Combination With Cemiplimab or REGN5678 for Adult Participants With Advanced Prostate Cancer

NCT: NCT05125016
Phase: Phase 1/Phase 2
CT.gov conditions: ['Metastatic Castration-resistant Prostate Cancer']
Mapped cancer_types: ['prostate_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05125016',
    title='A Trial to Find Out if REGN4336 is Safe and How Well it Works Alone and in Combination With Cemiplimab or REGN5678 for Adult Participants With Advanced Prostate Cancer',
    phase='Phase 1/Phase 2',
    setting='A Trial to Find Out if REGN4336 is Safe and How Well it Works Alone and in Combination With Cemiplimab or REGN5678 for Adult Participants With Advanced Prostate Cancer',
    cancer_types=frozenset(['prostate_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by analyzing the given data. The task is to fill out a JSON schema based on the raw eligibility criteria for the trial NCT05125016. Let\'s go through each field one by one.\\n\\nFirst, the requires_advanced_disease. The trial is for metastatic castration-resistant prostate cancer (mCRPC"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Histologically or cytologically confirmed adenocarcinoma of the prostate without pure small cell carcinoma
2. Metastatic, castration-resistant prostate cancer (mCRPC) with PSA value at screening ≥4 ng/mL that has progressed within 6 months prior to screening, according to 1 of the following:

   1. PSA progression as defined by a rising PSA level confirmed with an interval of ≥1 week between each assessment
   2. Radiographic disease progression in soft tissue based on Response Evaluation Criteria in Solid Tumors (RECIST) version 1.1 criteria with or without PSA progression
   3. Radiographic disease progression in bone defined as the appearance of 2 or more new bone lesions on bone scan with or without PSA progression NOTE: Measurable disease per RECIST version 1.1 per local reading at screening is not an eligibility criterion for enrollment
3. Has progressed upon or intolerant to ≥2 lines prior systemic therapy approved in the metastatic and/or castration-resistant setting (in addition to androgen deprivation therapy \[ADT\]) including at least one second-generation anti-androgen therapy (e.g. abiraterone, enzalutamide, apalutamide, or darolutamide)

Key Exclusion Criteria:

1. Has received treatment with an approved systemic therapy within 3 weeks of dosing or has not yet recovered (ie, grade ≤1 or baseline) from any acute toxicities
2. Has received any previous systemic biologic or immune-modulating therapy (except for Sipuleucel-T) within 5 half-lives of first dose of study therapy, as described in the protocol
3. Has received prior PSMA-targeting therapy. Exception: Prior therapy with approved PSMA-targeted radioligand(s) is permitted
4. Any condition that requires ongoing/continuous corticosteroid therapy (\>10 mg prednisone/day or anti-inflammatory equivalent) within 1 week prior to the first dose of study therapy
5. Ongoing or recent (within 5 years) evidence of significant autoimmune disease that required treatment with systemic immunosuppressive treatments
6. Encephalitis, meningitis, neurodegenerative disease (with the exception of mild dementia that does not interfere with activities of daily living \[ADLs\]) or uncontrolled seizures in the year prior to first dose of study therapy
7. Uncontrolled infection with human immunodeficiency virus (HIV), hepatitis B or hepatitis C infection; or diagnosis of immunodeficiency, as described in the protocol.

NOTE: Other protocol defined Inclusion/Exclusion Criteria apply
"""
