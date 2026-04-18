"""REGN7508 in Adult Participants for Prevention of Cancer-Associated Thrombosis

NCT: NCT07410117
Phase: Phase 3
CT.gov conditions: ['Cancer-Associated Thrombosis (CAT)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07410117',
    title='REGN7508 in Adult Participants for Prevention of Cancer-Associated Thrombosis',
    phase='Phase 3',
    setting='REGN7508 in Adult Participants for Prevention of Cancer-Associated Thrombosis',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by going through the requirements step by step. The user wants me to fill out the JSON schema based on the provided raw eligibility criteria for this Regeneron-sponsored trial. Let\'s look at each field one by one.\\n\\nFirst, the trial\'s metadata: NCT ID, phase, conditions, min/max age"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Has a histologically confirmed diagnosis of malignant solid tumors which are locally advanced or metastatic as described in the protocol
2. Has a Khorana thromboembolic risk score ≥2 at the time of screening or harbors a somatic documented tumor genetic variant known to be associated with an increased risk of VTE as described in the protocol
3. Has an Eastern Cooperative Oncology Group (ECOG) Performance Status 0 to 2 at the time of screening and day 1 prior to the first dose of study intervention

Key Exclusion Criteria:

1. Has known bleeding conditions (eg, Hemophilia A or B, von Willebrand's disease), hemorrhagic tumor sites, or other conditions with a high risk for bleeding (eg, hepatic disease associated with coagulopathy)
2. Has a cancer diagnosis consisting solely of basal cell or squamous cell skin carcinoma
3. Has a primary brain tumor or brain metastases as described in the protocol
4. Has a history of objective evidence of VTE or ATE, including incidental VTE identified by diagnostic imaging requiring anticoagulation
5. Has any condition that, as judged by the investigator, may confound the results of the study or would place the participant at increased risk of harm if he/she participated in the study

Note: Other Protocol Defined Inclusion/ Exclusion Criteria Apply
"""
