"""A Trial to Learn How Effective and Safe Odronextamab is Compared to Standard of Care for Adult Participants With Previously Treated Aggressive B-cell Non-Hodgkin Lymphoma

NCT: NCT06230224
Phase: Phase 3
CT.gov conditions: ['B-Cell Non-Hodgkin Lymphoma (B-NHL)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06230224',
    title='A Trial to Learn How Effective and Safe Odronextamab is Compared to Standard of Care for Adult Participants With Previously Treated Aggressive B-cell Non-Hodgkin Lymphoma',
    phase='Phase 3',
    setting='A Trial to Learn How Effective and Safe Odronextamab is Compared to Standard of Care for Adult Participants With Previously Treated Aggressive B-cell Non-Hodgkin Lymphoma',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by analyzing the user\'s problem. They want me to be an oncology clinical-trial eligibility normalizer. The task is to process the raw free-text eligibility criteria from ClinicalTrials.gov for a Regeneron-sponsored trial and fill in a specific JSON schema. The user provided the NCT"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Histologically proven aggressive B-NHL, as described in the protocol. Availability of tumor tissue for submission to central laboratory is required for study enrollment. Archival tumor tissue for histological assessment prior to enrollment is allowed
2. Have primary refractory or relapse 12 months or less (≤) from initiation of frontline therapy Only patients who received 1 prior line of therapy containing an anti-Cluster of Differentiation 20 (CD20) antibody and anthracycline are allowed for enrollment
3. Have measurable disease with at least one nodal lesion with longer diameter (LDi) greater than 1.5 cm or at least one extranodal lesion with LDi greater than 1.0 cm, documented by diagnostic imaging (computed tomography \[CT\] or magnetic resonance imaging \[MRI\])
4. Intent to proceed to autologous stem cell transplant (ASCT), as described in the protocol
5. Eastern Cooperative Oncology Group (ECOG) performance status of 0 to 1
6. Adequate hematologic and organ function.

Key Exclusion Criteria:

1. Primary central nervous system (CNS) lymphoma or known involvement by non-primary CNS NHL, as described in the protocol
2. History of or current relevant CNS pathology, as described in the protocol
3. A malignancy other than NHL unless the participant is adequately and definitively treated and is cancer free for at least 3 years, with the exception of localized prostate cancer, cervical carcinoma in situ, breast cancer in situ, or nonmelanoma skin cancer that was definitively treated
4. Any other significant active disease or medical condition that could interfere with the conduct of the study or put the participant at significant risk, as described in the protocol
5. Wash-out period from prior anti-lymphoma treatments and infections, as described in the protocol
6. Allergy/hypersensitivity to study drug, or excipients.

NOTE: Other protocol defined inclusion / exclusion criteria apply
"""
