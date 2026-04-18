"""A Study to Examine the Effects of Novel Therapy Linvoseltamab in Combination With Other Cancer Treatments for Adult Patients With Multiple Myeloma That is Resistant to Current Standard of Care Treatments

NCT: NCT05137054
Phase: Phase 1
CT.gov conditions: ['Multiple Myeloma']
Mapped cancer_types: ['multiple_myeloma']
Overall status: RECRUITING
Generated: 2026-04-18 by scripts/scrape_regeneron_trials.py
"""

from ..regeneron_rules import TrialRule

TRIAL = TrialRule(
    nct_id='NCT05137054',
    title='A Study to Examine the Effects of Novel Therapy Linvoseltamab in Combination With Other Cancer Treatments for Adult Patients With Multiple Myeloma That is Resistant to Current Standard of Care Treatments',
    phase='Phase 1',
    setting='A Study to Examine the Effects of Novel Therapy Linvoseltamab in Combination With Other Cancer Treatments for Adult Patients With Multiple Myeloma That is Resistant to Current Standard of Care Treatments',
    cancer_types=frozenset(['multiple_myeloma']),
    min_age_years=18,
    never_in_tcga_gates=['Kimi structuring failed: ValueError: model JSON failed StructuredPredicates validation after retry: model did not return valid JSON: "Okay, let\'s tackle this problem step by step. The user wants me to fill out a specific JSON schema based on the eligibility criteria for a clinical trial. Let\'s start by understanding what each field requires.\\n\\nFirst, the requirements: The trial is for multiple myeloma, Phase 1. The raw eligibility "'],
    scraped_at='2026-04-18',
)

