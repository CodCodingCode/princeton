"""Build a per-patient TCGA-SKCM dataset for batch testing.

Takes the outputs of ``fetch_tcga_skcm.py`` and fans out into per-case
directories under ``backend/data/tcga_skcm/cases/<submitter_id>/`` with:

    slide.jpg       ← thumbnail from the GDC (skipped if unavailable)
    tumor.vcf       ← minimal SnpEff-ANN VCF synthesized from the MAF parquet
    metadata.json   ← clinical fields for that patient

Missing slides mean the VLM falls back to placeholder, which short-circuits the
NCCN walker, so we prefer cases that actually have a downloadable slide.

Prereq::

    python backend/scripts/fetch_tcga_skcm.py
    python backend/scripts/build_tcga_skcm_cases.py --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from pathlib import Path

import httpx

GDC = "https://api.gdc.cancer.gov"
PROJECT = "TCGA-SKCM"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tcga_skcm"
CASES_DIR = DATA_DIR / "cases"
THUMB_MAX_SIZE = (1024, 1024)  # fed to VLM as base64; larger = slower, zero VLM benefit

AA_ONE_TO_THREE = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys",
    "Q": "Gln", "E": "Glu", "G": "Gly", "H": "His", "I": "Ile",
    "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe", "P": "Pro",
    "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
}
HGVS_SHORT_RE = re.compile(r"^p\.([A-Z])(\d+)([A-Z])$")


def _short_to_three(hgvs_short: str | None) -> str | None:
    """`p.V600E` → `p.Val600Glu`. parser.py's HGVS regex expects three-letter codes."""
    if not hgvs_short:
        return None
    m = HGVS_SHORT_RE.match(hgvs_short)
    if not m:
        return None
    ref1, pos, alt1 = m.groups()
    ref3 = AA_ONE_TO_THREE.get(ref1)
    alt3 = AA_ONE_TO_THREE.get(alt1)
    if not ref3 or not alt3:
        return None
    return f"p.{ref3}{pos}{alt3}"


_VCF_BASES = {"A", "C", "G", "T"}


def _normalize_chrom(c) -> str:
    """MAF Chromosome column is usually `chr1`/`chrX`; VCF convention accepts either,
    but we strip the `chr` prefix for determinism."""
    s = str(c).strip() if c is not None else ""
    if s.lower().startswith("chr"):
        s = s[3:]
    return s or "."


