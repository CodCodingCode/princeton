# Synthetic Oncology Patient Dataset

**Patient (canonical):** Margaret A. O'Brien, DOB 03/15/1957, F
**Primary Dx:** Non-Small Cell Lung Cancer (Adenocarcinoma), EGFR exon 19 deletion
**Disease course:** Stage IIIB → IV (progression with CNS and bone mets)
**Time span:** Jun 2023 - Feb 2026

> ⚠️ **ALL DATA IS 100% SYNTHETIC.** No real PHI. Any resemblance to a real patient is coincidental. Do not use for clinical decisions. Names, MRNs, accession numbers, providers, and facilities are fabricated.

---

## Purpose

This is a deliberately messy, multi-source synthetic oncology record designed to stress-test data extraction, abstraction, and clinical summarization pipelines. It mirrors the real-world pain points that make oncology data abstraction hard:

- **Identifier drift** - patient's name and MRN vary across institutions and systems
- **Document heterogeneity** - structured labs CSV, formal path reports, narrative progress notes, a faxed/OCR'd outside record
- **Amendments and contradictions** - an amended pathology report; contradictory staging in the initial CT vs. the multidisciplinary tumor board note
- **Biomarker data buried in free text** - EGFR, PD-L1, TMB scattered across 3 different reports with different formats
- **Temporal misalignment** - dates in MM/DD/YYYY, DD-MMM-YYYY, ISO, and narrative ("last March") formats
- **Missing data** - a progress note where molecular results are still "pending"
- **Noisy OCR** - simulated faxed-scan document with character substitutions (l↔1, O↔0, rn↔m)
- **Unit inconsistency** - tumor sizes in cm in one report, mm in another; labs with different reference ranges across labs
- **Duplicate-but-different records** - two versions of the same pathology with a date correction

---

## File inventory

| # | File | Source system (simulated) | Format |
|---|---|---|---|
| 01 | `01_demographics_registration.pdf` | Hospital admit/registration | Structured form PDF |
| 02 | `02_pathology_initial_AMENDED.pdf` | Academic pathology lab | Narrative PDF (amended) |
| 03 | `03_pathology_IHC_addendum.pdf` | Same path lab, addendum | Narrative PDF |
| 04 | `04_foundationone_cdx_report.pdf` | Foundation Medicine (vendor) | Genomic report PDF |
| 05 | `05_ct_chest_abdo_pelvis_staging.pdf` | Radiology (in-house) | Dictated report PDF |
| 06 | `06_pet_ct_staging.pdf` | Radiology (in-house) | Dictated report PDF |
| 07 | `07_brain_mri_with_contrast.pdf` | Radiology (outside imaging center) | Dictated report PDF |
| 08 | `08_med_onc_initial_consult.pdf` | Medical oncology EHR | Narrative note PDF |
| 09 | `09_chemo_infusion_flowsheet.pdf` | Infusion center system | Structured flowsheet PDF |
| 10 | `10_restaging_ct_progress_note.pdf` | Med onc follow-up | Narrative note PDF |
| 11 | `11_outside_records_FAXED.txt` | Community oncologist (faxed to us) | Noisy OCR text |
| 12 | `12_labs_longitudinal.csv` | Lab information system export | CSV |
| 13 | `13_liquid_biopsy_guardant360.pdf` | Guardant Health (vendor) | ctDNA report PDF |
| 14 | `14_ed_visit_headache.pdf` | ED EHR | Narrative note PDF |
| 15 | `15_hospital_discharge_summary.pdf` | Inpatient EHR | Narrative note PDF |
| - | `GROUND_TRUTH.json` | - | Canonical structured truth for eval |

---

## Known "gotchas" intentionally planted

Use `GROUND_TRUTH.json` as the answer key when testing extraction.

1. **Document 01 (demographics)** lists DOB as **03/15/1975** - a digit transposition typo. Every other document has **03/15/1957**. Extractors should prefer majority / cross-reference with age.
2. **Document 02 (pathology)** is an **amended** report - the original reported Stage IIIA, the amendment (signed 3 days later) corrects to Stage IIIB after additional nodal review. Both versions present.
3. **Document 02 and 03** use slightly different tumor size measurements (2.8 cm vs. 28 mm) - same lesion.
4. **Document 11 (faxed outside record)** has OCR-grade corruption: "O'Brien" appears as "0'Brien" and "0'8rien"; "EGFR" as "EGFF" in one place; "adenocarcinoma" as "adenocarcinonna". MRN is different (outside facility).
5. **Document 08 (med onc consult)** records PD-L1 as "pending" - the actual result is in Document 03, dated 4 days later.
6. **Document 12 (labs CSV)** includes two labs (creatinine, CA 19-9) with reference ranges from different labs - watch the units column.
7. **Documents 05 and 08** disagree on the mediastinal LN station involved (4R vs. 7) - the MDT in Doc 10 resolves to 4R+7 after PET.
8. **Document 13 (Guardant)** shows EGFR T790M resistance mutation emerging - clinically significant progression biomarker not captured in any narrative note.
9. **Patient name** appears as: "O'Brien", "OBRIEN", "Obrien", "O Brien", "Margret" (typo, Doc 11), "Maggie" (nickname, Doc 08 social hx).
10. **MRNs**: Main hospital `MRN 10284756`. Outside facility `MRN# 44-2019-C`. Imaging center `ACC 7781205`.

---

## Suggested uses

- Benchmarking LLM-based clinical data extraction (biomarker recall, staging accuracy, timeline reconstruction)
- Testing entity resolution / patient matching across disparate identifiers
- Training/evaluating NLP pipelines for oncology abstraction
- Demo data for clinical summarization products
- Educational material for health informatics courses

---

*Generated as a testing artifact. Not for clinical use.*
