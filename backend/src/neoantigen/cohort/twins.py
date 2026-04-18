"""Match a query patient against the TCGA-SKCM cohort.

Similarity is a simple weighted score:

* +0.40  same BRAF V600E status
* +0.20  same NRAS Q61 status
* +0.10  same KIT-mutant status
* +0.10  same NF1-mutant status
* +0.10  same AJCC stage bucket
* +0.05  age within ±10 years
* +0.05  Jaccard overlap of mutated genes (top driver set only)

Returns the top-K most similar patients with their outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tcga import TCGAPatient

DRIVER_SET = {"BRAF", "NRAS", "KIT", "NF1", "TP53", "PTEN", "CDKN2A", "MAP2K1", "MAP2K2"}


@dataclass
class QueryPatient:
    braf_v600e: bool
    nras_q61: bool
    kit_mutant: bool
    nf1_mutant: bool
    stage_bucket: str
    age: int | None
    mutated_genes: set[str]


@dataclass
class TwinMatch:
    patient: TCGAPatient
    similarity: float
    matching_features: list[str]


def _stage_match(query: str, candidate: str) -> bool:
    if query == "Unknown" or candidate == "Unknown":
        return False
    return query == candidate


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def find_twins(query: QueryPatient, cohort: list[TCGAPatient], top_k: int = 10) -> list[TwinMatch]:
    matches: list[TwinMatch] = []
    query_drivers = query.mutated_genes & DRIVER_SET

    for p in cohort:
        score = 0.0
        why: list[str] = []
        if query.braf_v600e == p.braf_v600e:
            score += 0.40
            if query.braf_v600e:
                why.append("BRAF V600E")
        if query.nras_q61 == p.nras_q61:
            score += 0.20
            if query.nras_q61:
                why.append("NRAS Q61")
        if query.kit_mutant == p.kit_mutant:
            score += 0.10
            if query.kit_mutant:
                why.append("KIT mutant")
        if query.nf1_mutant == p.nf1_mutant:
            score += 0.10
            if query.nf1_mutant:
                why.append("NF1 mutant")
        if _stage_match(query.stage_bucket, p.stage_bucket):
            score += 0.10
            why.append(f"stage {p.stage_bucket}")
        if query.age is not None and p.age_at_diagnosis is not None:
            if abs(query.age - p.age_at_diagnosis) <= 10:
                score += 0.05
                why.append("similar age")
        score += 0.05 * _jaccard(query_drivers, p.mutated_genes & DRIVER_SET)

        matches.append(TwinMatch(patient=p, similarity=round(score, 3), matching_features=why))

    matches.sort(key=lambda m: m.similarity, reverse=True)
    return matches[:top_k]
