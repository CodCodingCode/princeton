"""Patient-flow orchestrator — drop-in replacement for melanoma_orchestrator.

Flow (one call per case):

  1. PDF bytes in → extract text + structured oncology fields
  2. NCCN railway walk (streams THINKING_DELTA + RAILWAY_STEP events)
  3. Regeneron trial matching (parallel with 4)
  4. Trial-site geocoding for matched NCTs
  5. Final PatientCase bundled; DONE event emitted

All stages degrade silently when optional inputs (MHCflurry, RAG, Google Maps
API key, LLM endpoint) are missing — callers get a partial ``PatientCase``
with ``needs_more_data`` everywhere, not an exception.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..external.regeneron_rules import evaluate_all
from ..external.trial_sites import fetch_trial_sites
from ..io.pdf_extract import PDFExtraction, extract_oncology_fields
from ..models import (
    ClinicianIntake,
    EnrichedBiomarkers,
    Mutation,
    PathologyFindings,
    PatientCase,
    TrialMatch,
    TrialSite,
)
from ..nccn.railway import build_map
from ..nccn.walker import (
    PatientState,
    RailwayWalker,
    final_recommendation_from_steps,
)
from .events import EventBus, EventKind, set_current_bus


@dataclass
class PatientOrchestrator:
    case_id: str
    pdf_bytes: bytes
    bus: EventBus = field(default_factory=EventBus)

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
            EventKind.LOG, f"Starting case {self.case_id}", {"case_id": self.case_id}
        )

        # 1. PDF extraction -------------------------------------------------
        await self.bus.emit(EventKind.TOOL_START, "Extracting pathology PDF")
        extraction: PDFExtraction = await extract_oncology_fields(self.pdf_bytes)
        pathology: PathologyFindings = extraction.pathology
        intake: ClinicianIntake = extraction.intake
        mutations: list[Mutation] = extraction.mutations
        await self.bus.emit(
            EventKind.PDF_EXTRACTED,
            f"Extracted {len(mutations)} mutations, T-stage {pathology.t_stage}",
            {
                "pathology": pathology.model_dump(),
                "intake": intake.model_dump(),
                "mutations": [m.model_dump() for m in mutations],
                "used_vision_fallback": extraction.used_vision_fallback,
            },
        )

        case = PatientCase(
            case_id=self.case_id,
            pathology=pathology,
            intake=intake,
            mutations=mutations,
            pdf_text_excerpt=extraction.raw_text[:2000],
        )
        await self.bus.emit(EventKind.CASE_UPDATE, "Case shell ready", case.model_dump())

        # 2. NCCN railway walk ---------------------------------------------
        state = PatientState(pathology=pathology, mutations=mutations)
        walker = RailwayWalker(state=state)
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

        # 3 + 4. Trials + sites (parallel) ---------------------------------
        async def match_trials() -> list[TrialMatch]:
            # Regeneron rules are pure CPU — just call sync.
            return evaluate_all(case)

        async def hydrate_sites(matches: list[TrialMatch]) -> list[TrialSite]:
            # Only fetch sites for trials the patient isn't outright excluded from.
            relevant = [m.nct_id for m in matches if m.status != "ineligible"]
            if not relevant:
                return []
            return await fetch_trial_sites(relevant)

        matches = await match_trials()
        case.trial_matches = matches
        await self.bus.emit(
            EventKind.TRIAL_MATCHES_READY,
            f"{sum(1 for m in matches if m.status == 'eligible')} eligible / {len(matches)} total",
            {"matches": [m.model_dump() for m in matches]},
        )

        sites = await hydrate_sites(matches)
        case.trial_sites = sites
        await self.bus.emit(
            EventKind.TRIAL_SITES_READY,
            f"{len(sites)} trial sites geocoded",
            {"sites": [s.model_dump() for s in sites]},
        )

        await self.bus.emit(EventKind.CASE_UPDATE, "Case complete", case.model_dump())
        return case


__all__ = ["PatientOrchestrator"]


# Re-export EnrichedBiomarkers so downstream modules can construct one if they
# want to layer computed TMB/UV into the case (currently unused in the default
# flow — the PDF extractor fills intake directly).
_ = EnrichedBiomarkers
