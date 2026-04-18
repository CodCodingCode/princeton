"""Melanoma copilot orchestrator.

Replaces the canine cancer ``CaseOrchestrator``. Drives the panel-1/2/3 demo:

1. VLM reads the pathology slide → ``PathologyFindings``.
2. Parse the tumour VCF → ``list[Mutation]``.
3. NCCN walker walks the decision tree, emitting reasoning + node-visited events.
4. Molecular landscape: fold WT/mutant for top driver mutations and pull drug
   co-crystals for known pairs (Panel 2 data).
5. If the NCCN path arrives at the personalized vaccine endpoint, run the
   existing peptide pipeline and dock the top three peptides into HLA-A*02:01
   (Panel 3 data).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from ..models import (
    MelanomaCase,
    Mutation,
    PathologyFindings,
    PipelineResult,
)
from ..nccn.walker import NCCNWalker, PatientState
from ..pipeline.parser import parse as parse_mutations
from ..pipeline.runner import RunConfig, run as run_pipeline_sync
from ..pipeline.scoring import build_scorer
from .events import EventBus, EventKind, set_current_bus
from .molecular import build_landscape
from .structure import dock_peptide
from .vlm_pathology import analyze_slide


DEFAULT_HLA = "HLA-A*02:01"


@dataclass
class MelanomaOrchestrator:
    slide_path: Path
    vcf_path: Path
    bus: EventBus = field(default_factory=EventBus)
    hla_allele: str = DEFAULT_HLA

    async def run(self) -> MelanomaCase:
        set_current_bus(self.bus)
        case = MelanomaCase(pathology=PathologyFindings())
        try:
            # 1. Pathology
            pathology = await analyze_slide(self.slide_path)
            case.pathology = pathology
            await self.bus.emit(
                EventKind.CASE_UPDATE, "pathology", {"pathology": pathology.model_dump()}
            )

            # 2. Mutations
            mutations: list[Mutation] = []
            if self.vcf_path.exists():
                try:
                    mutations = parse_mutations(self.vcf_path)
                except Exception as e:
                    await self.bus.emit(EventKind.LOG, f"VCF parse failed: {e}")
            case.mutations = mutations
            await self.bus.emit(
                EventKind.TOOL_RESULT,
                f"🧬 Parsed {len(mutations)} mutations from VCF",
                {"mutations": [m.model_dump() for m in mutations]},
            )
            await self.bus.emit(
                EventKind.CASE_UPDATE, "mutations", {"mutations": [m.model_dump() for m in mutations]}
            )

            # 3. NCCN walker
            tmb = _estimate_tmb(mutations)
            state = PatientState(pathology=pathology, mutations=mutations, tumor_mutational_burden=tmb)
            walker = NCCNWalker(state=state)
            async for step in walker.walk():
                case.nccn_path.append(step)
            if case.nccn_path:
                last = case.nccn_path[-1]
                case.final_recommendation = last.chosen_option or last.node_title
            await self.bus.emit(
                EventKind.NCCN_PATH_COMPLETE,
                f"NCCN ▸ path complete ({len(case.nccn_path)} nodes)",
                {"path": [s.model_dump() for s in case.nccn_path]},
            )

            # 4. Molecular landscape (Panel 2) and 5. Vaccine pipeline (Panel 3) in parallel
            wants_vaccine = any(s.node_id == "VACCINE_CANDIDATE" and "Yes" in s.chosen_option for s in case.nccn_path) \
                or any(s.node_id == "FINAL" for s in case.nccn_path)

            molecular_task = asyncio.create_task(build_landscape(mutations))
            pipeline_task: asyncio.Task[PipelineResult | None] | None = None
            if mutations:
                pipeline_task = asyncio.create_task(self._run_pipeline(mutations))

            case.molecules = await molecular_task
            await self.bus.emit(
                EventKind.CASE_UPDATE,
                "molecules",
                {"molecules": [m.model_dump() for m in case.molecules]},
            )

            if pipeline_task is not None and wants_vaccine:
                pipeline = await pipeline_task
                case.pipeline = pipeline
                if pipeline:
                    await self.bus.emit(
                        EventKind.PIPELINE_RESULT,
                        f"💉 Pipeline produced {len(pipeline.candidates)} candidates",
                        {"pipeline": pipeline.model_dump()},
                    )
                    case.poses = await self._dock_top_peptides(pipeline)
                    await self.bus.emit(
                        EventKind.CASE_UPDATE,
                        "vaccine",
                        {"pipeline": pipeline.model_dump(), "poses": [p.model_dump() for p in case.poses]},
                    )
            elif pipeline_task is not None:
                pipeline_task.cancel()

            await self.bus.emit(EventKind.DONE, "✅ Case complete", {"case": case.model_dump()})
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Orchestrator error: {e}")
            raise
        finally:
            await self.bus.close()
            set_current_bus(None)
        return case

    async def _run_pipeline(self, mutations: list[Mutation]) -> PipelineResult | None:
        await self.bus.emit(EventKind.TOOL_START, "💉 Running vaccine pipeline")
        try:
            config = RunConfig(
                scorer=build_scorer("heuristic", self.hla_allele),
                top_n=10,
                max_nm=500.0,
            )
            return await asyncio.to_thread(run_pipeline_sync, mutations, config, console=Console(quiet=True))
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Pipeline failed: {e}")
            return None

    async def _dock_top_peptides(self, pipeline: PipelineResult):
        poses = []
        for cand in pipeline.candidates[:3]:
            try:
                pose = await dock_peptide(
                    peptide=cand.peptide.sequence,
                    allele=self.hla_allele,
                    mutation_label=cand.peptide.mutation.full_label,
                )
            except Exception as e:
                await self.bus.emit(EventKind.LOG, f"Dock {cand.peptide.sequence} failed: {e}")
                continue
            poses.append(pose)
            await self.bus.emit(
                EventKind.STRUCTURE_READY,
                f"🔭 {cand.peptide.sequence} docked into {self.hla_allele} ({pose.method})",
                {"pose": pose.model_dump()},
            )
        return poses


def _estimate_tmb(mutations: list[Mutation]) -> float:
    """Crude proxy: missense count / 1 Mb. Real TMB needs full-exome context;
    this is enough for the demo to drive 'high TMB' branches when relevant."""
    return float(len(mutations))
