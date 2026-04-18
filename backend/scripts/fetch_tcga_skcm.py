"""Pre-build the TCGA-SKCM cohort dataset for the demo.

Pulls open-access data from the NCI Genomic Data Commons (no auth required):

* Per-case clinical fields (vital status, days to death/last follow-up, AJCC
  stage, age at diagnosis, sex).
* The masked somatic mutation MAF (MuTect2 caller) for each TCGA-SKCM case —
  this is open-access since 2018.
* One representative slide thumbnail (PNG, ~80 KB) for the BRAF V600E demo
  patient. We keep only the thumbnail because full SVS slides are 1-3 GB each.

Outputs:
    backend/data/tcga_skcm/clinical.csv
    backend/data/tcga_skcm/mutations.parquet         (all patients, long format)
    backend/data/tcga_skcm/cases.json                (case_id ↔ submitter_id map)
    backend/data/tcga_skcm/demo_slide.jpg            (representative BRAF V600E)
    backend/data/tcga_skcm/demo_patient.txt          (chosen case submitter_id)

Run from the repo root::

    python backend/scripts/fetch_tcga_skcm.py

About 50-150 MB total; run time ~10-20 minutes on a fresh laptop.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
from pathlib import Path

import httpx

GDC = "https://api.gdc.cancer.gov"
PROJECT = "TCGA-SKCM"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "tcga_skcm"


def _post(endpoint: str, payload: dict, *, timeout: float = 60.0) -> dict:
    r = httpx.post(f"{GDC}/{endpoint}", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_cases() -> list[dict]:
    """Return the full TCGA-SKCM case list with clinical fields."""
    fields = [
        "case_id",
        "submitter_id",
        "demographic.gender",
        "demographic.vital_status",
        "demographic.days_to_death",
        "demographic.age_at_index",
        "diagnoses.ajcc_pathologic_stage",
        "diagnoses.days_to_last_follow_up",
        "diagnoses.primary_diagnosis",
        "diagnoses.tumor_grade",
        "diagnoses.site_of_resection_or_biopsy",
    ]
    body = {
        "filters": {
            "op": "in",
            "content": {"field": "project.project_id", "value": [PROJECT]},
        },
        "fields": ",".join(fields),
        "size": 600,
        "format": "JSON",
    }
    print(f"→ fetching {PROJECT} case list…")
    data = _post("cases", body)
    hits = data["data"]["hits"]
    print(f"  got {len(hits)} cases")
    return hits


def write_clinical_csv(cases: list[dict], path: Path) -> None:
    import csv

    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "case_id", "submitter_id", "sex", "vital_status",
            "age_at_diagnosis", "stage",
            "days_to_death", "days_to_last_follow_up",
            "primary_diagnosis", "tumor_grade", "biopsy_site",
        ])
        for c in cases:
            demo = c.get("demographic") or {}
            diag = (c.get("diagnoses") or [{}])[0]
            w.writerow([
                c.get("case_id"),
                c.get("submitter_id"),
                demo.get("gender"),
                demo.get("vital_status"),
                demo.get("age_at_index"),
                diag.get("ajcc_pathologic_stage"),
                demo.get("days_to_death"),
                diag.get("days_to_last_follow_up"),
                diag.get("primary_diagnosis"),
                diag.get("tumor_grade"),
                diag.get("site_of_resection_or_biopsy"),
            ])
    print(f"→ wrote {path}")


def fetch_maf_file_ids() -> list[tuple[str, str, int]]:
    """Find all open-access masked-somatic MAF files for TCGA-SKCM.

    GDC now emits one MAF per aliquot (workflow
    ``Aliquot Ensemble Somatic Variant Merging and Masking``) rather than one
    cohort-wide MAF, so we need to pull them all and concat.
    """
    body = {
        "filters": {
            "op": "and",
            "content": [
                {"op": "in", "content": {"field": "cases.project.project_id", "value": [PROJECT]}},
                {"op": "in", "content": {"field": "data_format", "value": ["MAF"]}},
                {"op": "in", "content": {"field": "data_type", "value": ["Masked Somatic Mutation"]}},
                {"op": "in", "content": {"field": "analysis.workflow_type",
                                        "value": ["Aliquot Ensemble Somatic Variant Merging and Masking"]}},
                {"op": "in", "content": {"field": "access", "value": ["open"]}},
            ],
        },
        "fields": "file_id,file_name,file_size",
        "size": 1000,
        "format": "JSON",
    }
    data = _post("files", body)
    hits = data["data"]["hits"]
    if not hits:
        raise SystemExit(
            "No open-access MAFs found for TCGA-SKCM. The GDC may have re-keyed "
            "workflow names again; check https://portal.gdc.cancer.gov manually."
        )
    total_mb = sum(h["file_size"] for h in hits) / (1024 * 1024)
    print(f"→ MAF files: {len(hits)} aliquots, total {total_mb:.1f} MB")
    return [(h["file_id"], h["file_name"], h["file_size"]) for h in hits]


def download_mafs(file_infos: list[tuple[str, str, int]], chunk_dir: Path) -> list[Path]:
    """Download each per-aliquot MAF into ``chunk_dir``. Skip existing complete files."""
    chunk_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, (fid, fname, fsize) in enumerate(file_infos, 1):
        p = chunk_dir / fname
        if p.exists() and p.stat().st_size == fsize:
            paths.append(p)
            continue
        url = f"{GDC}/data/{fid}"
        print(f"  [{i}/{len(file_infos)}] {fname} ({fsize // 1024} KB)", end="\r")
        with httpx.stream("GET", url, timeout=120.0) as r:
            r.raise_for_status()
            p.write_bytes(r.read())
        paths.append(p)
    print(f"\n  downloaded {len(paths)} MAFs to {chunk_dir}")
    return paths


def parse_mafs_to_parquet(maf_paths: list[Path], out_path: Path) -> None:
    """Read every MAF, concatenate, and stash a slim missense-only parquet."""
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pandas missing — install with: pip install -e './backend[prep]'")

    print(f"→ parsing {len(maf_paths)} MAFs → parquet…")
    frames: list = []
    for p in maf_paths:
        try:
            with gzip.open(p, "rt") as f:
                df = pd.read_csv(
                    f,
                    sep="\t",
                    comment="#",
                    low_memory=False,
                    usecols=[
                        "Hugo_Symbol",
                        "Variant_Classification",
                        "Variant_Type",
                        "HGVSp_Short",
                        "Tumor_Sample_Barcode",
                        "case_id",
                        "t_alt_count",
                        "t_ref_count",
                    ],
                )
        except Exception as e:
            print(f"  ⚠ skipped {p.name}: {type(e).__name__}: {e}")
            continue
        frames.append(df)
    if not frames:
        raise SystemExit("No MAFs parsed — aborting.")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["Variant_Classification"] == "Missense_Mutation"].copy()
    df["vaf"] = df["t_alt_count"] / (df["t_alt_count"] + df["t_ref_count"]).replace(0, 1)
    df["submitter_id"] = df["Tumor_Sample_Barcode"].str.slice(0, 12)
    out = df[["submitter_id", "case_id", "Hugo_Symbol", "HGVSp_Short", "vaf"]].rename(
        columns={"Hugo_Symbol": "gene", "HGVSp_Short": "hgvs_p"}
    )
    out.to_parquet(out_path, index=False)
    print(f"  wrote {out_path} ({len(out)} missense mutations across "
          f"{out['submitter_id'].nunique()} patients)")


def pick_braf_v600e_demo_patient(parquet_path: Path) -> str:
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    # GDC's MuTect2 output annotates BRAF against a longer transcript that
    # numbers residues +40 vs. the canonical UniProt P15056 — V600E appears
    # as p.V640E. Accept both so this keeps working if GDC switches transcripts.
    hgvs = df.hgvs_p.fillna("")
    braf = df[(df.gene == "BRAF") & (hgvs.str.contains("V640E") | hgvs.str.contains("V600E"))]
    if braf.empty:
        raise SystemExit("No BRAF V600E patients found in MAF — unexpected.")
    candidates = braf.submitter_id.value_counts().head(20).index.tolist()
    chosen = candidates[0]
    print(f"→ demo patient: {chosen} (had {(df.submitter_id == chosen).sum()} missense mutations)")
    return chosen


def fetch_demo_slide_thumbnail(submitter_id: str, dest: Path) -> None:
    """Download a slide thumbnail (PNG) for the chosen patient."""
    body = {
        "filters": {
            "op": "and",
            "content": [
                {"op": "in", "content": {"field": "cases.submitter_id", "value": [submitter_id]}},
                {"op": "in", "content": {"field": "data_format", "value": ["SVS"]}},
                {"op": "in", "content": {"field": "experimental_strategy", "value": ["Diagnostic Slide", "Tissue Slide"]}},
            ],
        },
        "fields": "file_id,file_name",
        "size": 1,
    }
    data = _post("files", body)
    hits = data["data"]["hits"]
    if not hits:
        print(f"  no slide for {submitter_id}; skipping thumbnail")
        return
    file_id = hits[0]["file_id"]
    # Slide thumbnail endpoint returns a JPEG ~50–200 KB
    url = f"{GDC}/data/{file_id}?related_files=true"
    print(f"→ pulling slide thumbnail for {submitter_id}…")
    try:
        # The simpler approach: GDC has a slide image preview at /tile but it
        # requires libcucim/openslide on our side. For demo, try the HTSrv
        # preview endpoint which serves a downsized JPEG.
        preview_url = f"https://portal.gdc.cancer.gov/auth/api/data/{file_id}/slide-image"
        r = httpx.get(preview_url, follow_redirects=True, timeout=120.0)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            dest.write_bytes(r.content)
            print(f"  saved thumbnail to {dest} ({len(r.content) // 1024} KB)")
            return
    except Exception as e:
        print(f"  thumbnail download failed ({e}); will fall back to placeholder")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-slide", action="store_true", help="Skip slide thumbnail download")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cases = fetch_cases()
    write_clinical_csv(cases, OUT_DIR / "clinical.csv")

    case_map = [{"case_id": c["case_id"], "submitter_id": c["submitter_id"]} for c in cases]
    (OUT_DIR / "cases.json").write_text(json.dumps(case_map, indent=2))

    file_infos = fetch_maf_file_ids()
    maf_paths = download_mafs(file_infos, OUT_DIR / "maf_chunks")
    parse_mafs_to_parquet(maf_paths, OUT_DIR / "mutations.parquet")

    chosen = pick_braf_v600e_demo_patient(OUT_DIR / "mutations.parquet")
    (OUT_DIR / "demo_patient.txt").write_text(chosen)

    if not args.skip_slide:
        fetch_demo_slide_thumbnail(chosen, OUT_DIR / "demo_slide.jpg")

    print("\n✓ done. Run `python backend/scripts/build_pubmed_rag.py` next.")


if __name__ == "__main__":
    main()
