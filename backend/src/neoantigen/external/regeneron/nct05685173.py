"""A Trial to Study if REGN5837 in Combination With Odronextamab is Safe for Adult Participants With Aggressive B-cell Non-Hodgkin Lymphomas

NCT: NCT05685173
Phase: Phase 1
CT.gov conditions: ['B-cell Non-Hodgkins Lymphoma (B-NHL)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05685173',
    title='A Trial to Study if REGN5837 in Combination With Odronextamab is Safe for Adult Participants With Aggressive B-cell Non-Hodgkin Lymphomas',
    phase='Phase 1',
    setting='A Trial to Study if REGN5837 in Combination With Odronextamab is Safe for Adult Participants With Aggressive B-cell Non-Hodgkin Lymphomas',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: \'Okay, let\\\'s start by going through each field in the JSON schema and checking the raw eligibility criteria.\\n\\nFirst, the requires_advanced_disease. The inclusion criteria mention "disease that has progressed after at least 2 lines of systemic therapy", which implies advanced or relapsed disease. So p\''],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Have documented CD20+ aggressive B-NHL, with disease that has progressed after at least 2 lines of systemic therapy containing an anti-CD20 antibody and an alkylating agent, as described in the protocol.
2. Measurable disease on cross sectional imaging as defined in the protocol
3. Eastern Cooperative Oncology Group (ECOG) performance status 0 or 1
4. Adequate bone marrow, renal and hepatic function as defined in the protocol
5. Availability of tumor tissue for submission to central laboratory is required for study enrollment. Archival tumor tissue for histological assessment prior to enrollment is allowed
6. During dose expansion phase of the study, participant should be willing to undergo mandatory tumor biopsies, if in the opinion of the investigator, the participant has an accessible lesion that can be biopsied without significant risk to the participant.

Key Exclusion Criteria:

1. Prior treatments with allogeneic stem cell transplantation or solid organ transplantation, treatment with anti-CD20 x anti- CD3 bispecific antibody, such as odronextamab
2. Diagnosis of mantle cell lymphoma (MCL)
3. Primary central nervous system (CNS) lymphoma or known involvement by non-primary CNS lymphoma, as described in the protocol
4. Treatment with any systemic anti-lymphoma therapy within 5 half-lives or within 14 days prior to first administration of study drug, whichever is shorter, as described in the protocol
5. Standard radiotherapy within 14 days of first administration of study drug, as described in the protocol
6. Continuous systemic corticosteroid treatment with more than 10 mg per day of prednisone or corticosteroid equivalent within 72 hours of start of odronextamab
7. Co-morbid conditions, as described in the protocol
8. Infections, as described in the protocol
9. Allergy/hypersensitivity: Known hypersensitivity to both allopurinol and rasburicase

NOTE: Other protocol defined inclusion / exclusion criteria apply
"""
