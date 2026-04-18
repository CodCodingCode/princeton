"""A Trial to Learn How Well Linvoseltamab Works Compared to the Combination of Elotuzumab, Pomalidomide and Dexamethasone for Adult Participants With Relapsed/Refractory Multiple Myeloma

NCT: NCT05730036
Phase: Phase 3
CT.gov conditions: ['Relapsed Refractory Multiple Myeloma (RRMM)']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05730036',
    title='A Trial to Learn How Well Linvoseltamab Works Compared to the Combination of Elotuzumab, Pomalidomide and Dexamethasone for Adult Participants With Relapsed/Refractory Multiple Myeloma',
    phase='Phase 3',
    setting='A Trial to Learn How Well Linvoseltamab Works Compared to the Combination of Elotuzumab, Pomalidomide and Dexamethasone for Adult Participants With Relapsed/Refractory Multiple Myeloma',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s start by analyzing the problem. The user wants me to create a structured JSON based on the eligibility criteria from a clinical trial. The trial is sponsored by Regeneron, so I need to check if the drug is related to any of the required fields.\\n\\nFirst, look at the required fields. The ma"'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Age 18 years or older (or legal adult age in the country) at the time of the screening visit.
2. Eastern Cooperative Oncology Group (ECOG) performance status ≤1. Patients with ECOG 2 solely due to local symptoms of myeloma (eg. pain) may be allowed after discussion with the Medical Monitor.
3. Received at least 1 and no more than 4 prior lines of anti-neoplastic MM therapies, including lenalidomide and a proteasome inhibitor and demonstrated disease progression on or after the last therapy as defined by the 2016 IMWG criteria. Participants who have received only 1 line of prior line of antimyeloma therapy must be lenalidomide refractory, as described in the protocol.

   Note: Participants in Israel also must have previously received a CD38 antibody. Participants in the EU and the UK must have previously received 2 to 4 prior lines of therapy, including a CD38 antibody.
4. Patients must have measurable disease for response assessment as per the 2016 IMWG response assessment criteria, as described in the protocol
5. Adequate hematologic function and hepatic function within 7 days of randomization, as well as adequate renal and cardiac function and corrected calcium
6. Life expectancy of at least 6 months

Key Exclusion Criteria:

1. Diagnosis of plasma cell leukemia, amyloidosis, Waldenström macroglobulinemia, or POEMS syndrome (polyneuropathy, organomegaly, endocrinopathy, monoclonal protein, and skin changes).
2. Prior treatment with elotuzumab and/or pomalidomide
3. Participants with known MM brain lesions or meningeal involvement
4. Treatment with any systemic anti-cancer therapy within 5 half-lives or within 28 days before first administration of study drug, whichever is shorter
5. History of allogeneic stem cell transplantation within 6 months, or autologous stem cell transplantation within 12 weeks of the start of study treatment. Participants who have received an allogeneic transplant must be off all immunosuppressive medications for 6 weeks without signs of graft-versus-host disease. Steroids at doses equivalent to suppletion doses may be acceptable.
6. Prior treatment with B-cell maturation antigen (BCMA) directed immunotherapies Note: BCMA antibody-drug conjugates are allowed.
7. History of progressive multifocal leukoencephalopathy (PML), known or suspected PML, or history of a neurocognitive condition or central nervous system (CNS) movement disorder (Parkinson's disease or Parkinsonism).
8. Any infection requiring hospitalization or treatment with IV anti-infectives within 2 weeks of first administration of study drug
9. Uncontrolled infection with human immunodeficiency virus (HIV), hepatitis B virus (HBV) or hepatitis C virus (HCV); or another uncontrolled infection, as defined in the protocol 10 Cardiac ejection fraction \<40%.

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
