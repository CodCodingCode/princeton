"""Reverse translate protein sequences to codon-optimized mRNA."""

from __future__ import annotations

OPTIMAL_CODON: dict[str, str] = {
    "A": "GCC", "R": "CGG", "N": "AAC", "D": "GAC", "C": "TGC",
    "E": "GAG", "Q": "CAG", "G": "GGC", "H": "CAC", "I": "ATC",
    "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC", "P": "CCC",
    "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG",
}

STOP_CODON = "TAA"


def reverse_translate(protein: str) -> str:
    out: list[str] = []
    for aa in protein:
        codon = OPTIMAL_CODON.get(aa.upper())
        if codon is None:
            raise ValueError(f"Cannot reverse-translate non-standard residue: {aa!r}")
        out.append(codon)
    return "".join(out)
