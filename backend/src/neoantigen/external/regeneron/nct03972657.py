"""A Trial to Find Out if REGN5678 (Nezastomig) is Safe and How Well it Works Alone or in Combination With Cemiplimab for Adult Participants With Metastatic Castration-Resistant Prostate Cancer and Other Tumors

NCT: NCT03972657
Phase: Phase 1/Phase 2
CT.gov conditions: ['Metastatic Castration-Resistant Prostate Cancer (mCRPC)', 'Clear Cell Renal Cell Carcinoma (ccRCC)']
Mapped cancer_types: ['prostate_carcinoma', 'renal_cell_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT03972657',
    title='A Trial to Find Out if REGN5678 (Nezastomig) is Safe and How Well it Works Alone or in Combination With Cemiplimab for Adult Participants With Metastatic Castration-Resistant Prostate Cancer and Other Tumors',
    phase='Phase 1/Phase 2',
    setting='A Trial to Find Out if REGN5678 (Nezastomig) is Safe and How Well it Works Alone or in Combination With Cemiplimab for Adult Participants With Metastatic Castration-Resistant Prostate Cancer and Other Tumors',
    cancer_types=frozenset(['prostate_carcinoma', 'renal_cell_carcinoma']),
    min_age_years=18,
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

mCRPC cohorts (men):

1. Men with histologically or cytologically confirmed adenocarcinoma of the prostate without pure small cell carcinoma.
2. PSA value at screening ≥4 ng/mL that has progressed within 6 months prior to screening as defined in the protocol.
3. Has received ≥2 lines prior systemic therapy approved in the metastatic and/or castration-resistant setting (in addition to Androgen Deprivation Therapy \[ADT\]) including at least:

   1. one second-generation anti-androgen therapy (eg, abiraterone, enzalutamide, apalutamide, or darolutamide)
   2. 177Lu-PSMA-617 radiotherapy, or another lutetium-based PSMA targeted radioligand, as described in the protocol

ccRCC cohorts (men and women):

1. Histologically or cytologically confirmed RCC with a clear-cell component.
2. Diagnosis of metastatic ccRCC with at least one measurable lesion via RECIST 1.1 criteria
3. Has progressed on or after ≥1 line prior systemic therapy approved in the metastatic setting. Prior treatment must include an anti-Programmed Death-1 (receptor) \[PD-1\]/Programmed Death-Ligand 1 (PD-L1) therapy and either ipilimumab and/or a tyrosine kinase inhibitor

Key Exclusion Criteria:

1. Has received treatment with an approved systemic therapy within 3 weeks of dosing or has not yet recovered (ie, grade ≤1 or baseline) from any acute toxicities, as described in the protocol
2. Has received any previous systemic biologic therapy within 5 half-lives of first dose of study therapy, as described in the protocol
3. Has received prior PSMA-targeting therapy with the exception of a PSMA targeting radioligand (eg. 177Lu-PSMA-617) in mCRPC
4. Dose Escalation: Has had prior anti-cancer immunotherapy (other than sipuleucel-T) within 5 half-lives prior to study therapy.
5. Dose Expansion (mCRPC only): Has had prior anti-cancer immunotherapy, as described in the protocol
6. Any condition that requires ongoing/continuous corticosteroid therapy (\>10 mg prednisone/day or anti-inflammatory equivalent) within 1 week prior to the first dose of study therapy
7. Ongoing or recent (within 5 years) evidence of significant autoimmune disease that required treatment with systemic immunosuppressive treatments, as described in the protocol
8. Encephalitis, meningitis, neurodegenerative disease (with the exception of mild dementia that does not interfere with Activities of Daily Living \[ADLs\]) or uncontrolled seizures in the year prior to first dose of study therapy
9. Uncontrolled infection with Human Immunodeficiency Virus (HIV), hepatitis B or hepatitis C infection; or diagnosis of immunodeficiency

NOTE: Other protocol defined Inclusion/Exclusion Criteria apply
"""
