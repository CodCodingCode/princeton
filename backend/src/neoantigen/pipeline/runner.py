"""End-to-end pipeline orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from rich.console import Console

from ..external.clinicaltrials import search_trials
from ..external.dgidb import search_drugs
from ..models import (
    Candidate,
    ClinicalTrial,
    DrugInteraction,
    Mutation,
    Peptide,
    PipelineResult,
)
from .construct import build_construct
from .filters import filter_candidates
from .peptides import generate_peptides
from .protein import apply_mutation, fetch_protein
from .scoring import Scorer


@dataclass
class RunConfig:
    scorer: Scorer
    top_n: int = 15
    max_nm: float = 500.0
    with_apis: bool = False
    species: str = "human"


async def _fetch_external(
    mutations: list[Mutation],
) -> tuple[list[DrugInteraction], list[ClinicalTrial]]:
    genes = sorted({m.gene for m in mutations})
    async with httpx.AsyncClient() as client:
        drug_tasks = [search_drugs(client, g) for g in genes]
        trial_tasks = [search_trials(client, g) for g in genes]
        drug_lists, trial_lists = await asyncio.gather(
            asyncio.gather(*drug_tasks),
            asyncio.gather(*trial_tasks),
        )

    drugs = [d for sub in drug_lists for d in sub]
    trials = [t for sub in trial_lists for t in sub]
    return drugs, trials


def run(mutations: list[Mutation], config: RunConfig, *, console: Console | None = None) -> PipelineResult:
    console = console or Console()

    all_peptides: list[Peptide] = []
    reference_by_gene: dict[str, str] = {}

    for mutation in mutations:
        if mutation.gene not in reference_by_gene:
            console.log(f"[cyan]fetch[/cyan] {mutation.gene} reference protein ({config.species})")
            reference_by_gene[mutation.gene] = fetch_protein(mutation.gene, species=config.species)
        reference = reference_by_gene[mutation.gene]
        mutant = apply_mutation(reference, mutation)
        peptides = generate_peptides(mutant, mutation)
        console.log(f"[cyan]peptides[/cyan] {mutation.full_label}: {len(peptides)} candidates")
        all_peptides.extend(peptides)

    console.log(f"[cyan]score[/cyan] {len(all_peptides)} peptides with {config.scorer.name} ({config.scorer.allele})")
    config.scorer.score(all_peptides)

    filtered: list[Peptide] = []
    for mutation in mutations:
        mutation_peptides = [p for p in all_peptides if p.mutation.full_label == mutation.full_label]
        ref = reference_by_gene[mutation.gene]
        filtered.extend(filter_candidates(mutation_peptides, ref, max_nm=config.max_nm))

    filtered.sort(key=lambda p: p.score_nm or float("inf"))
    top = filtered[: config.top_n]
    candidates = [Candidate(peptide=p, rank=i + 1) for i, p in enumerate(top)]
    console.log(f"[cyan]filter[/cyan] kept {len(filtered)} peptides ≤ {config.max_nm} nM, taking top {len(candidates)}")

    construct = build_construct(candidates) if candidates else None
    if construct:
        console.log(
            f"[cyan]construct[/cyan] {construct.length_bp} bp "
            f"(~${construct.estimated_cost_usd} at $0.07/bp)"
        )

    drugs: list[DrugInteraction] = []
    trials: list[ClinicalTrial] = []
    if config.with_apis:
        console.log("[cyan]apis[/cyan] querying ClinicalTrials.gov + DGIdb")
        drugs, trials = asyncio.run(_fetch_external(mutations))
        console.log(f"[cyan]apis[/cyan] {len(drugs)} drug interactions, {len(trials)} clinical trials")

    return PipelineResult(
        mutations=mutations,
        candidates=candidates,
        drugs=drugs,
        trials=trials,
        vaccine=construct,
    )
