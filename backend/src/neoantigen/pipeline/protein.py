"""Fetch reference protein sequences from UniProt, cache locally, apply mutations."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from ..genes import lookup as lookup_accession
from ..models import Mutation

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{accession}.fasta"


def cache_dir() -> Path:
    root = Path(os.environ.get("NEOANTIGEN_CACHE", Path.home() / ".cache" / "neoantigen"))
    path = root / "proteins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_fasta(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith(">")]
    return "".join(lines)


def fetch_protein(gene: str, *, species: str = "human", force: bool = False, timeout: float = 15.0) -> str:
    accession = lookup_accession(gene, species=species)
    if accession is None:
        raise KeyError(f"Unknown gene symbol: {gene!r} (species={species}). Add it to src/neoantigen/genes.py.")

    cache_path = cache_dir() / f"{accession}.fasta"
    if cache_path.exists() and not force:
        return _parse_fasta(cache_path.read_text())

    url = UNIPROT_URL.format(accession=accession)
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    cache_path.write_text(response.text)
    return _parse_fasta(response.text)


def apply_mutation(sequence: str, mutation: Mutation) -> str:
    idx = mutation.position - 1
    if idx < 0 or idx >= len(sequence):
        raise ValueError(
            f"{mutation.full_label}: position {mutation.position} out of range "
            f"for {len(sequence)}-aa protein"
        )
    actual = sequence[idx]
    if actual != mutation.ref_aa:
        raise ValueError(
            f"{mutation.full_label}: reference mismatch — protein has {actual!r} "
            f"at position {mutation.position}, mutation expects {mutation.ref_aa!r}"
        )
    return sequence[:idx] + mutation.alt_aa + sequence[idx + 1:]
