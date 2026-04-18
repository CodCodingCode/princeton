"""A Study to Assess the Safety and Anti-Tumor Activity of REGN7945 in Combination With Linvoseltamab in Adult Participants With Relapsed/Refractory Multiple Myeloma

NCT: NCT06669247
Phase: Phase 1/Phase 2
CT.gov conditions: ['Relapsed/Refractory Multiple Myeloma']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06669247',
    title='A Study to Assess the Safety and Anti-Tumor Activity of REGN7945 in Combination With Linvoseltamab in Adult Participants With Relapsed/Refractory Multiple Myeloma',
    phase='Phase 1/Phase 2',
    setting='A Study to Assess the Safety and Anti-Tumor Activity of REGN7945 in Combination With Linvoseltamab in Adult Participants With Relapsed/Refractory Multiple Myeloma',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group (ECOG) performance status ≤1 as described in the protocol
2. Received at least 3 lines of therapy including exposure to at least 1 anti-CD38 antibody, 1 immunomodulatory imide drug (IMiD), and 1 proteasome inhibitor (PI) and have demonstrated disease progression on or after the last therapy, as defined in the protocol. Prior treatment with other BCMA directed immunotherapies, including BCMA CAR-T cells and BCMA antibody-drug conjugates (Phase 1 and 2), and with BCMA x CD3 bispecific antibodies (Phase 1 only), is allowed
3. Participants must have the measurable disease for response assessment as described in the protocol
4. Adequate hematologic, hepatic, and renal function as described in the protocol

Key Exclusion Criteria:

1. Diagnosis of plasma cell leukemia, primary systemic light-chain amyloidosis (including myeloma associated amyloidosis), Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or POEMS syndrome (polyneuropathy, organomegaly, endocrinopathy, monoclonal protein, and skin changes)
2. Treatment with any systemic anti-cancer therapy within 5 half-lives or within 28 days before first administration of study drug, whichever is shorter
3. History of allogeneic stem cell transplantation within 6 months, or autologous stem cell transplantation within 12 weeks of the start of study treatment
4. Treatment with systemic corticosteroid treatment with more than 10 mg per day of prednisone or steroid equivalent within 72 hours of start of study drug
5. Participants who have known central nervous system (CNS) involvement with MM or known or suspected progressive multifocal leukoencephalopathy (PML), history of a neurocognitive condition or CNS disorder, or history of seizure within 12 months prior to study enrollment
6. Live or live attenuated vaccination within 28 days before first study drug administration with a vector that has replicative potential
7. Has received a COVID-19 vaccination within 1 week of planned start of study medication as described in the protocol
8. Myelodysplastic syndrome or another malignancy in the past 3 years, except for nonmelanoma skin cancer, in situ carcinoma, thyroid cancer, or low-risk early stage prostate adenocarcinoma, as described in the protocol
9. Significant cardiovascular disease as described in the protocol
10. Uncontrolled infection with HIV, Hep B or Hep C infection, or other uncontrolled infection, such as CMV, as described in the protocol
11. Known hypersensitivity to both allopurinol and rasburicase

Note: Other protocol-defined Inclusion/ Exclusion Criteria apply
"""
