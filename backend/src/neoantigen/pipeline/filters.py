"""Filter candidate peptides.

- Must contain the mutated residue (sanity check)
- Must not also appear in the reference (normal) protein — avoid self-reactivity
- Score below the affinity threshold
"""

from __future__ import annotations

from ..models import Peptide


def filter_candidates(
    peptides: list[Peptide],
    reference_protein: str,
    *,
    max_nm: float = 500.0,
) -> list[Peptide]:
    kept: list[Peptide] = []
    for p in peptides:
        if p.score_nm is None:
            continue
        if p.score_nm > max_nm:
            continue
        if not p.contains_mutation:
            continue
        if p.sequence in reference_protein:
            continue
        kept.append(p)
    kept.sort(key=lambda x: (x.score_nm if x.score_nm is not None else float("inf")))
    return kept
