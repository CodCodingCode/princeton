# Synthetic Oncology Patient Dataset - VLM Edition (Polished)

**Patient (canonical):** Margaret A. O'Brien, DOB 03/15/1957, F
**Primary Dx:** Non-Small Cell Lung Cancer (Adenocarcinoma), EGFR exon 19 deletion
**Disease course:** Stage IIIB → IV (progression with CNS and bone mets)
**Time span:** Jun 2023 - Feb 2026

> ⚠️ **ALL DATA IS 100% SYNTHETIC.** No real PHI. Any resemblance to a real patient is coincidental. Do not use for clinical decisions. Names, MRNs, accession numbers, providers, and facilities are fabricated.

---

## Dataset composition

A deliberately messy, multi-source synthetic oncology record designed to stress-test data extraction and summarization pipelines (both text-only LLMs and VLMs) against the real-world pain points that make oncology abstraction hard.

**24 files across four modalities:**
- 15 born-digital PDF reports
- 6 rasterized page images (simulating scanned-into-EHR and faxed documents)
- 1 longitudinal CSV (labs)
- 1 raw OCR'd text file (the faxed outside record)
- 1 canonical answer key (`GROUND_TRUTH.json`)
- This README

---

## File inventory

### Text-extractable PDFs (15 reports)
| # | File | Chart embedded? | Source |
|---|---|---|---|
| 01 | `01_demographics_registration.pdf` | - | Hospital admit form |
| 02 | `02_pathology_initial_AMENDED.pdf` | - | Academic path lab (amended) |
| 03 | `03_pathology_IHC_addendum.pdf` | - | Same path lab, addendum |
| 04 | `04_foundationone_cdx_report.pdf` | - | Foundation Medicine vendor |
| 05 | `05_ct_chest_abdo_pelvis_staging.pdf` | - | In-house radiology |
| 06 | `06_pet_ct_staging.pdf` | - | In-house radiology |
| 07 | `07_brain_mri_with_contrast.pdf` | - | Outside imaging center |
| 08 | `08_med_onc_initial_consult.pdf` | - | Medical oncology EHR |
| 09 | `09_chemo_infusion_flowsheet.pdf` | **Weight trend chart** | Infusion center (landscape) |
| 10 | `10_restaging_ct_progress_note.pdf` | **4-point CEA response chart** | Med onc follow-up |
| 13 | `13_liquid_biopsy_guardant360.pdf` | **VAF bar chart** | Guardant Health |
| 14 | `14_ed_visit_headache.pdf` | - | ED EHR |
| 15 | `15_hospital_discharge_summary.pdf` | **11-point CEA on-treatment chart** | Inpatient EHR |

### Rasterized page images (for VLM benchmarking)
| File | Description |
|---|---|
| `03_pathology_IHC_addendum_p1.png` | 200 DPI grayscale - simulates scanned-into-EHR |
| `09_chemo_infusion_flowsheet_p1.png` / `_p2.png` | 200 DPI grayscale landscape flowsheet |
| `14_ed_visit_headache_p1.png` | 200 DPI grayscale |
| `11_outside_records_FAXED_p1.png` through `_p4.png` | Fake-scanned fax: 150 DPI grayscale, 1° tilt, scanner noise, toner artifacts (alpha-blended, not opaque), paper tint, transmission header/footer |

### Structured / raw text
| File | Description |
|---|---|
| `11_outside_records_FAXED.txt` | Pre-OCR-corrupted text version - kept for comparison with the new scanned images |
| `12_labs_longitudinal.csv` | 98 lab rows spanning 06/2023 – 01/2026 |
| `GROUND_TRUTH.json` | Canonical structured truth - 7 top-level sections |

---

## Embedded charts - what each tests

All charts are derived exclusively from synthetic values already present elsewhere in the dataset. No external data, no copyright issues, no chart-vs-text inconsistencies.

| Chart | Doc | Data source | VLM task |
|---|---|---|---|
| **CEA response trend** (4 points) | 10 | CSV, 07/2023 – 01/2024 | Read trend line, identify the dashed ULN reference, associate visual decline with "partial response" narrative |
| **CEA on-treatment trend** (11 points) | 15 | CSV, 07/2023 – 07/2025 | Identify the green shaded 1L osimertinib region, read the red dashed "CNS progression (MRI 09/15/25)" event line with annotation arrow, interpret the nadir-then-rise U-shape |
| **Guardant VAF bars** (5 alterations) | 13 | Guardant text | Distinguish bars-as-VAF from the hatched MET-as-copy-number bar, read colored categorical styling (red=acquired resistance, navy=founder, etc.), parse italicized subtitles under each bar |
| **Weight trend line** (24 points) | 09 | Flowsheet | Read a long time series, recognize the 1L→2L color transition at 10/15/25, read the "-8.3 kg over ~30 mo" annotation |