_RAW_ELIGIBILITY = """
General Key Inclusion Criteria:

1. Eastern Cooperative Oncology Group (ECOG) performance status ≤1
2. Participants must have measurable disease as defined in the protocol according to International Myeloma Working Group (IMWG) consensus criteria
3. Adequate creatinine clearance, hematologic function and hepatic function, as defined in protocol
4. Life expectancy of at least 6 months.

Cohort Specific Inclusion Criteria:

For cohorts 1-6, each participant must have RRMM with progression following at least 3 lines of therapy, or at least 2 lines of therapy and either prior exposure to at least 1 anti-CD38 antibody, 1 immunomodulatory imide drug (IMiD) and 1 proteasome inhibitor (PI), or double-refractory to 1 PI and 1 IMiD, or the combination of 1 PI and 1 IMiD.

Cohort 1: Prior treatment with daratumumab is allowed if previously tolerated. However, participants enrolled in the expansion portion cannot be refractory to an anti-CD38 antibody containing regimen. In addition, all participants must have at least a 6-month washout from prior anti-CD38 antibody therapy.

Cohort 2: Prior treatment with carfilzomib is allowed if previously tolerated at the approved full dose. Carfilzomib-refractory participants may enroll in the dose finding portion provided they are triple-class refractory (PI, IMiD, anti-CD38 antibody). However, participants enrolled in the dose expansion portion cannot be refractory to carfilzomib. In addition, all participants must have at least a 6-month washout from prior carfilzomib therapy.

Cohort 3: Prior treatment with lenalidomide is allowed if previously tolerated at the approved full dose. However, a participant cannot be refractory to any combination regimen that included 25 mg of lenalidomide. In addition, participants must have at least a 6-month washout from any prior lenalidomide therapy (including maintenance therapy).

Cohort 4: Prior treatment with bortezomib is allowed if previously tolerated at the approved full dose. Bortezomib-refractory participants may enroll in the dose finding portion provided they are triple-class refractory (PI, IMiD, anti-CD38 antibody). However, participants enrolled in the dose expansion portion cannot be refractory to bortezomib. In addition, all participants must have at least a 6-month washout from prior bortezomib therapy.

Cohort 5: Prior treatment with pomalidomide is allowed if previously tolerated at the approved full dose. Additionally, participants must undergo at least a 6-month washout following prior pomalidomide therapy before enrollment.

Cohort 6: Prior treatment with isatuximab is allowed if previously tolerated. Additionally, participants must undergo at least a 3-month washout following prior anti-CD38 antibody therapy before enrollment.

Cohort 7 and 8: RRMM with progressive disease and received at least 3 lines of therapy including exposure to at least 1 anti-CD38 antibody, 1IMiD, and 1 PI or triple-class refractory disease (anti-CD38 antibody, IMiD, PI).

Cohort 9: Progressive RRMM in participants with triple-class refractory disease (anti-CD38 antibody, IMiD, PI) after at least 3 lines of therapy Cohort 10: Progressive RRMM after at least 3 lines of therapy including exposure to at least 1 anti-CD38 antibody, 1 IMiD, and 1 PI.

General Key Exclusion Criteria:

1. Diagnosis of plasma cell leukemia, primary light-chain amyloidosis (excluding myeloma associated amyloidosis), Waldenström macroglobulinemia (lymphoplasmacytic lymphoma), or POEMS syndrome (polyneuropathy, organomegaly, endocrinopathy, monoclonal protein, and skin changes)
2. Participants with known MM brain lesions or meningeal involvement
3. Treatment with any systemic anti-myeloma therapy within 5 half-lives or within 21 days prior to first administration of study drug regimen, whichever is shorter
4. History of allogeneic and autologous stem cell transplantation, as described in the protocol
5. Unless stated otherwise in a specific sub-protocol, prior treatment with a T cell-based immunotherapy directed against BCMA bispecific antibodies and bispecific T-cell engagers (BiTEs), and BCMA chimeric antigen receptor (CAR) T cells (Note: BCMA antibody-drug conjugates are not excluded)
6. History of progressive multifocal leukoencephalopathy, neurodegenerative condition or central nervous system (CNS) movement disorder or participants with a history of seizure within 12 months prior to study enrollment are excluded
7. Live or attenuated vaccination within 28 days prior to first study drug regimen administration with a vector that has replicative potential
8. Cardiac ejection fraction \<40% by echocardiogram (Echo) or multigated acquisition (MUGA) scan.

Cohort Specific Exclusion Criteria:

Cohort 2:

1\. Dose expansion: Prior treatment with a B-cell maturation antigen (BCMA) -directed CAR T-cell therapy will not be exclusionary if completed at least 12 weeks prior to first study treatment

Cohort 3:

1\. Known malabsorption syndrome or pre-existing gastrointestinal (GI) condition that may impair absorption of lenalidomide; delivery of lenalidomide via nasogastric tube or gastrostomy tube is not allowed.

Cohort 4:

1\. Peripheral neuropathy grade ≥2

Cohort 5:

1\. Known malabsorption syndrome or pre-existing GI conditions that may impair absorption of pomalidomide; delivery of pomalidomide via nasogastric tube or gastrostomy tube is not allowed.

Cohort 7:

1. Prior treatment with anti-lymphocyte activation gene 3 (LAG-3) agents. Prior exposure to vaccine therapies or other immune checkpoint modulating therapies such as anti-programmed cell death protein 1 (PD-1) antibodies is permitted, as described in the protocol.
2. Ongoing or recent (within 2 years) evidence of an autoimmune disease that has required systemic treatment with immunosuppressive agents, as described in the protocol.
3. Prior solid organ transplant.
4. History of grade ≥3 immune-mediated adverse events (with the exclusion of endocrinopathies that are fully controlled by hormone replacement) from prior checkpoint inhibitor therapies.

Cohort 8:

1. Prior treatment with anti-PD-1 or anti-PD-L1 agents. Prior exposure to vaccine therapies or other immune checkpoint modulating therapies such as anti-cytotoxic T lymphocyte-associated antigen 4 (CTLA-4) antibodies is permitted, as described in the protocol.
2. Encephalitis or meningitis in the year prior to enrollment.
3. History of interstitial lung disease (eg, idiopathic pulmonary fibrosis or organizing pneumonia), of active, noninfectious pneumonitis that required immune-suppressive doses of glucocorticoids to assist with management, or of pneumonitis within the last 5 years. A history of radiation pneumonitis in the radiation field is permitted as long as pneumonitis resolved ≥6 months prior to enrollment.
4. Ongoing or recent (within 2 years) evidence of an autoimmune disease that has required systemic treatment with immunosuppressive agents, as described in the protocol.
5. Prior solid organ transplant.
6. History of grade ≥3 immune-mediated adverse events (with the exclusion of endocrinopathies that are fully controlled by hormone replacement) from prior checkpoint inhibitor therapies.

Cohort 9:

1. Abnormal QT interval corrected by Fridericia's formula (QTcF), as described in the protocol
2. Use of concomitant medications that are known to prolong the QT/QTcF interval including Class Ia and Class III antiarrhythmics at the time of informed consent
3. Ongoing use or anticipated use of food or drugs that are known strong/moderate cytochrome P450 (CYP)3A4 inhibitors, or strong CYP3A inducers within 14 days prior to first dose of nirogacestat
4. Known malabsorption syndrome or existing gastrointestinal GI condition that may impair absorption of nirogacestat; delivery of nirogacestat via nasogastric tube or gastrostomy tube is not allowed.

Cohort 10:

1. Known or suspected active Epstein-Barr virus (EBV) infection.
2. Known history of Hemophagocytic lymphohistiocytosis/Macrophage activation syndrome (HLH/MAS).
3. Prior treatment with cevostamab or another agent with the same target \[Fragment crystallizable receptor-like 5 (FcRH5)\].

NOTE: Other protocol defined inclusion/exclusion criteria apply
"""
