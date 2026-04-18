"""A Study With Combinations of Anti-LAG-3 and Anti-PD-1 Antibodies in Adult Participants With Advanced or Metastatic Melanoma (Harmony Head-to-Head)

NCT: NCT06246916
Phase: Phase 3
CT.gov conditions: ['Melanoma']
Mapped cancer_types: ['cutaneous_melanoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06246916',
    title='A Study With Combinations of Anti-LAG-3 and Anti-PD-1 Antibodies in Adult Participants With Advanced or Metastatic Melanoma (Harmony Head-to-Head)',
    phase='Phase 3',
    setting='A Study With Combinations of Anti-LAG-3 and Anti-PD-1 Antibodies in Adult Participants With Advanced or Metastatic Melanoma (Harmony Head-to-Head)',
    cancer_types=frozenset(['cutaneous_melanoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by analyzing the raw eligibility criteria provided. The user is asking to fill in a specific JSON schema based on the data from ClinicalTrials.gov for a Regeneron trial.\\n\\nFirst, I need to check each field in the schema and see what the criteria say.\\n\\nStarting with requires_advanced"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participants with histologically confirmed unresectable stage III and stage IV (metastatic) melanoma per American Joint Committee on Cancer (AJCC), eighth revised edition.
2. Participants must not have received prior systemic therapy for unresectable or metastatic melanoma as described in the protocol.
3. Measurable disease per RECIST version 1.1.
4. Eastern Cooperative Oncology Group (ECOG) performance status (PS) ≤1
5. Adequate bone marrow, hepatic, and kidney function
6. Known B-Rapidly Accelerated Fibrosarcoma protein (BRAF) V600 mutation status or submitted sample for BRAF V600 mutation assessment as described in the protocol

Key Exclusion Criteria:

Medical Conditions:

1. Uveal, acral or mucosal melanoma.
2. Ongoing or recent (within 2 years) evidence of an autoimmune disease that required systemic treatment with immunosuppressive agents as described in the protocol.
3. Uncontrolled infection with human immunodeficiency virus (HIV), hepatitis B (HBV), or hepatitis C virus (HCV) infection; or diagnosis of immunodeficiency that is related to, or results in chronic infection. Mild cancer-related immunodeficiency (such as immunodeficiency treated with gamma globulin and without chronic or recurrent infection) is allowed.

   Prior/Concomitant Therapy:
4. Prior immune checkpoint inhibitor therapy other than anti-PD1/PD-L1 as described in the protocol
5. Systemic immune suppression as described in the protocol.

   Other Comorbidities:
6. Participants with a history of myocarditis.
7. Troponin T (TnT) or troponin I (TnI) \>2x institutional upper limit of normal (ULN).
8. Active or untreated brain metastases or spinal cord compression as described in the protocol.

Note: Other protocol-defined Inclusion/ Exclusion Criteria apply.
"""
