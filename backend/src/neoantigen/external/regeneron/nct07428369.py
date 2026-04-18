"""A Study of Linvo-VR vs DVRd in Transplant-Eligible Adult Participants With Newly Diagnosed Multiple Myeloma (NDMM)

NCT: NCT07428369
Phase: Phase 2/Phase 3
CT.gov conditions: ['Multiple Myeloma (MM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: NOT_YET_RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT07428369',
    title='A Study of Linvo-VR vs DVRd in Transplant-Eligible Adult Participants With Newly Diagnosed Multiple Myeloma (NDMM)',
    phase='Phase 2/Phase 3',
    setting='A Study of Linvo-VR vs DVRd in Transplant-Eligible Adult Participants With Newly Diagnosed Multiple Myeloma (NDMM)',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, I need to parse the eligibility criteria for this multiple myeloma trial. Let\'s go through each field step by step.\\n\\nStarting with requires_advanced_disease: The problem states it\'s for Newly Diagnosed Multiple Myeloma (NDMM), so they\'re not advanced. Wait, but NDMM can be any stage. Let\'s che"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Participants must have a histologically or cytologically confirmed diagnosis of multiple myeloma, which requires the presence of clonal bone marrow plasma cells ≥10% or biopsy-proven bony or extramedullary plasmacytoma, and at least one other criteria as defined by the SLiM (\>=60%, Light chains I/U \>10, Magnetic resonance imaging \>1 focal lesion) CRAB (Calcium elevation, Renal insufficiency, Anemia, Bone disease) criteria
2. Participants must have measurable disease, as defined in the protocol
3. Participants must be considered eligible for high-dose chemotherapy (melphalan) and ASCT per local standard guidelines
4. Eastern Cooperative Oncology Group (ECOG) performance status ≤2
5. Must be willing to defer ASCT

Key Exclusion Criteria:

1. Any prior therapy for Monoclonal Gammopathy of Undetermined Significance (MGUS), Monoclonal Gammopathy of Renal Significance (MGRS), Smoldering Multiple Myeloma (SMM), or MM, with the exception of those defined in the protocol
2. Participants who have received or are receiving any investigational agent or cell therapy with known or suspected activity against MM (or another plasma cell disorder), or those whose AEs due to agents administered earlier (such as radiation and/or corticosteroids) have not recovered to a severity of grade 0 or grade 1
3. Participants with non-secretory MM, diagnosis of plasma cell leukemia (\>20% circulating plasma cells), symptomatic amyloidosis (including myeloma associated amyloidosis), Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or POEMS syndrome (Polyneuropathy, Organomegaly, Endocrinopathy, Monoclonal protein, and Skin changes).
4. Participants who have known Central Nervous System (CNS) or meningeal involvement with MM or known or suspected Progressive Multifocal Leukoencephalopathy (PML), a history of a neurocognitive condition or CNS movement disorder, OR a history of seizure, Transient Ischemic Attack (TIA), or stroke within 12 months prior to study randomization
5. Another malignancy besides MM that is progressive or has required treatment in the 3 years preceding randomization with the exceptions defined in the protocol

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
