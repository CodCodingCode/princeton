"""A Study to Compare Linvoseltamab and Daratumumab Treatment in High-Risk Smoldering Multiple Myeloma (HR-SMM)

NCT: NCT07393282
Phase: Phase 3
CT.gov conditions: ['High Risk Smoldering Multiple Myeloma (HR-SMM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: NOT_YET_RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07393282',
    title='A Study to Compare Linvoseltamab and Daratumumab Treatment in High-Risk Smoldering Multiple Myeloma (HR-SMM)',
    phase='Phase 3',
    setting='Phase 3 study comparing linvoseltamab vs daratumumab in high-risk smoldering multiple myeloma (HR-SMM)',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    requires_ecog_0_1=True,
    requires_no_prior_systemic_advanced=True,
    never_in_tcga_gates=['Exclusion: history of neurodegenerative condition, CNS movement disorder, or seizure within 12 months', 'Exclusion: prior exposure to treatments for plasma cell disorders (including chemotherapies, immunomodulatory drugs, proteasome inhibitors, anti-CD38 antibodies)', 'Exclusion: diagnosis of systemic light chain amyloidosis, Waldenström macroglobulinemia, plasma cell leukemia, or soft tissue plasmacytoma', 'Other protocol-defined criteria apply'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group performance status score ≤1
2. SMM diagnosis per IMWG criteria as defined in the protocol
3. Meets HR-SMM criteria by 1 of the risk models as defined in the protocol

Key Exclusion Criteria:

1. Evidence of myeloma-defining events attributable to the underlying plasma cell dyscrasia, as defined in the protocol
2. Diagnosis of systemic light chain amyloidosis, Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), plasma cell leukemia, or soft tissue plasmacytoma
3. History of neurodegenerative condition, progressive multifocal leukoencephalopathy, or Central Nervous System (CNS) movement disorder
4. History of a seizure within the 12 months of randomization
5. Prior exposure to any approved or investigational treatments directed against a clonal plasma cell disorder (including but not limited to conventional chemotherapies, radiotherapy, immunomodulatory drugs, proteasome inhibitors, anti-CD38 antibodies). Ongoing treatment with other monoclonal antibodies (eg, infliximab, rituximab) or other treatments likely to interfere with study procedures or results, as described in the protocol.

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
