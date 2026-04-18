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
import sys
import time
import traceback
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
    doc_concurrency: int = 10

    async def _stage_start(self, num: str, name: str) -> float:
        msg = f"[stage {num}] ▶ START · {name}"
        print(msg, flush=True, file=sys.stderr)
        await self.bus.emit(EventKind.LOG, msg, {"stage": num, "phase": "start"})
        return time.time()

    async def _stage_done(self, num: str, name: str, t0: float, detail: str = "") -> None:
        dt = time.time() - t0
        tail = f" · {detail}" if detail else ""
        msg = f"[stage {num}] ✓ DONE  · {name} ({dt:.2f}s){tail}"
        print(msg, flush=True, file=sys.stderr)
        await self.bus.emit(
            EventKind.LOG, msg, {"stage": num, "phase": "done", "seconds": dt}
        )

    async def _stage_fail(self, num: str, name: str, exc: BaseException) -> None:
        tb = traceback.format_exc()
        msg = f"[stage {num}] ✗ FAIL  · {name}: {exc!r}"
        print(msg, flush=True, file=sys.stderr)
        print(tb, flush=True, file=sys.stderr)
        await self.bus.emit(
            EventKind.TOOL_ERROR,
            msg,
            {"stage": num, "phase": "fail", "error": repr(exc), "traceback": tb},
        )

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
        banner = f"=== Starting case {self.case_id} · {len(self.pdfs)} document(s) ==="
        print(banner, flush=True, file=sys.stderr)
        await self.bus.emit(
            EventKind.LOG,
            banner,
            {"case_id": self.case_id, "doc_count": len(self.pdfs)},
        )

        # ── Stage 1: Per-doc extraction (text + per-page VLM), bounded concurrency ──
        t0 = await self._stage_start("1", "Per-doc extraction (pypdf + MediX VLM)")
        total_pdfs = len(self.pdfs)
        await self.bus.emit(
            EventKind.TOOL_START,
            f"Extracting {total_pdfs} documents",
            {"phase": "extract_start", "total": total_pdfs, "stage": "1"},
        )
        try:
            sem = asyncio.Semaphore(self.doc_concurrency)
            done_counter = {"n": 0}

            async def _one(pdf: InputPDF) -> DocumentExtraction:
                async with sem:
                    print(
                        f"[stage 1]   · extracting {pdf.filename} ({len(pdf.data)} bytes)",
                        flush=True,
                        file=sys.stderr,
                    )
                    await self.bus.emit(
                        EventKind.LOG,
                        f"Extracting {pdf.filename} ({len(pdf.data)} bytes)",
                        {
                            "phase": "extract_file_start",
                            "stage": "1",
                            "filename": pdf.filename,
                            "bytes": len(pdf.data),
                        },
                    )
                    doc = await extract_document(pdf.filename, pdf.data)
                    done_counter["n"] += 1
                    print(
                        f"[stage 1]   · extracted  {pdf.filename} "
                        f"· {len(doc.text_excerpt)} chars "
                        f"({done_counter['n']}/{total_pdfs})",
                        flush=True,
                        file=sys.stderr,
                    )
                    await self.bus.emit(
                        EventKind.LOG,
                        f"Extracted {pdf.filename} · {len(doc.text_excerpt)} chars "
                        f"({done_counter['n']}/{total_pdfs})",
                        {
                            "phase": "extract_progress",
                            "stage": "1",
                            "done": done_counter["n"],
                            "total": total_pdfs,
                            "filename": pdf.filename,
                            "chars": len(doc.text_excerpt),
                            "bytes": len(pdf.data),
                        },
                    )
                    return doc

            documents: list[DocumentExtraction] = await asyncio.gather(
                *[_one(p) for p in self.pdfs]
            )
        except Exception as e:
            await self._stage_fail("1", "Per-doc extraction", e)
            raise
        await self._stage_done(
            "1",
            "Per-doc extraction",
            t0,
            f"{len(documents)} doc(s) extracted",
        )

        # ── Stage 2: Kimi K2 cross-doc aggregation ─────────────────────────────
        t0 = await self._stage_start(
            "2", "Cross-doc aggregation (Kimi K2 → canonical record)"
        )
        try:
            (
                pathology,
                intake,
                mutations,
                provenance,
                conflicts,
            ) = await aggregate_documents(documents)
        except Exception as e:
            await self._stage_fail("2", "Cross-doc aggregation", e)
            raise
        await self._stage_done(
            "2",
            "Cross-doc aggregation",
            t0,
            f"{len(mutations)} mutation(s) · {len(provenance)} provenance · "
            f"{len(conflicts)} conflict(s)",
        )

        # ── Stage 3: Enrichment (TMB from mutations) ───────────────────────────
        t0 = await self._stage_start("3", "Enrichment (TMB from mutations)")
        try:
            enriched: EnrichedBiomarkers = await enrich(mutations=mutations)
        except Exception as e:
            await self._stage_fail("3", "Enrichment", e)
            raise
        await self._stage_done(
            "3",
            "Enrichment",
            t0,
            f"TMB={enriched.tmb_mut_per_mb}",
        )

        # ── Stage 4: Primary cancer detection ──────────────────────────────────
        t0 = await self._stage_start("4", "Primary cancer detection")
        try:
            primary_cancer_type = detect_primary_cancer(pathology, mutations)
        except Exception as e:
            await self._stage_fail("4", "Primary cancer detection", e)
            raise
        await self._stage_done(
            "4",
            "Primary cancer detection",
            t0,
            f"primary={primary_cancer_type}",
        )

        # ── Stage 5: Case shell assembled (CASE_UPDATE + PDF_EXTRACTED) ────────
        t0 = await self._stage_start("5", "Case shell assembled")
        try:
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
            await self.bus.emit(
                EventKind.CASE_UPDATE, "Case shell ready", case.model_dump()
            )
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
        except Exception as e:
            await self._stage_fail("5", "Case shell assembled", e)
            raise
        await self._stage_done("5", "Case shell assembled", t0)

        # ── Stage 6: Dynamic NCCN railway (4 phases, RAG-grounded) ─────────────
        t0 = await self._stage_start(
            "6", "Dynamic NCCN railway (4 phases, RAG-grounded)"
        )
        try:
            state = PatientState(
                pathology=pathology,
                mutations=mutations,
                tumor_mutational_burden=enriched.tmb_mut_per_mb,
            )
            walker = DynamicRailwayWalker(
                state=state, cancer_type=primary_cancer_type
            )
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
            await self.bus.emit(
                EventKind.CASE_UPDATE, "Railway attached", case.model_dump()
            )
        except Exception as e:
            await self._stage_fail("6", "Dynamic NCCN railway", e)
            raise
        await self._stage_done(
            "6", "Dynamic NCCN railway", t0, f"{len(steps)} node(s)"
        )

        # ── Stage 7: Regeneron trial matching ──────────────────────────────────
        t0 = await self._stage_start("7", "Regeneron trial matching")
        try:
            matches: list[TrialMatch] = evaluate_all(case)
            case.trial_matches = matches
            eligible_n = sum(1 for m in matches if m.status == "eligible")
            await self.bus.emit(
                EventKind.TRIAL_MATCHES_READY,
                f"{eligible_n} eligible / {len(matches)} total",
                {"matches": [m.model_dump() for m in matches]},
            )
        except Exception as e:
            await self._stage_fail("7", "Regeneron trial matching", e)
            raise
        await self._stage_done(
            "7",
            "Regeneron trial matching",
            t0,
            f"{eligible_n}/{len(matches)} eligible",
        )

        # ── Stage 8: Trial-site geocoding ──────────────────────────────────────
        t0 = await self._stage_start("8", "Trial-site geocoding")
        try:
            relevant = [m.nct_id for m in matches if m.status != "ineligible"]
            sites: list[TrialSite] = (
                await fetch_trial_sites(relevant) if relevant else []
            )
            case.trial_sites = sites
            await self.bus.emit(
                EventKind.TRIAL_SITES_READY,
                f"{len(sites)} trial sites geocoded",
                {"sites": [s.model_dump() for s in sites]},
            )
        except Exception as e:
            await self._stage_fail("8", "Trial-site geocoding", e)
            raise
        await self._stage_done(
            "8",
            "Trial-site geocoding",
            t0,
            f"{len(sites)} site(s) across {len(relevant)} NCT(s)",
        )

        await self.bus.emit(EventKind.CASE_UPDATE, "Case complete", case.model_dump())
        footer = f"=== Case {self.case_id} complete ==="
        print(footer, flush=True, file=sys.stderr)
        await self.bus.emit(EventKind.LOG, footer)
        return case


__all__ = ["PatientOrchestrator", "InputPDF"]


_ = EnrichedBiomarkers  # re-exported via models; silence unused-import lint
_ = PathologyFindings
_ = ClinicianIntake
