"""Main case orchestrator — deterministic 8-step workflow.

Drives the end-to-end case generation with a plain async Python workflow (no
multi-turn tool-calling loop). LLM reasoning is performed inside three PydanticAI
agents (pathology, emails, explain) backed by K2 Think V2; every other step is
a pure compute or IO call. Tools emit events to an EventBus; the external
consumer (Streamlit UI or CLI) consumes the stream and reconstructs the CaseFile.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import (
    CaseFile,
    EmailDraft,
    LabMatch,
    PathologyReport,
    PipelineResult,
    StructurePose,
    TimelineEvent,
)
from .events import AgentEvent, EventBus, EventKind, set_current_bus
from . import tools


DEFAULT_LOCATION = "New York, NY"
DEFAULT_ALLELE = "DLA-88*50101"


@dataclass
class CaseOrchestrator:
    """One-shot orchestrator: runs the 8-step workflow end-to-end for a single case."""

    vcf_path: Path
    pdf_path: Path
    bus: EventBus = field(default_factory=EventBus)
    case: CaseFile | None = None

    async def run(self) -> None:
        """Run the deterministic workflow. Emits events to self.bus;
        external consumer assembles CaseFile from CASE_UPDATE events."""
        set_current_bus(self.bus)
        try:
            # Step 1: Pathology extraction
            pathology = await tools.read_pathology(self.pdf_path)
            if "error" in pathology:
                raise RuntimeError(f"Pathology extraction failed: {pathology['error']}")

            species = pathology.get("species") or "canine"
            allele = _first_allele(pathology) or DEFAULT_ALLELE

            # Step 2: Neoantigen pipeline
            pipeline = await tools.run_neoantigen_pipeline(
                vcf_path=self.vcf_path,
                species=species,
                allele=allele,
            )
            if "error" in pipeline:
                raise RuntimeError(f"Pipeline failed: {pipeline['error']}")

            # Step 3: Parallel discovery (labs, vets, vendors, drugs, trials)
            location = pathology.get("owner_location") or DEFAULT_LOCATION
            genes: list[str] = pipeline.get("genes") or []
            cancer_type = pathology.get("cancer_type") or ""
            mrna_length = int(pipeline.get("construct_length_bp") or 600)

            labs, vets, vendors, _drugs, _trials = await asyncio.gather(
                tools.find_sequencing_labs(location),
                tools.find_vet_oncologists(location),
                tools.find_synthesis_vendors(mrna_length),
                tools.find_drug_interactions(genes),
                tools.find_clinical_trials(genes, cancer_type),
                return_exceptions=True,
            )

            # Step 4: Structure docking for the top candidate
            top = pipeline.get("top_candidate")
            if top:
                await tools.validate_structure_3d(
                    peptide=top["sequence"],
                    dla_allele=allele,
                    mutation_label=top["mutation"],
                )

            # Step 5: Parallel email drafts (4 recipient types)
            top_lab = _first_name(labs, default="Sequencing Lab Partner")
            top_vet = _first_name(vets, default="Veterinary Oncology Team")
            context_summary = _build_context_summary(pathology, pipeline, top)

            await asyncio.gather(
                tools.draft_email("sequencing_lab", top_lab, context=context_summary),
                tools.draft_email(
                    "synthesis_vendor", "TriLink BioTechnologies", context=context_summary
                ),
                tools.draft_email("vet_oncologist", top_vet, context=context_summary),
                tools.draft_email("ethics_board", "Ethics Committee", context=context_summary),
                return_exceptions=True,
            )

            # Step 6: Treatment timeline
            await tools.generate_timeline(start_week=1, species=species)

            # Step 7: Plain-English owner explanation
            await tools.explain_case_to_owner(
                patient_name=pathology.get("patient_name") or "the patient",
                cancer_type=cancer_type or "cancer",
                candidate_count=int(pipeline.get("candidates") or 0),
                top_mutation=(top["mutation"] if top else "unknown"),
            )

            # Step 8: Done
            await self.bus.emit(EventKind.DONE, "✅ Case complete")
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Workflow error: {e}")
        finally:
            await self.bus.close()
            set_current_bus(None)


def _first_allele(pathology: dict[str, Any]) -> str | None:
    alleles = pathology.get("dla_alleles") or []
    return alleles[0] if alleles else None


def _first_name(result: Any, default: str) -> str:
    """Extract the first entry's `name` from a discovery result list.

    Handles the case where the result is an Exception (from asyncio.gather with
    return_exceptions=True), an empty list, or a list of dicts.
    """
    if isinstance(result, BaseException) or not result:
        return default
    first = result[0]
    if isinstance(first, dict):
        return first.get("name") or default
    return default


def _build_context_summary(
    pathology: dict[str, Any],
    pipeline: dict[str, Any],
    top: dict[str, Any] | None,
) -> str:
    parts = [
        f"Patient: {pathology.get('patient_name', 'unknown')} "
        f"({pathology.get('species', 'canine')}, {pathology.get('cancer_type', 'cancer')}).",
        f"Mutations found: {pipeline.get('mutations_found', 0)}.",
        f"Neoantigen candidates: {pipeline.get('candidates', 0)}.",
    ]
    if top:
        parts.append(
            f"Top candidate: {top['sequence']} from mutation {top['mutation']} "
            f"(predicted affinity {top.get('score_nm', '?')} nM)."
        )
    return " ".join(parts)


def build_case_file(events: list[AgentEvent]) -> CaseFile | None:
    """Reconstruct a CaseFile from a captured list of CASE_UPDATE events."""
    pathology_data: dict | None = None
    pipeline_data: dict | None = None
    structures: list[dict] = []
    seq_labs: list[dict] = []
    vets: list[dict] = []
    vendors: list[dict] = []
    emails: list[dict] = []
    timeline_data: list[dict] = []
    plain_english = ""

    for ev in events:
        if ev.kind != EventKind.CASE_UPDATE:
            continue
        p = ev.payload
        if "pathology" in p:
            pathology_data = p["pathology"]
        if "pipeline_result" in p:
            pipeline_data = p["pipeline_result"]
        if "pose" in p:
            structures.append(p["pose"])
        if "labs" in p:
            seq_labs = p["labs"]
        if "vets" in p:
            vets = p["vets"]
        if "vendors" in p:
            vendors = p["vendors"]
        if "email" in p:
            emails.append(p["email"])
        if "timeline" in p:
            timeline_data = p["timeline"]
        if "plain_english" in p:
            plain_english = p["plain_english"]

    if pathology_data is None:
        return None

    pipeline = (
        PipelineResult(**pipeline_data)
        if pipeline_data
        else PipelineResult(mutations=[], candidates=[])
    )
    return CaseFile(
        pathology=PathologyReport(**pathology_data),
        pipeline=pipeline,
        structures=[StructurePose(**s) for s in structures],
        sequencing_labs=[LabMatch(**l) for l in seq_labs],
        synthesis_vendors=[LabMatch(**v) for v in vendors],
        vet_oncologists=[LabMatch(**v) for v in vets],
        emails=[EmailDraft(**e) for e in emails],
        timeline=[TimelineEvent(**t) for t in timeline_data],
        plain_english=plain_english,
    )


async def run_case(vcf_path: Path, pdf_path: Path, bus: EventBus | None = None) -> CaseOrchestrator:
    """Create a case orchestration. Caller consumes bus.stream() for live events."""
    bus = bus or EventBus()
    return CaseOrchestrator(vcf_path=vcf_path, pdf_path=pdf_path, bus=bus)
