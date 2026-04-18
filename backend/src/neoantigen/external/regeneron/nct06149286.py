"""A Trial to Find Out if Odronextamab Combined With Lenalidomide is Safe and Works Better Than Rituximab Combined With Lenalidomide in Adult Participants With Follicular Lymphoma and Marginal Zone Lymphoma

NCT: NCT06149286
Phase: Phase 3
CT.gov conditions: ['Relapsed/Refractory Follicular Lymphoma', 'Relapsed/Refractory Marginal Zone Lymphoma (R/R MZL)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06149286',
    title='A Trial to Find Out if Odronextamab Combined With Lenalidomide is Safe and Works Better Than Rituximab Combined With Lenalidomide in Adult Participants With Follicular Lymphoma and Marginal Zone Lymphoma',
    phase='Phase 3',
    setting='Relapsed/refractory follicular lymphoma or marginal zone lymphoma',
    cancer_types=frozenset(['other']),
    requires_advanced_disease=True,
    min_age_years=18,
    requires_measurable_disease=True,
    never_in_tcga_gates=['Prior systemic therapy including anti-CD20 monoclonal antibody required', 'Specific histology requirements for FL grade 1-3a or MZL subtypes'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Local histologic confirmation of FL grade 1-3a or MZL (nodal, splenic, or extra nodal MZL) as assessed by the investigator, as described in the protocol.
2. Must have refractory disease or relapsed after at least 1 prior line (with a duration of at least 2 cycles) of systemic chemo-immunotherapy or immunotherapy. Prior systemic therapy should have included at least one anti-Cluster of Differentiation 20 (CD20) monoclonal antibody and participant should meet indication for treatment, as described in the protocol.
3. Have measurable disease on cross sectional imaging documented by diagnostic Computed Tomography \[CT\], or Magnetic Resonance Imaging \[MRI\] imaging, as described in the protocol.
4. Eastern Cooperative Oncology Group (ECOG) performance status of 0 to 2.
5. Adequate hematologic and organ function, as described in the protocol.
6. All study participants must:

   1. Have an understanding that lenalidomide could have a potential teratogenic risk.
   2. Agree to abstain from donating blood while taking study drug therapy and for 28 days after discontinuation of lenalidomide.
   3. Agree not to share study medication with another person.
   4. Agree to be counseled about pregnancy precautions and risk of fetal exposure associated with lenalidomide.

Key Exclusion Criteria:

1. Primary Central Nervous System (CNS) lymphoma or known involvement (either current or prior history of CNS involvement) by non-primary CNS NHL, as described in the protocol.
2. Participants with current or past histological evidence of high-grade or diffuse large B-cell lymphoma, or any histology other than FL grade 1-3a or MZL.
3. History of or current relevant CNS pathology, as described in the protocol.
4. A malignancy other than NHL (inclusion diagnosis) unless the participant is adequately and definitively treated and is cancer free for at least 3 years, with the exception of localized prostate cancer treated with hormone therapy or local radiotherapy (ie, pellets), cervical carcinoma in situ, breast cancer in situ, or nonmelanoma skin cancer that was definitively treated.
5. Any other significant active disease or medical condition that could interfere with the conduct of the study or put the participant at significant risk, as described in the protocol.
6. Allergy/hypersensitivity to study drugs or excipients. as described in the protocol.
7. Active infection as defined in the protocol.

Note: Other protocol-defined Inclusion/Exclusion criteria apply
"""
