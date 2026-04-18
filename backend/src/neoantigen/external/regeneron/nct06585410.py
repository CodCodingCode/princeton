"""Study of Intralesional Cemiplimab in Adult Patients With Early Stage Cutaneous Squamous Cell Carcinoma

NCT: NCT06585410
Phase: Phase 3
CT.gov conditions: ['Cutaneous Squamous Cell Carcinoma (CSCC)']
Mapped cancer_types: ['other']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT06585410',
    title='Study of Intralesional Cemiplimab in Adult Patients With Early Stage Cutaneous Squamous Cell Carcinoma',
    phase='Phase 3',
    setting='Study of Intralesional Cemiplimab in Adult Patients With Early Stage Cutaneous Squamous Cell Carcinoma',
    cancer_types=frozenset(['other']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s go step by step through the problem. The task is to convert the raw eligibility criteria into a specific JSON structure. Let\'s start by understanding each field in the schema and how to map the given information to them.\\n\\nFirst, the requirements. The user provided the NCT ID, phase, cond"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participants who have a histologically confirmed invasive CSCC TL, as described in the protocol
2. Participants who have CSCC TL ≥1 cm and ≤2.0 cm (longest diameter) located in either the Head or Neck (HN), hand, or pre-tibial surface, as described in the protocol
3. Participants who are judged to be eligible for surgical resection of their CSCC TL and the method of planned surgical resection would be Micrographically oriented histographic surgery (Mohs) or other surgical method of Complete Margin Assessment (CMA). Participants for whom the planned surgery is surgical excision without margin control are not eligible
4. Eastern Cooperative Oncology Group (ECOG) performance status (PS) ≤1
5. Adequate hepatic, renal and bone marrow functions, as described in the protocol

Key Exclusion Criteria:

1. Participant in which the TL is a keratoacanthoma (KA), adenosquamous carcinoma, desmoplastic carcinoma, basal cell carcinoma, basosquamous.carcinoma, Bowen's disease, or CSCC in situ without an invasive component. (Note: For participants with invasive CSCC with a minor basaloid component, the patient may be eligible after discussion with the sponsor medical director.)
2. Ongoing or recent (within 5 years) evidence of significant autoimmune disease that required treatment with systemic immunosuppressive treatments, which may suggest risk for Immune-mediated Adverse Events (imAEs), as described in the protocol
3. History of non-infectious pneumonitis within the last 5 years
4. TL (lesion planned for intralesional therapy) or other non-target CSCC lesion in dry red lip (vermillion), oral cavity, or nasal mucosa

NOTE: Other protocol defined inclusion / exclusion criteria apply.
"""
