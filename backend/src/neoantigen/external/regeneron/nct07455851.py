"""A Trial to Study if REGN17372 in Combination With Linvoseltamab is Tolerable for Adult Participants With Relapsed/Refractory Multiple Myeloma

NCT: NCT07455851
Phase: Phase 1/Phase 2
CT.gov conditions: ['Relapsed Refractory Multiple Myeloma (RRMM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07455851',
    title='A Trial to Study if REGN17372 in Combination With Linvoseltamab is Tolerable for Adult Participants With Relapsed/Refractory Multiple Myeloma',
    phase='Phase 1/Phase 2',
    setting='A Trial to Study if REGN17372 in Combination With Linvoseltamab is Tolerable for Adult Participants With Relapsed/Refractory Multiple Myeloma',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s see. I need to process the eligibility criteria from the given ClinicalTrials.gov data for this Regeneron trial. The goal is to fill out the JSON schema correctly. Let me start by breaking down each field.\\n\\nFirst, the NCT ID is NCT07455851, Phase 1/2, conditions are Relapsed Refractory M"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participants with RRMM who have exhausted (or are not a candidate for) all therapeutic options that are expected to provide meaningful clinical benefit and have received at least 3 lines of therapy as defined in the protocol
2. ECOG performance status score ≤1
3. Participants must have measurable disease for response assessment as described in the protocol
4. Adequate hematologic, cardiac, hepatic, and renal function, as described in the protocol

Key Exclusion Criteria:

1. Participants with non-secretory MM, active plasma cell leukemia, known amyloidosis, Waldenström macroglobulinemia, or known POEMS syndrome as defined in the protocol
2. Participants who have known MM brain lesions or CNS involvement
3. Participants with a history of PML, a neurocognitive condition or CNS movement disorder, or a history of seizure within 12 months prior to entering screening
4. Prior treatment with GPRC5D-directed immunotherapies (phase 1 and phase 2) and/or prior treatment with a BCMAxCD3 bispecific antibody (phase 2)

Note: Other protocol defined inclusion/exclusion criteria apply
"""
