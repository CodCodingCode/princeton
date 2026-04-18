"""Phase 1/2 Study of Linvoseltamab in Adult Patients With Relapsed or Refractory Multiple Myeloma

NCT: NCT03761108
Phase: Phase 1/Phase 2
CT.gov conditions: ['Multiple Myeloma']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT03761108',
    title='Phase 1/2 Study of Linvoseltamab in Adult Patients With Relapsed or Refractory Multiple Myeloma',
    phase='Phase 1/Phase 2',
    setting='Phase 1/2 Study of Linvoseltamab in Adult Patients With Relapsed or Refractory Multiple Myeloma',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: \'Okay, I need to analyze the provided eligibility criteria for the clinical trial NCT03761108 and fill in the JSON schema correctly. Let me start by going through each required field.\\n\\nStarting with "requires_advanced_disease". The inclusion criteria mention that patients must be relapsed or refracto\''],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group (ECOG) performance status ≤ 1
2. Confirmed diagnosis of active Multiple Myeloma (MM) by International Myeloma Working Group (IMWG) diagnostic criteria
3. Patients must have myeloma that is response-evaluable according to the 2016 IMWG response criteria as defined in the protocol.

   * Phase 1, Part 1 (Dose Escalation): Patients with MM who have exhausted all therapeutic options that are expected to provide meaningful clinical benefit, either through disease relapse, treatment refractory disease or intolerance of the therapy and including either:

     a. Progression on or after at least 3 lines of therapy, or intolerance of therapy, including a proteasome inhibitor, an Immunomodulatory agent (IMiD), and an anti-CD38 antibody, OR b. Progression on or after an anti-CD38 antibody and have disease that is "double refractory" to a proteasome inhibitor and an IMiD, or intolerance of therapy. The anti-CD38 antibody may have been administered alone or in combination with another agent such as a proteasome inhibitor (PI). Refractory disease is defined as lack of response or relapse within 60 days of last treatment.
   * Phase 1, Part 2 (SC Administration): Patients with MM whose disease meets the following criteria:

     a. Progression on or after at least 3 prior lines of therapy including a(n) PI, IMiD, and anti-CD38 antibody, OR b. Patients must be triple-refractory, defined as being refractory to prior treatment with at least 1 anti-CD38 antibody, a proteasome inhibitor, and an IMiD.
   * Phase 2 (Cohorts 1 and 2):

   Patients with MM whose disease meets the following criteria:

   a. Progression on or after at least 3 prior lines of therapy including a(n) PI, IMiD, and anti-CD38 antibody, OR b. Patients must be triple- refractory, defined as being refractory\* to prior treatment with at least 1 PI, 1 IMiD, and an anti-CD38 antibody.
   * Phase 2 (Cohort 3):

   Patients with MM whose disease meets the following criteria:
   1. Progression on or after at least 3 prior lines of therapy including a(n) PI, IMiD, and anti-CD38 antibody, OR
   2. Patients must be triple- refractory, defined as being refractory\* to prior treatment with at least 1 PI, 1 IMiD, and an anti-CD38 antibody.

      * Refractory disease is defined as progression during treatment or within 60 days after completion of therapy, or \<25% response to therapy.

   AND, for ALL patients, if they have relapsed after a BCMA-directed CAR-T cellular therapy then:

   • Treatment with a CAR-T must have been associated with a response of PR or better, and

   • If CAR-T cellular therapy was the most recent prior therapy, excluding corticosteroids, then treatment must have been a minimum of 60 days prior to treatment with linvoseltamab.

   Key Exclusion Criteria:

1\. Diagnosis of plasma cell leukemia, primary systemic light-chain amyloidosis, (excluding myeloma-associated amyloidosis), Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or POEMS syndrome (polyneuropathy, organomegaly, endocrinopathy, monoclonal protein, and skin changes) 2. Patients with known MM brain lesions or meningeal involvement 3. Cardiac ejection fraction \<40% by echocardiogram or multi-gated acquisition scan (MUGA) 4. Prior treatment with BCMA-directed immunotherapies, including BCMA bispecific antibodies and BiTEs. Note: BCMA antibody-drug conjugates are not excluded and BCMA-directed CAR-T treatment is not excluded in Phase 2 Cohort 3.

5\. History of allogeneic stem cell transplantation at any time, or autologous stem cell transplantation within 12 weeks of the start of study treatment

Note 1: Other protocol defined inclusion / exclusion criteria apply Note 2: US sites are active but currently not enrolling
"""
