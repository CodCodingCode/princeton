"""A Proof-of-Concept Study to Learn Whether Linvoseltamab Can Eliminate Abnormal Plasma Cells That May Lead to Multiple Myeloma in Adult Patients With High-Risk Monoclonal Gammopathy of Undetermined Significance or Non-High-Risk Smoldering Multiple Myeloma

NCT: NCT06140524
Phase: Phase 2
CT.gov conditions: ['Monoclonal Gammopathy of Undetermined Significance (MGUS)', 'Smoldering Multiple Myeloma (SMM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06140524',
    title='A Proof-of-Concept Study to Learn Whether Linvoseltamab Can Eliminate Abnormal Plasma Cells That May Lead to Multiple Myeloma in Adult Patients With High-Risk Monoclonal Gammopathy of Undetermined Significance or Non-High-Risk Smoldering Multiple Myeloma',
    phase='Phase 2',
    setting='A Proof-of-Concept Study to Learn Whether Linvoseltamab Can Eliminate Abnormal Plasma Cells That May Lead to Multiple Myeloma in Adult Patients With High-Risk Monoclonal Gammopathy of Undetermined Significance or Non-High-Risk Smoldering Multiple Myeloma',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by understanding the problem. The user wants me to create a JSON object based on the provided ClinicalTrials.gov data for a specific trial. The trial is NCT06140524, a Phase 2 study for multiple myeloma conditions, specifically MGUS and SMM. The main task is to fill in all the spec"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. HR-MGUS or NHR-SMM as defined in the protocol
2. Eastern Cooperative Oncology Group (ECOG) performance status ≤1
3. Adequate hematologic and hepatic function, as described in the protocol
4. Estimated glomerular filtration rate (GFR) ≥30 mL/min/1.73 m\^2 by the Modification of Diet in Renal Disease (MDRD) equation

Key Exclusion Criteria:

1. High-risk SMM, as defined in the protocol
2. Evidence of any of myeloma-defining events, as described in the protocol
3. Diagnosis of systemic light-chain amyloidosis, Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), solitary plasmacytoma, or symptomatic MM
4. Clinically significant cardiac or vascular disease within 3 months of study enrollment, as described in the protocol
5. Any infection requiring hospitalization or treatment with intravenous (IV) anti-infectives within 28 days of the first dose of linvoseltamab
6. Uncontrolled Human Immunodeficiency Virus (HIV), Hepatitis B Virus (HBV), or Hepatitis C Virus (HCV) infection; or other uncontrolled infection or unexplained signs of infection, as described in the protocol

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
