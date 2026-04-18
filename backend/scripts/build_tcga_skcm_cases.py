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


def _write_vcf(rows: list[dict], path: Path) -> int:
    """Write a minimal SnpEff-ANN VCF. Returns number of mutations written."""
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
    """Pull an H&E thumbnail out of the full SVS via ranged HTTP reads.

    Uses tiffslide + fsspec to lazy-read only the header + thumbnail page
    from the remote SVS file (~2-5 MB of network traffic instead of 100-500 MB).
    The ``/auth/.../slide-image`` rendering endpoint is token-gated as of 2026,
    but ``/data/{file_id}`` is open-access and accepts range requests.
    """
    import fsspec
    import tiffslide

    url = f"{GDC}/data/{file_id}"
    try:
        with fsspec.open(url, "rb") as f:
            slide = tiffslide.TiffSlide(f)
            thumb = slide.get_thumbnail(THUMB_MAX_SIZE)
    except Exception:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    thumb.convert("RGB").save(dest, "JPEG", quality=85)
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
