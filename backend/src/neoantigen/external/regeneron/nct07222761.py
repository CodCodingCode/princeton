"""A Study to Compare Linvoseltamab Monotherapy and Linvoseltamab + Carfilzomib Combination Therapy With Standard-of-Care Combination Regimens in Adult Participants With Relapsed/Refractory Multiple Myeloma (RRMM)

NCT: NCT07222761
Phase: Phase 3
CT.gov conditions: ['Relapsed and/or Refractory Multiple Myeloma (RRMM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07222761',
    title='A Study to Compare Linvoseltamab Monotherapy and Linvoseltamab + Carfilzomib Combination Therapy With Standard-of-Care Combination Regimens in Adult Participants With Relapsed/Refractory Multiple Myeloma (RRMM)',
    phase='Phase 3',
    setting='A Study to Compare Linvoseltamab Monotherapy and Linvoseltamab + Carfilzomib Combination Therapy With Standard-of-Care Combination Regimens in Adult Participants With Relapsed/Refractory Multiple Myeloma (RRMM)',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by carefully going through each part of the problem. The user provided a specific NCT ID (NCT07222761) which is a Phase 3 trial for relapsed/refractory multiple myeloma (RRMM). The conditions listed are RRMM, and the age is 18+ with no upper limit.\\n\\nFirst, the required fields. Let\'"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participant with RRMM who received at least 1 but not more than 3 prior lines of therapy, which must have included treatment with lenalidomide and either a Protease Inhibitor (PI) or anti-CD38 monoclonal antibody
2. Eastern Cooperative Oncology Group (ECOG) performance status score ≤2
3. Confirmed progressive disease according to IMWG criteria during or after the most recent line of therapy

Key Exclusion Criteria:

1. Prior treatment with a T cell-based immunotherapy targeting BCMA, including BCMA-directed bispecific antibodies, Bispecific T-cell Engagers (BiTEs), and Chimeric Antigen Receptor (CAR) T cells. Antibody-drug conjugates targeting BCMA (eg, belantamab mafodotin) are not excluded
2. Diagnosis of plasma cell leukemia, symptomatic amyloidosis (including myeloma-associated amyloidosis), Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or POEMS syndrome (polyneuropathy, organomegaly, endocrinopathy, monoclonal protein, and skin changes)
3. Known Central Nervous System (CNS) involvement of myeloma including meningeal involvement
4. History of neurodegenerative condition, Progressive Multifocal Leukoencephalopathy (PML), or CNS movement disorder

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
