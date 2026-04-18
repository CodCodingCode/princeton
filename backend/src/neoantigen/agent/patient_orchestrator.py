"""Patient-flow orchestrator — multi-PDF folder input.

Flow (one call per case):

  1. Folder of PDFs in → per-doc extraction (pypdf text + MediX VLM per page)
  2. Kimi K2 aggregator reconciles across docs → canonical PatientCase
  3. NCCN railway walk on the canonical record (streams THINKING_DELTA +
     RAILWAY_STEP events)
  4. Regeneron trial matching (parallel with 5)
  5. Trial-site geocoding for matched NCTs
  6. Final PatientCase bundled; DONE event emitted

All stages degrade silently when optional inputs (MediX tunnel, RAG, Google
Maps API key, Kimi endpoint) are missing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Sequence

from ..enrichment import enrich
from ..enrichment.cancer_type import detect_primary_cancer
from ..external.regeneron_rules import evaluate_all
from ..external.trial_sites import fetch_trial_sites
from ..io.aggregator import aggregate_documents
from ..io.pdf_extract import extract_document
from ..models import (
    ClinicianIntake,
    DocumentExtraction,
    EnrichedBiomarkers,
    Mutation,
    PathologyFindings,
    PatientCase,
    TrialMatch,
    TrialSite,
)
from ..nccn.dynamic_walker import (
    DynamicRailwayWalker,
    PatientState,
    final_recommendation_from_steps,
)
from ..nccn.railway import build_map
from .events import EventBus, EventKind, set_current_bus


@dataclass
class InputPDF:
    filename: str
    data: bytes


@dataclass
class PatientOrchestrator:
    case_id: str
    pdfs: Sequence[InputPDF]
    bus: EventBus = field(default_factory=EventBus)
    doc_concurrency: int = 3

    async def run(self) -> PatientCase:
        set_current_bus(self.bus)
        try:
            case = await self._run_inner()
        finally:
            await self.bus.emit(EventKind.DONE, "Run complete", {"case_id": self.case_id})
            await self.bus.close()
            set_current_bus(None)
        return case

    async def _run_inner(self) -> PatientCase:
        await self.bus.emit(
            EventKind.LOG,
            f"Starting case {self.case_id} · {len(self.pdfs)} documents",
            {"case_id": self.case_id, "doc_count": len(self.pdfs)},
        )

        # 1. Per-doc extraction (text + per-page VLM) — bounded concurrency
        await self.bus.emit(
            EventKind.TOOL_START,
            f"Extracting {len(self.pdfs)} documents",
        )
        sem = asyncio.Semaphore(self.doc_concurrency)

        async def _one(pdf: InputPDF) -> DocumentExtraction:
            async with sem:
                return await extract_document(pdf.filename, pdf.data)

        documents: list[DocumentExtraction] = await asyncio.gather(
            *[_one(p) for p in self.pdfs]
        )

        # 2. Kimi K2 cross-doc aggregation
        (
            pathology,
            intake,
            mutations,
            provenance,
            conflicts,
        ) = await aggregate_documents(documents)

        # 2.5. Enrichment — compute TMB from mutations (always runs; silent when
        #      the list is empty). Without this, the walker sees "TMB: unknown"
        #      at the systemic-therapy phase.
        enriched: EnrichedBiomarkers = await enrich(mutations=mutations)

        # 2.6. Primary cancer detection — seeds the RAG query + phase prompts.
        primary_cancer_type = detect_primary_cancer(pathology, mutations)

        # Bundle the case shell
        case = PatientCase(
            case_id=self.case_id,
            pathology=pathology,
            primary_cancer_type=primary_cancer_type,
            intake=intake,
            enrichment=enriched,
            mutations=mutations,
            documents=documents,
            provenance=provenance,
            conflicts=conflicts,
            pdf_text_excerpt=(documents[0].text_excerpt if documents else ""),
        )
        await self.bus.emit(EventKind.CASE_UPDATE, "Case shell ready", case.model_dump())

        # Legacy event for frontend components still keyed on PDF_EXTRACTED
        await self.bus.emit(
            EventKind.PDF_EXTRACTED,
            f"Canonical record · {primary_cancer_type} · {len(mutations)} mutations · "
            f"{len(provenance)} provenance entries · {len(conflicts)} conflicts",
            {
                "pathology": pathology.model_dump(),
                "intake": intake.model_dump(),
                "enrichment": enriched.model_dump(),
                "mutations": [m.model_dump() for m in mutations],
                "provenance": [p.model_dump() for p in provenance],
                "conflicts": conflicts,
                "doc_count": len(documents),
                "primary_cancer_type": primary_cancer_type,
            },
        )

        # 3. Dynamic railway walk (4 phases grounded in phase-2+ trial RAG)
        state = PatientState(
            pathology=pathology,
            mutations=mutations,
            tumor_mutational_burden=enriched.tmb_mut_per_mb,
        )
        walker = DynamicRailwayWalker(state=state, cancer_type=primary_cancer_type)
        steps = await walker.walk()
        rmap = build_map(
            steps,
            final_recommendation=final_recommendation_from_steps(steps),
        )
        case.railway = rmap
        case.final_recommendation = rmap.final_recommendation
        await self.bus.emit(
            EventKind.RAILWAY_READY,
            f"Railway ready — {len(steps)} nodes",
            {"railway": rmap.model_dump()},
        )
        await self.bus.emit(EventKind.CASE_UPDATE, "Railway attached", case.model_dump())

        # 4 + 5. Trials + sites
        matches: list[TrialMatch] = evaluate_all(case)
        case.trial_matches = matches
        await self.bus.emit(
            EventKind.TRIAL_MATCHES_READY,
            f"{sum(1 for m in matches if m.status == 'eligible')} eligible / "
            f"{len(matches)} total",
            {"matches": [m.model_dump() for m in matches]},
        )

        relevant = [m.nct_id for m in matches if m.status != "ineligible"]
        sites: list[TrialSite] = await fetch_trial_sites(relevant) if relevant else []
        case.trial_sites = sites
        await self.bus.emit(
            EventKind.TRIAL_SITES_READY,
            f"{len(sites)} trial sites geocoded",
            {"sites": [s.model_dump() for s in sites]},
        )

        await self.bus.emit(EventKind.CASE_UPDATE, "Case complete", case.model_dump())
        return case


__all__ = ["PatientOrchestrator", "InputPDF"]


_ = EnrichedBiomarkers  # re-exported via models; silence unused-import lint
_ = PathologyFindings
_ = ClinicianIntake