---

## Polished in this edition

This release corrects defects found in an earlier pass:

1. **Doc 15 CEA chart** - previously included a post-discharge data point (10/15/25 from the CSV, but discharge was 10/03/25). Now trimmed to pre-admission data only; CNS progression is marked as a dashed vertical line at the MRI date (09/15/25) rather than as a phantom data point. Caption reworded to describe only what the chart actually shows.
2. **Fake scanned fax** - previously had four bugs: (a) literal `[PAGE N OF 4]` source-file markers visible in body text; (b) toner-artifact function used opaque `paste()` that completely obliterated 3 lines on page 4 and the WBC/Hgb lab values on page 3; (c) no synthetic watermark on the weight chart. All three fixed: markers stripped, toner artifacts now use ~45% alpha-blended overlays with rounded soft edges (lightens without obliterating), watermarks consistent across all four charts.
3. **All rendering defects from prior audit** remain fixed: HTML tag leaks (`<b>`, `&lt;`), unsupported Unicode black boxes (`SpO■` → `SpO₂`), header cell overflows, column width issues in the flowsheet, BSA superscript, Guardant Dx field overflow, FoundationOne header/subtitle collision.
4. **Chart data accuracy verified programmatically** - all CEA, weight, and VAF values cross-checked against the CSV and Guardant report text. Zero mismatches.

---

## Three ways to consume the dataset

| Mode | Inputs | Tests |
|---|---|---|
| **Text-only LLM** | 15 PDFs + CSV + `11_*.txt` | Text extraction, table understanding, timeline reconstruction |
| **VLM, mixed-modality** | PNGs for 03/09/11/14 + PDFs for the rest | Real OCR on scans, chart reading, clean PDF parsing - matches real hospital data lake heterogeneity |
| **VLM, fully-scanned** | Rasterize every PDF to 300 DPI and feed images only | Hardest setting: no text stream, VLM must do everything visually |

`GROUND_TRUTH.json` is identical across all three modes.

---

## Known "gotchas" (all intentional, preserved from original design)

1. **Doc 01 DOB typo** - `03/15/1975` instead of `1957`. Every other doc has 1957.
2. **Doc 02 amendment** - original signed 22-JUN-2023 reports Stage IIIA; amendment 25-JUN-2023 corrects to IIIB. Both versions present in text.
3. **Doc 02 vs 03 unit drift** - same lesion reported as 2.8 cm and 28 mm respectively.
4. **Doc 05 vs 08 nodal disagreement** - CT report says station 4R only; med onc consult says station 7. Doc 10's MDT note resolves to 4R + 7 after PET-CT.
5. **Doc 08 PD-L1 pending** - consult records PD-L1 as "pending"; actual result is in doc 03 four days later.
6. **Doc 11 OCR corruption** - `0'Brien`/`0'8rien`, `Margret`, `EGFF`, `adenocarcinonna`, `l` ↔ `1`, `rn` ↔ `m`, `O` ↔ `0`. Now rendered at the pixel level in the PNG versions (VLM must actually OCR them rather than receive pre-corrupted Unicode).
7. **Doc 11 MRN drift** - outside facility uses `44-2019-C`, main hospital uses `10284756`, imaging center uses `CVI-2023-11872`.
8. **Doc 12 CSV reference range drift** - creatinine and CA 19-9 have different ref ranges depending on lab source (UVA vs LabCorp). One CA 19-9 row at the end is flagged by the lab as a unit error (ng/mL instead of U/mL).
9. **Doc 13 emergent T790M** - acquired resistance to osimertinib visible in the VAF chart (red bar). Clinically drives the 2L regimen switch.
10. **Name/capitalization variants** - `O'Brien`, `OBRIEN`, `Obrien`, `O Brien`, `Margret` (typo), `Maggie` (nickname).

---

*Generated as a testing artifact. Not for clinical use. 100% synthetic.*
