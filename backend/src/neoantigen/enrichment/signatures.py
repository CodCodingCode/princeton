"""UV mutational-signature fraction from a VCF.

SBS7a/b (COSMIC) is the canonical UV-damage signature in melanoma: C→T
transitions at dipyrimidine contexts (preceding pyrimidine at the 5′ base).
The hallmark is an over-representation of CC→CT and TC→TT compared to the
expected ~1/6 background rate of C→T at random context.

This module uses a **dinucleotide-context approximation**: we count C→T (and
its reverse-complement G→A) SNVs where the VCF ``REF`` column paired with
the immediately preceding ``REF`` in genomic order forms a pyrimidine-pyrimidine
dinucleotide. Because we read the VCF without a reference FASTA, we
approximate the 5′ flanking base using the **POS ordering within the same
chromosome** — consecutive MAF rows are usually independent events, so the
approximation mostly captures same-codon / same-locus dipyrimidines. For
the Regeneron demo this is enough to surface a qualitative "UV-high" chip.

Pass-through when the VCF has placeholder coords (everything on chr1 pos
100+i A→T) — the function detects that case and returns ``None`` so the
caller can show "signature n/a" instead of a misleading 0%.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PURINES = frozenset({"A", "G"})
_PYRIMIDINES = frozenset({"C", "T"})
_BASES = _PURINES | _PYRIMIDINES


@dataclass
class UVSignatureResult:
    fraction: float
    total_scored: int
    uv_hits: int


def compute_uv_signature(vcf_path: Path) -> UVSignatureResult | None:
    """Read ``vcf_path`` and compute the UV-signature fraction.

    Returns ``None`` when the VCF has no usable SNVs (all placeholders, or
    every variant rejected for non-base REF/ALT).
    """
    snvs = _read_snvs(vcf_path)
    if not snvs:
        return None

    # Detect placeholder VCF: every row on chr1 with POS 100+i and A→T.
    # These are written by older `build_tcga_skcm_cases.py` and carry no
    # real genomic context.
    all_placeholder = all(
        row.chrom == "1" and row.ref == "A" and row.alt == "T"
        for row in snvs
    )
    if all_placeholder:
        return None

    # Group by chromosome so we can look at the 5′ REF neighbour in POS order.
    by_chrom: dict[str, list[_VCFRow]] = {}
    for row in snvs:
        by_chrom.setdefault(row.chrom, []).append(row)
    for rows in by_chrom.values():
        rows.sort(key=lambda r: r.pos)

    uv_hits = 0
    total = 0
    for chrom, rows in by_chrom.items():
        for i, row in enumerate(rows):
            if row.ref not in _BASES or row.alt not in _BASES:
                continue
            total += 1
            prev_ref = rows[i - 1].ref if i > 0 else None
            if _is_uv_hit(prev_ref, row.ref, row.alt):
                uv_hits += 1

    if total == 0:
        return None
    return UVSignatureResult(
        fraction=round(uv_hits / total, 3),
        total_scored=total,
        uv_hits=uv_hits,
    )


@dataclass
class _VCFRow:
    chrom: str
    pos: int
    ref: str
    alt: str


def _read_snvs(path: Path) -> list[_VCFRow]:
    out: list[_VCFRow] = []
    for raw in path.read_text().splitlines():
        if not raw or raw.startswith("#"):
            continue
        cols = raw.split("\t")
        if len(cols) < 5:
            continue
        chrom = cols[0].lstrip("chr").upper()
        try:
            pos = int(cols[1])
        except ValueError:
            continue
        ref = cols[3].strip().upper()
        alt = cols[4].strip().upper()
        # Only single-nucleotide variants — indels / multiallelic skip.
        if len(ref) != 1 or len(alt) != 1:
            continue
        out.append(_VCFRow(chrom=chrom, pos=pos, ref=ref, alt=alt))
    return out


def _is_uv_hit(prev_ref: str | None, ref: str, alt: str) -> bool:
    """Return True when (prev_ref, ref, alt) matches the SBS7 UV fingerprint:
    C→T or G→A (reverse complement) at a dipyrimidine context."""
    if ref == "C" and alt == "T":
        return prev_ref in _PYRIMIDINES if prev_ref is not None else False
    if ref == "G" and alt == "A":
        # Reverse-complement context: the *following* base on the + strand
        # corresponds to the 5′ neighbour on the - strand. We approximate by
        # also accepting G→A when prev_ref is a purine (R at the - strand
        # equivalent of a Y at the + strand). This is looser than a true
        # reference-aware SBS7 lookup but sufficient for qualitative scoring.
        return prev_ref in _PURINES if prev_ref is not None else False
    return False
