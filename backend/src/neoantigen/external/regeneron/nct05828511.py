"""A Window of Opportunity Trial to Learn if Linvoseltamab is Safe and Well Tolerated, and How Well it Works in Adult Participants With Recently Diagnosed Multiple Myeloma Who Have Not Already Received Treatment

NCT: NCT05828511
Phase: Phase 1/Phase 2
CT.gov conditions: ['Multiple Myeloma']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05828511',
    title='A Window of Opportunity Trial to Learn if Linvoseltamab is Safe and Well Tolerated, and How Well it Works in Adult Participants With Recently Diagnosed Multiple Myeloma Who Have Not Already Received Treatment',
    phase='Phase 1/Phase 2',
    setting='A Window of Opportunity Trial to Learn if Linvoseltamab is Safe and Well Tolerated, and How Well it Works in Adult Participants With Recently Diagnosed Multiple Myeloma Who Have Not Already Received Treatment',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by understanding the task. I need to convert the raw eligibility criteria from ClinicalTrials.gov into a specific JSON structure. The user provided the NCT ID, phase, conditions, age bounds, and the raw text. Let me go through each part carefully.\\n\\nFirst, the requirements. The JSON"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group (ECOG) performance status of 0, 1, or 2
2. Confirmed diagnosis of symptomatic Multiple Myeloma (MM) by International Myeloma Working Group (IMWG) diagnosis criteria, as described in the protocol
3. Response-evaluable myeloma, according to the 2016 IMWG response criteria, as defined in the protocol
4. No prior therapy for MM, with the exception of prior emergent or palliative radiation and up to 1 month of single-agent corticosteroids, with washout periods as per the protocol
5. Participants must have evidence of adequate bone marrow reserves and hepatic, renal and cardiac function as defined in the protocol
6. Participants must be age \<70 and have adequate hepatic, renal, pulmonary and cardiac function to be considered transplant-eligible. The specific thresholds for adequate organ function are as per institutional guidance.

Key Exclusion Criteria:

1. Receiving any concurrent investigational agent with known or suspected activity against MM, or agents targeting the A proliferation-inducing ligand (APRIL)/ Transmembrane activator and calcium modulator and cyclophilin ligand interactor (TACI)/BCMA axis
2. Known Central Nervous System (CNS) involvement with MM, known or suspected Progressive Multifocal Leukoencephalopathy (PML), a history of neurocognitive conditions, or CNS movement disorder, or history of seizure within 12 months prior to study enrollment
3. Rapidly progressive symptomatic disease, (e.g. progressing renal failure or hypercalcemia not responsive to standard medical interventions), in urgent need of treatment with chemotherapy
4. Diagnosis of non-secretory MM, active plasma cell leukemia primary light-chain (AL) amyloidosis, Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or known POEMS syndrome (Plasma cell dyscrasia with polyneuropathy, Organomegaly, Endocrinopathy, Monoclonal protein, and Skin changes)

Note: Other protocol-defined Inclusion/Exclusion criteria apply
"""
