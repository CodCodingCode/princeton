"""Sliding window peptide generation around a mutation site."""

from __future__ import annotations

from ..models import Mutation, Peptide

DEFAULT_LENGTHS = (8, 9, 10, 11)


def generate_peptides(
    mutant_protein: str,
    mutation: Mutation,
    lengths: tuple[int, ...] = DEFAULT_LENGTHS,
) -> list[Peptide]:
    mut_idx = mutation.position - 1
    peptides: list[Peptide] = []

    for length in lengths:
        for start in range(mut_idx - length + 1, mut_idx + 1):
            if start < 0 or start + length > len(mutant_protein):
                continue
            seq = mutant_protein[start:start + length]
            peptides.append(
                Peptide(
                    sequence=seq,
                    length=length,
                    mutation=mutation,
                    mutation_index=mut_idx - start,
                )
            )
    return peptides
