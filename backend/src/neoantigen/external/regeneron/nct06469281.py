"""A Study to Learn if 27T51, a Mucin-16 (MUC16) Protein Targeting Immune Cell Therapy, Administered Alone or in Combination is Safe and How Well it Works for Adult Participants With Recurrent or Treatment Resistant Ovarian Cancers

NCT: NCT06469281
Phase: Phase 1
CT.gov conditions: ['Epithelial Ovarian Cancer', 'Primary Peritoneal Carcinoma', 'Fallopian Tube Cancer']
Mapped cancer_types: ['ovarian_carcinoma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06469281',
    title='A Study to Learn if 27T51, a Mucin-16 (MUC16) Protein Targeting Immune Cell Therapy, Administered Alone or in Combination is Safe and How Well it Works for Adult Participants With Recurrent or Treatment Resistant Ovarian Cancers',
    phase='Phase 1',
    setting='A Study to Learn if 27T51, a Mucin-16 (MUC16) Protein Targeting Immune Cell Therapy, Administered Alone or in Combination is Safe and How Well it Works for Adult Participants With Recurrent or Treatment Resistant Ovarian Cancers',
    cancer_types=frozenset(['ovarian_carcinoma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by understanding the user\'s request. They want me to act as an oncology clinical-trial eligibility normalizer. Given the raw text from ClinicalTrials.gov for a Regeneron-sponsored trial and some structured metadata, I need to fill in the provided JSON schema exactly.\\n\\nFirst, I\'ll l"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group (ECOG) performance status ≤ 1
2. Histological diagnosis of epithelial ovarian, primary peritoneal, or fallopian tube cancer according to World of Health Organization (WHO) 2020 classification
3. Recurrent or refractory epithelial ovarian, primary peritoneal, or fallopian tube cancer, as described in the protocol
4. Serum cancer antigen (CA) 125 ≥ 2 × upper limit of normal (ULN) as assessed at the local lab by a 510(k) cleared test at screening
5. Participants must have at least 1 measurable tumor lesion as defined by the response evaluation criteria in solid tumors (RECIST) 1.1.
6. Expected survival ≥ 3 months

Key Exclusion Criteria:

1. Inadequate cardiovascular, renal and hepatic function, as described in the protocol
2. Absolute lymphocyte count (ALC) \< 100 cells/μL at time of leukapheresis
3. History of Grade ≥ 2 hemorrhage within 30 days, or inadequate coagulation parameters, as described in the protocol
4. Known history or presence of clinically relevant central nervous system (CNS) pathology, as described in the protocol
5. Ongoing or recent (within 2 years) evidence of significant autoimmune disease that required treatment with systemic immunosuppressive treatments, which may suggest risk for immune related adverse events (AEs)
6. Treatment with any cellular or gene therapy

Note: Other protocol-defined Inclusion/Exclusion criteria apply
"""
