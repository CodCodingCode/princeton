"""A Trial to Find Out How Safe REGN7075 is and How Well it Works in Combination With Cemiplimab for Adult Participants With Advanced Cancers

NCT: NCT04626635
Phase: Phase 1/Phase 2
CT.gov conditions: ['Advanced Solid Tumors']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT04626635',
    title='A Trial to Find Out How Safe REGN7075 is and How Well it Works in Combination With Cemiplimab for Adult Participants With Advanced Cancers',
    phase='Phase 1/Phase 2',
    setting='A Trial to Find Out How Safe REGN7075 is and How Well it Works in Combination With Cemiplimab for Adult Participants With Advanced Cancers',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by going through all the required fields and figuring out their values based on the provided information.\\n\\nFirst, the raw eligibility criteria. The key inclusion criteria mention ECOG 0 or 1, which is required. The exclusion criteria don\'t mention any specific stage, but the condit"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Has an Eastern Cooperative Oncology Group (ECOG) performance status of 0 or 1
2. Has histologically or cytologically confirmed cancer that meets criteria as defined in the protocol
3. Expansion Cohorts only: Is anti-Programmed cell Death protein-1 (PD-1)/Programmed cell Death Ligand-1 (PD-L1) naïve, defined as never having previously been treated with a drug that targets the PD-1
4. Has at least 1 lesion that meets study criteria as defined in the protocol
5. Willing to provide tumor tissue from newly obtained biopsy (at a minimum core biopsy) from a tumor site that has not been previously irradiated
6. Has adequate organ and bone marrow function as defined in the protocol
7. In the judgement of the investigator, has a life expectancy of at least 3 months

Key Exclusion Criteria:

1. Is currently participating in another study of a therapeutic agent
2. Has participated in any study of an investigational agent or an investigational device within 4 weeks of the first administration of study drug as defined in the protocol
3. Has received treatment with an approved systemic therapy within 4 weeks of the first administration of study drug or has not yet recovered (ie, grade 1 or baseline) from any acute toxicities
4. Has received recent anti-Epidermal Growth Factor Receptor (EGFR) antibody therapy as defined in the protocol
5. Has received radiation therapy or major surgery within 14 days of the first administration of study drug or has not recovered (ie, grade 1 or baseline) from adverse events
6. Has received any previous systemic, non-immunomodulatory biologic therapy within 4 weeks of first administration of study drug.
7. Has had prior anti-cancer immunotherapy within 5 half-lives prior to study drug as defined in the protocol
8. Has second malignancy that is progressing or requires active treatment as defined in the protocol
9. Has any condition requiring ongoing/continuous corticosteroid therapy (\>10 mg prednisone/day or anti-inflammatory equivalent) within 1-2 weeks prior to the first dose of study drug as defined in the protocol
10. Has ongoing or recent (within 5 years) evidence of significant autoimmune disease or any other condition that required treatment with systemic immunosuppressive treatments as defined in the protocol
11. Has untreated or active primary brain tumor, Central Nervous System (CNS) metastases, leptomeningeal disease, or spinal cord compression
12. Has encephalitis, meningitis, organic brain disease (eg, Parkinson's disease) or uncontrolled seizures within 1 year prior to the first dose of study drug
13. Has any ongoing inflammatory skin disease as defined in the protocol

NOTE: Other protocol-defined Inclusion/ Exclusion Criteria apply
"""
