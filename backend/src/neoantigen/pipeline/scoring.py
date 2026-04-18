"""Peptide-MHC binding scorers.

Default (production): ``MHCflurryScorer`` — real pretrained ML models.
Test fixture only: ``HeuristicScorer`` — hand-rolled pseudo-nM math. Not a
real MHC predictor. Only reachable via an explicit ``name="heuristic"``
opt-in so no production path silently picks it up.
"""

from __future__ import annotations

import math
import warnings
from typing import Protocol

from ..models import Peptide

HYDROPHOBIC = set("AILMFWVC")

A0201_P2_ANCHORS = set("LMIV")
A0201_PC_ANCHORS = set("VLIM")


HEURISTIC_WARNING = (
    "⚠ heuristic-only scoring — NOT a real MHC predictor. "
    "The reported nM values are made-up anchor-residue math. "
    "Install mhcflurry (already a base dependency) and run "
    "`mhcflurry-downloads fetch` for real affinity predictions."
)


class Scorer(Protocol):
    name: str
    allele: str
    is_heuristic: bool

    def score(self, peptides: list[Peptide]) -> None: ...


class HeuristicScorer:
    """Test-fixture scorer. Pseudo-nM math; NOT a real MHC predictor."""

    name = "heuristic"
    is_heuristic = True

    def __init__(self, allele: str = "HLA-A*02:01") -> None:
        self.allele = allele
        warnings.warn(HEURISTIC_WARNING, RuntimeWarning, stacklevel=2)

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
    is_heuristic = False

    def __init__(self, allele: str = "HLA-A*02:01") -> None:
        self.allele = allele
        try:
            from mhcflurry import Class1AffinityPredictor
        except ImportError as e:
            raise RuntimeError(
                "mhcflurry not installed. Run: pip install -e './backend' && mhcflurry-downloads fetch"
            ) from e
        self._predictor = Class1AffinityPredictor.load()

    def score(self, peptides: list[Peptide]) -> None:
        if not peptides:
            return
        seqs = [p.sequence for p in peptides]
        predictions = self._predictor.predict(peptides=seqs, allele=self.allele)
        for peptide, nm in zip(peptides, predictions):
            peptide.score_nm = float(nm)


def build_scorer(name: str = "mhcflurry", allele: str = "HLA-A*02:01") -> Scorer:
    """Build a scorer. Defaults to real MHCflurry.

    Pass ``name="heuristic"`` to opt into the test-fixture scorer; this emits
    a ``RuntimeWarning`` on construction.
    """
    if name == "heuristic":
        return HeuristicScorer(allele=allele)
    if name != "mhcflurry":
        raise ValueError(f"Unknown scorer '{name}'. Use 'mhcflurry' or 'heuristic'.")
    return MHCflurryScorer(allele=allele)
