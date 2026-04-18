"""Investigation of Ubamatamab Combination Therapy in Adult Participants With Platinum-Resistant Ovarian Cancer

NCT: NCT06787612
Phase: Phase 2
CT.gov conditions: ['Ovarian Cancer', 'Fallopian Tube Cancer', 'Primary Peritoneal Cancer']
Mapped cancer_types: ['ovarian_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06787612',
    title='Investigation of Ubamatamab Combination Therapy in Adult Participants With Platinum-Resistant Ovarian Cancer',
    phase='Phase 2',
    setting='Investigation of Ubamatamab Combination Therapy in Adult Participants With Platinum-Resistant Ovarian Cancer',
    cancer_types=frozenset(['ovarian_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, I need to process the user\'s request correctly this time. Let me start by understanding the problem. The user provided a JSON schema that the AI must fill out based on the eligibility criteria from a clinical trial. The trial is NCT06787612, a Phase 2 study for ovarian, fallopian tube, and pri"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participants with histologically or cytologically confirmed diagnosis of advanced serous or endometrioid ovarian (regardless of the grade), primary peritoneal, or fallopian tube cancer (clear cell, mucinous, and carcinosarcoma are excluded)
2. Must have progression on prior therapy documented radiographically and must have at least 1 measurable lesion (not previously irradiated) that can be accurately measured by RECIST 1.1
3. Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1
4. Adequate organ and bone marrow function, as described in the protocol
5. Platinum-Resistant Ovarian Cancer, as described in the protocol

Key Exclusion Criteria:

1. Major surgical procedure or significant traumatic injury within 4 weeks prior to first dose of study intervention(s)
2. Documented allergic or acute hypersensitivity reaction attributed to antibody treatments or doxorubicin hydrochloride or components of study intervention(s)
3. Another malignancy that is progressing or requires active treatment, as described in the protocol
4. Untreated or active Central Nervous System (CNS) metastases, or carcinomatous meningitis, as described in the protocol
5. Uncontrolled infections including but not limited to human immunodeficiency virus, hepatitis B or hepatitis C infection, or diagnosis of immunodeficiency
6. Moderate to large or ascites, as described in the protocol
7. Bowel obstruction within last 3 months or current need for parenteral nutrition

NOTE: Other protocol-defined inclusion/exclusion criteria apply
"""
