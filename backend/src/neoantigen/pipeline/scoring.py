"""Peptide-MHC binding scorers.

Default: heuristic based on length and anchor residues (HLA-A*02:01-ish).
Opt-in: MHCflurry via `--mhcflurry` flag.
"""

from __future__ import annotations

import math
from typing import Protocol

from ..models import Peptide

HYDROPHOBIC = set("AILMFWVC")
A0201_P2_ANCHORS = set("LMIV")
A0201_PC_ANCHORS = set("VLIM")

# DLA-88 anchor preferences from canine peptidome studies (Ross 2018, Barth 2016).
# DLA-88*50101 favors hydrophobic P2 and aromatic/hydrophobic C-terminus.
DLA_88_50101_P2_ANCHORS = set("AILMV")
DLA_88_50101_PC_ANCHORS = set("FLWMIV")
# DLA-88*00801 — different preferred anchors
DLA_88_00801_P2_ANCHORS = set("EDQ")
DLA_88_00801_PC_ANCHORS = set("LMFI")


class Scorer(Protocol):
    name: str
    allele: str

    def score(self, peptides: list[Peptide]) -> None: ...


class HeuristicScorer:
    """Pseudo-nM scorer. Lower score = stronger predicted binding."""

    name = "heuristic"

    def __init__(self, allele: str = "HLA-A*02:01") -> None:
        self.allele = allele

    def _score_one(self, seq: str) -> float:
        length = len(seq)
        score = 0.0

        if length == 9:
            score += 0.0
        elif length == 10:
            score += 0.5
        elif length == 8:
            score += 1.5
        else:
            score += 2.0

        if length >= 2 and seq[1] in A0201_P2_ANCHORS:
            score -= 1.8
        if seq[-1] in A0201_PC_ANCHORS:
            score -= 1.8

        hydrophobic_fraction = sum(1 for aa in seq if aa in HYDROPHOBIC) / length
        score -= hydrophobic_fraction * 0.8

        if "P" in seq[1:-1]:
            score += 0.7

        pseudo_nm = 50.0 * math.exp(score)
        return round(pseudo_nm, 2)

    def score(self, peptides: list[Peptide]) -> None:
        for p in peptides:
            p.score_nm = self._score_one(p.sequence)


class MHCflurryScorer:
    """Real ML scorer using pretrained MHCflurry models."""

    name = "mhcflurry"

    def __init__(self, allele: str = "HLA-A*02:01") -> None:
        self.allele = allele
        try:
            from mhcflurry import Class1AffinityPredictor
        except ImportError as e:
            raise RuntimeError(
                "mhcflurry not installed. Run: pip install -e '.[ml]' && mhcflurry-downloads fetch"
            ) from e
        self._predictor = Class1AffinityPredictor.load()

    def score(self, peptides: list[Peptide]) -> None:
        if not peptides:
            return
        seqs = [p.sequence for p in peptides]
        predictions = self._predictor.predict(peptides=seqs, allele=self.allele)
        for peptide, nm in zip(peptides, predictions):
            peptide.score_nm = float(nm)


class DLAHeuristicScorer:
    """Canine DLA-I binding heuristic. Same shape as HeuristicScorer but with DLA anchors."""

    name = "dla-heuristic"

    def __init__(self, allele: str = "DLA-88*50101") -> None:
        self.allele = allele
        if "50101" in allele:
            self._p2 = DLA_88_50101_P2_ANCHORS
            self._pc = DLA_88_50101_PC_ANCHORS
        elif "00801" in allele:
            self._p2 = DLA_88_00801_P2_ANCHORS
            self._pc = DLA_88_00801_PC_ANCHORS
        else:
            self._p2 = DLA_88_50101_P2_ANCHORS
            self._pc = DLA_88_50101_PC_ANCHORS

    def _score_one(self, seq: str) -> float:
        length = len(seq)
        score = 0.0
        if length == 9:
            score += 0.0
        elif length == 10:
            score += 0.4
        elif length == 8:
            score += 1.2
        else:
            score += 2.0

        if length >= 2 and seq[1] in self._p2:
            score -= 1.6
        if seq[-1] in self._pc:
            score -= 1.6

        hydrophobic_fraction = sum(1 for aa in seq if aa in HYDROPHOBIC) / length
        score -= hydrophobic_fraction * 0.6

        if "P" in seq[1:-1]:
            score += 0.5

        pseudo_nm = 60.0 * math.exp(score)
        return round(pseudo_nm, 2)

    def score(self, peptides: list[Peptide]) -> None:
        for p in peptides:
            p.score_nm = self._score_one(p.sequence)


def build_scorer(name: str, allele: str) -> Scorer:
    if name == "mhcflurry":
        return MHCflurryScorer(allele=allele)
    if name == "dla-heuristic" or allele.startswith("DLA"):
        return DLAHeuristicScorer(allele=allele)
    return HeuristicScorer(allele=allele)
