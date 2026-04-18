"""Parse VCF (SnpEff ANN field) or a simple gene/mutation TSV."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Mutation

AA_THREE_TO_ONE = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}

HGVS_P_RE = re.compile(r"p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})")
SHORT_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")


def _parse_hgvs_p(hgvs: str) -> tuple[str, int, str] | None:
    m = HGVS_P_RE.search(hgvs)
    if not m:
        return None
    ref3, pos, alt3 = m.groups()
    ref = AA_THREE_TO_ONE.get(ref3)
    alt = AA_THREE_TO_ONE.get(alt3)
    if not ref or not alt:
        return None
    return ref, int(pos), alt


def _parse_short(label: str) -> tuple[str, int, str] | None:
    m = SHORT_RE.match(label.strip())
    if not m:
        return None
    ref, pos, alt = m.groups()
    return ref, int(pos), alt


def parse_tsv(path: Path) -> list[Mutation]:
    mutations: list[Mutation] = []
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 2:
            parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            raise ValueError(f"{path}:{line_no}: expected 'gene<TAB>mutation', got {line!r}")
        gene = parts[0]
        if gene.lower() == "gene":
            continue
        parsed = _parse_short(parts[1]) or _parse_hgvs_p(parts[1])
        if not parsed:
            raise ValueError(f"{path}:{line_no}: could not parse mutation {parts[1]!r}")
        ref, pos, alt = parsed
        mutations.append(Mutation(gene=gene, ref_aa=ref, position=pos, alt_aa=alt))
    return mutations


def parse_vcf(path: Path) -> list[Mutation]:
    mutations: list[Mutation] = []
    seen: set[tuple[str, str, int, str]] = set()
    for raw in path.read_text().splitlines():
        if not raw or raw.startswith("#"):
            continue
        cols = raw.split("\t")
        if len(cols) < 8:
            continue
        info = cols[7]
        ann_field = next((kv for kv in info.split(";") if kv.startswith("ANN=")), None)
        if not ann_field:
            continue
        for ann in ann_field[len("ANN="):].split(","):
            fields = ann.split("|")
            if len(fields) < 11:
                continue
            effect = fields[1]
            gene = fields[3]
            hgvs_p = fields[10]
            if "missense" not in effect or not gene or not hgvs_p:
                continue
            parsed = _parse_hgvs_p(hgvs_p)
            if not parsed:
                continue
            ref, pos, alt = parsed
            key = (gene, ref, pos, alt)
            if key in seen:
                continue
            seen.add(key)
            mutations.append(Mutation(gene=gene, ref_aa=ref, position=pos, alt_aa=alt))
    return mutations


def parse(path: Path) -> list[Mutation]:
    suffix = path.suffix.lower()
    if suffix == ".vcf":
        return parse_vcf(path)
    return parse_tsv(path)
