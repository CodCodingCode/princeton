"""Path constants for the frontend. No neoantigen imports — safe to load before dotenv."""

from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
SAMPLE_DIR = BACKEND_DIR / "sample_data"
OUT_DIR = BACKEND_DIR / "out"

DEMO_VCF = SAMPLE_DIR / "tcga_skcm_demo.vcf"
DEMO_SLIDE = SAMPLE_DIR / "tcga_skcm_demo_slide.jpg"
CASES_ROOT = BACKEND_DIR / "data" / "tcga_skcm" / "cases"