def _write_vcf(rows: list[dict], path: Path) -> int:
    """Write a minimal SnpEff-ANN VCF. Returns number of mutations written.

    When a row carries real genomic coordinates (``chromosome``, ``start_position``,
    ``ref_allele``, ``alt_allele`` — added to the parquet by the refreshed
    ``fetch_tcga_skcm.py``) we emit them verbatim so downstream UV-signature
    inference has real dinucleotide context. For older parquets lacking those
    columns we fall back to the historical ``chr1 100+i A→T`` placeholder —
    the pipeline's parser only consumes HGVSp, so mutation extraction keeps
    working either way."""
    lines = [
        "##fileformat=VCFv4.2",
        "##INFO=<ID=ANN,Number=.,Type=String,Description=\"SnpEff annotations\">",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    written = 0
    for row in rows:
        gene = row.get("gene")
        three = _short_to_three(row.get("hgvs_p"))
        if not gene or not three:
            continue
        ann = (
            f"T|missense_variant|MODERATE|{gene}|ENSG|transcript|ENST|"
            f"protein_coding|1/1|c.NNN|{three}"
        )

        chrom = _normalize_chrom(row.get("chromosome"))
        pos_raw = row.get("start_position")
        ref = str(row.get("ref_allele") or "").strip().upper()
        alt = str(row.get("alt_allele") or "").strip().upper()
        real_coords = (
            chrom not in {".", ""}
            and pos_raw not in (None, "")
            and ref in _VCF_BASES
            and alt in _VCF_BASES
        )
        if real_coords:
            lines.append(f"{chrom}\t{int(pos_raw)}\t.\t{ref}\t{alt}\t.\t.\tANN={ann}")
        else:
            lines.append(f"1\t{100 + written}\t.\tA\tT\t.\t.\tANN={ann}")
        written += 1
    path.write_text("\n".join(lines) + "\n")
    return written


async def _fetch_slide_file_id(client: httpx.AsyncClient, submitter_id: str) -> str | None:
    body = {
        "filters": {
            "op": "and",
            "content": [
                {"op": "in", "content": {"field": "cases.submitter_id", "value": [submitter_id]}},
                {"op": "in", "content": {"field": "data_format", "value": ["SVS"]}},
                {
                    "op": "in",
                    "content": {
                        "field": "experimental_strategy",
                        "value": ["Diagnostic Slide", "Tissue Slide"],
                    },
                },
            ],
        },
        "fields": "file_id,file_name",
        "size": 1,
    }
    r = await client.post(f"{GDC}/files", json=body, timeout=60.0)
    r.raise_for_status()
    hits = r.json().get("data", {}).get("hits", [])
    return hits[0]["file_id"] if hits else None


def _extract_thumbnail_sync(file_id: str, dest: Path) -> bool:
    """Extract a diagnostic-magnification H&E tile from the remote SVS.

    The full-slide overview (``slide.get_thumbnail``) is too zoomed out for the
    VLM to see cellular detail — it's basically a postage stamp with pink
    tissue blobs. Instead:

    1. Pull an overview (downsampled) thumbnail to locate the tissue.
    2. Find the centre-of-mass of the tissue (non-white pixels).
    3. Crop a ``TILE_PX``-square window at level 0 (full magnification)
       around that point and save it as ``slide.jpg``.

    Uses tiffslide + fsspec for lazy HTTP range reads, so per-slide network
    usage stays in the low tens of MB instead of downloading the full SVS.
    """
    import fsspec
    import numpy as np
    import tiffslide

    url = f"{GDC}/data/{file_id}"
    try:
        with fsspec.open(url, "rb") as f:
            slide = tiffslide.TiffSlide(f)
            overview = slide.get_thumbnail((512, 512))
            arr = np.asarray(overview.convert("L"))
            tissue = (arr < 220).astype(np.uint8)  # dark pixels = tissue
            if tissue.sum() < 100:
                return False  # essentially blank slide

            # Find the densest TISSUE patch by sliding a window and picking the
            # maximum. Centroid/mean fails when there are two tissue fragments
            # separated by a gap — the mean lands in the blank middle.
            thumb_tile = 64
            stride = 16
            H, W = tissue.shape
            best_score, best_xy = -1, (W // 2, H // 2)
            for yy in range(0, max(1, H - thumb_tile), stride):
                for xx in range(0, max(1, W - thumb_tile), stride):
                    score = int(tissue[yy:yy + thumb_tile, xx:xx + thumb_tile].sum())
                    if score > best_score:
                        best_score = score
                        best_xy = (xx + thumb_tile // 2, yy + thumb_tile // 2)
            cx_thumb, cy_thumb = best_xy

            level0_w, level0_h = slide.level_dimensions[0]
            scale_x = level0_w / overview.size[0]
            scale_y = level0_h / overview.size[1]
            cx0 = int(cx_thumb * scale_x)
            cy0 = int(cy_thumb * scale_y)

            tile_px = 1024
            x0 = max(0, min(level0_w - tile_px, cx0 - tile_px // 2))
            y0 = max(0, min(level0_h - tile_px, cy0 - tile_px // 2))
            tile = slide.read_region((x0, y0), 0, (tile_px, tile_px))
    except Exception:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tile.convert("RGB").save(dest, "JPEG", quality=88)
    return dest.exists() and dest.stat().st_size > 0


async def _build_case(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    submitter_id: str,
    mutations: list[dict],
    clinical: dict,
    resume: bool,
) -> tuple[str, str]:
    case_dir = CASES_DIR / submitter_id
    slide_path = case_dir / "slide.jpg"
    vcf_path = case_dir / "tumor.vcf"
    meta_path = case_dir / "metadata.json"

    if resume and slide_path.exists() and vcf_path.exists() and meta_path.exists():
        return (submitter_id, "skipped")

    async with sem:
        case_dir.mkdir(parents=True, exist_ok=True)
        try:
            file_id = await _fetch_slide_file_id(client, submitter_id)
        except Exception as e:
            return (submitter_id, f"lookup_failed:{type(e).__name__}")
        if not file_id:
            return (submitter_id, "no_slide_file")

        ok = await asyncio.to_thread(_extract_thumbnail_sync, file_id, slide_path)
        if not ok:
            return (submitter_id, "thumbnail_failed")

        n = _write_vcf(mutations, vcf_path)
        if n == 0:
            # No parseable missense mutations — useless for the pipeline.
            slide_path.unlink(missing_ok=True)
            vcf_path.unlink(missing_ok=True)
            return (submitter_id, "no_mutations")
        meta_path.write_text(json.dumps(clinical, indent=2, default=str))
        return (submitter_id, "ok")


async def main_async(limit: int, resume: bool, concurrency: int) -> None:
    try:
        import pandas as pd
    except ImportError as e:
        raise SystemExit("pandas missing — install with: pip install -e './backend[prep]'") from e

    parquet = DATA_DIR / "mutations.parquet"
    clinical_csv = DATA_DIR / "clinical.csv"
    if not parquet.exists() or not clinical_csv.exists():
        raise SystemExit(
            f"Missing {parquet} or {clinical_csv}. "
            f"Run `python backend/scripts/fetch_tcga_skcm.py` first."
        )

    df = pd.read_parquet(parquet)
    # Oversample 3x so slide-less / no-mutation cases don't starve us.
    top = df.submitter_id.value_counts().head(limit * 3).index.tolist()
    print(f"→ {PROJECT}: considering top {len(top)} patients by missense count "
          f"(target {limit} successful cases, concurrency={concurrency})")

    clinical_by_sid: dict[str, dict] = {}
    with clinical_csv.open() as f:
        for row in csv.DictReader(f):
            clinical_by_sid[row["submitter_id"]] = row

    CASES_DIR.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    counts: dict[str, int] = {}
    successful = 0

    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(
                _build_case(
                    client,
                    sem,
                    sid,
                    df[df.submitter_id == sid].to_dict("records"),
                    clinical_by_sid.get(sid, {"submitter_id": sid}),
                    resume,
                )
            )
            for sid in top
        ]
        try:
            for coro in asyncio.as_completed(tasks):
                sid, status = await coro
                counts[status] = counts.get(status, 0) + 1
                if status in {"ok", "skipped"}:
                    successful += 1
                    marker = "✓" if status == "ok" else "·"
                    print(f"  {marker} [{successful:>3}/{limit}] {sid} ({status})")
                else:
                    print(f"  ✗ {sid} ({status})")
                if successful >= limit:
                    break
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"\n✓ Done — {summary}")
    print(f"  Cases on disk: {CASES_DIR} ({sum(1 for _ in CASES_DIR.iterdir())} dirs)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--limit", type=int, default=100, help="Target number of successful cases")
    ap.add_argument("--resume", action="store_true", help="Skip cases with existing slide+vcf+meta")
    ap.add_argument("--concurrency", type=int, default=8, help="Parallel GDC requests")
    args = ap.parse_args()
    asyncio.run(main_async(args.limit, args.resume, args.concurrency))


if __name__ == "__main__":
    main()
