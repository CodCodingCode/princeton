"""A Trial to Learn if Odronextamab is Safe and Well-Tolerated and How Well it Works Compared to Rituximab Combined With Different Types of Chemotherapy for Adult Participants With Previously Untreated Follicular Lymphoma

NCT: NCT06091254
Phase: Phase 3
CT.gov conditions: ['Follicular Lymphoma (FL)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06091254',
    title='A Trial to Learn if Odronextamab is Safe and Well-Tolerated and How Well it Works Compared to Rituximab Combined With Different Types of Chemotherapy for Adult Participants With Previously Untreated Follicular Lymphoma',
    phase='Phase 3',
    setting='A Trial to Learn if Odronextamab is Safe and Well-Tolerated and How Well it Works Compared to Rituximab Combined With Different Types of Chemotherapy for Adult Participants With Previously Untreated Follicular Lymphoma',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let me start by going through each part of the problem step by step. The user provided the raw eligibility criteria for a trial, and I need to map that into the specified JSON schema. Let\'s take each field one by one.\\n\\nFirst, requires_advanced_disease. Looking at the Key Inclusion Criteria, co"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Diagnosis of Cluster of Differentiation 20\^+ (CD20\^+) FL Grade 1-3a, stage II bulky or stage III / IV
2. Need for treatment as described in the protocol
3. Have measurable disease on cross-sectional imaging documented by diagnostic imaging Computed Tomography (CT) or Magnetic Resonance Imaging (MRI)
4. Eastern Cooperative Oncology Group (ECOG) performance status of 0-2
5. Adequate bone marrow function and hepatic function, as described in the protocol

Key Exclusion Criteria:

1. Central Nervous System (CNS) lymphoma or leptomeningeal lymphoma
2. Histological evidence of transformation to a high-grade or diffuse large B-cell lymphoma
3. Waldenström Macroglobulinemia (WM, lymphoplasmacytic lymphoma), Grade 3b follicular lymphoma, chronic lymphocytic leukemia, or small lymphocytic lymphoma
4. Treatment with any systemic anti-lymphoma therapy
5. Infections and allergy/hypersensitivity to study drug or excipient, as described in the protocol

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
