"""Build the final mRNA vaccine construct: Kozak + ATG + epitopes + linkers + stop."""

from __future__ import annotations

from ..models import Candidate, VaccineConstruct
from .codon import OPTIMAL_CODON, STOP_CODON, reverse_translate

KOZAK = "GCCGCCACC"
START_AA = "M"
AAY_LINKER = "AAY"


def build_construct(candidates: list[Candidate], linker: str = AAY_LINKER) -> VaccineConstruct:
    epitopes = [c.peptide.sequence for c in candidates]
    if not epitopes:
        raise ValueError("Cannot build construct with zero epitopes")

    aa_sequence = START_AA + linker.join(epitopes)
    nt_body = reverse_translate(aa_sequence)
    nt_sequence = KOZAK + nt_body + STOP_CODON

    return VaccineConstruct(
        epitopes=epitopes,
        linker=linker,
        nucleotide_sequence=nt_sequence,
        amino_acid_sequence=aa_sequence,
    )
