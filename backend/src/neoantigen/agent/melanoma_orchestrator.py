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

from ..cohort import (
    has_cohort,
    load_cohort,
    mutations_for_patient,
    find_twins,
    kaplan_meier,
)
from ..cohort import demo_intake
from ..cohort.tcga import TCGAPatient
from ..cohort.twins import QueryPatient
from ..enrichment import enrich as enrich_biomarkers
from ..external.regeneron_rules import REGENERON_TRIALS, evaluate as evaluate_regeneron
from ..external.trials import CTGovStudy, fetch_melanoma_trials
from ..models import (
    BiomarkerChip,
    ClinicianIntake,
    CohortSnapshot,
    EnrichedBiomarkers,
    MelanomaCase,
    Mutation,
    PathologyFindings,
    PipelineResult,
    SurvivalPoint,
    TrialMatch,
    TwinMatchRef,
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
    tcga_patient_id: str | None = None
    intake: ClinicianIntake | None = None

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
            source_label = "VCF"
            if self.tcga_patient_id and has_cohort():
                source_label = f"TCGA-SKCM ({self.tcga_patient_id})"
                mutations = mutations_for_patient(self.tcga_patient_id)
            elif self.vcf_path.exists():
                try:
                    mutations = parse_mutations(self.vcf_path)
                except Exception as e:
                    await self.bus.emit(EventKind.LOG, f"VCF parse failed: {e}")
            case.mutations = mutations
            await self.bus.emit(
                EventKind.TOOL_RESULT,
                f"🧬 Loaded {len(mutations)} mutations from {source_label}",
                {"mutations": [m.model_dump() for m in mutations]},
            )
            await self.bus.emit(
                EventKind.CASE_UPDATE, "mutations", {"mutations": [m.model_dump() for m in mutations]}
            )

            # 2b. Enrichment (TMB + UV signature + cBioPortal prior therapy)
            await self.bus.emit(EventKind.TOOL_START, "🧪 Enriching biomarkers")
            try:
                enrichment = await enrich_biomarkers(
                    mutations=mutations,
                    vcf_path=self.vcf_path if self.vcf_path and self.vcf_path.exists() else None,
                    tcga_submitter_id=self.tcga_patient_id,
                )
            except Exception as e:
                await self.bus.emit(EventKind.LOG, f"Enrichment partial: {e}")
                enrichment = EnrichedBiomarkers()
            case.enrichment = enrichment
            # Fall back to the curated demo registry when no clinician-entered
            # intake came through (CLI path, blank Streamlit form). Only fires
            # for the handful of submitter ids in DEMO_INTAKE — every other
            # patient still lands in needs_more_data as a real clinician would
            # expect. The identity of this object is later used by
            # _build_biomarker_chips to tag chips as curated.
            intake = self.intake or demo_intake.get(self.tcga_patient_id)
            if intake is not None:
                case.intake = intake
                # LAG-3 IHC: intake is the only source — copy onto pathology so
                # the NCCN walker's evidence_for() hasattr lookup and the
                # molecular panel both read one canonical location.
                if intake.lag3_ihc_percent is not None:
                    case.pathology.lag3_ihc_percent = intake.lag3_ihc_percent
            case.biomarker_chips = _build_biomarker_chips(case.pathology, enrichment, case.intake)
            await self.bus.emit(
                EventKind.ENRICHMENT_READY,
                _enrichment_label(enrichment),
                {
                    "enrichment": enrichment.model_dump(),
                    "biomarker_chips": [c.model_dump() for c in case.biomarker_chips],
                },
            )
            await self.bus.emit(
                EventKind.CASE_UPDATE,
                "enrichment",
                {
                    "enrichment": enrichment.model_dump(),
                    "biomarker_chips": [c.model_dump() for c in case.biomarker_chips],
                    "pathology": case.pathology.model_dump(),
                    "intake": case.intake.model_dump() if case.intake else None,
                },
            )

            # 3. NCCN walker — TMB from enrichment (exome denom) replaces the
            # naive missense-count heuristic so downstream IO-vs-chemo branches
            # route off a real mut/Mb value.
            tmb = enrichment.tmb_mut_per_mb if enrichment.tmb_mut_per_mb is not None else _estimate_tmb(mutations)
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
            # Panel 3 fires whenever we have mutations — the candidate peptides are
            # always informative even when the NCCN walk terminates early (e.g.
            # REBIOPSY when the slide is too faded for the VLM to confirm melanoma).
            # The walker's clinical recommendation is shown independently.
            wants_vaccine = bool(mutations)

            molecular_task = asyncio.create_task(build_landscape(mutations))
            trials_task = asyncio.create_task(self._match_trials(case))
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

            # 5b. Clinical trial matching (Regeneron overlay + generic CT.gov).
            try:
                case.trials = await trials_task
            except Exception as e:
                await self.bus.emit(EventKind.TOOL_ERROR, f"Trial matching failed: {e}")
                case.trials = []
            eligible_n = sum(1 for t in case.trials if t.status == "eligible")
            regeneron_n = sum(1 for t in case.trials if t.is_regeneron)
            await self.bus.emit(
                EventKind.TRIAL_MATCHES_READY,
                f"🧪 {len(case.trials)} trials shown · {eligible_n} eligible · {regeneron_n} Regeneron",
                {"trials": [t.model_dump() for t in case.trials]},
            )

            # 6. Cohort match (Panel 4) — only when running on a TCGA patient.
            if self.tcga_patient_id and has_cohort():
                case.cohort = await self._build_cohort_snapshot(case)

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
            try:
                scorer = build_scorer("mhcflurry", self.hla_allele)
            except Exception as e:
                await self.bus.emit(
                    EventKind.TOOL_ERROR,
                    f"⚠ MHCflurry unavailable ({e}). Falling back to heuristic scorer — "
                    "reported nM values are NOT real predictions.",
                )
                scorer = build_scorer("heuristic", self.hla_allele)
            config = RunConfig(scorer=scorer, top_n=10, max_nm=500.0)
            return await asyncio.to_thread(run_pipeline_sync, mutations, config, console=Console(quiet=True))
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Pipeline failed: {e}")
            return None

    async def _match_trials(self, case: MelanomaCase) -> list[TrialMatch]:
        """Fetch recruiting melanoma trials from CT.gov and evaluate Regeneron rules.

        Non-Regeneron trials are returned with status='unscored' (surfaced in UI
        but not structurally matched). Sort order: Regeneron-eligible first,
        then Regeneron needs_more_data, then other trials, then ineligible.

        When running on a TCGA patient, the matching clinical record (age,
        AJCC stage) is passed to the evaluator to resolve age / stage gates.
        """
        await self.bus.emit(EventKind.TOOL_START, "🧪 Matching clinical trials")

        tcga_record: TCGAPatient | None = None
        if self.tcga_patient_id and has_cohort():
            try:
                cohort = load_cohort()
                tcga_record = next(
                    (p for p in cohort if p.submitter_id == self.tcga_patient_id),
                    None,
                )
            except Exception as e:
                await self.bus.emit(EventKind.LOG, f"TCGA clinical lookup failed: {e}")

        try:
            studies: list[CTGovStudy] = await fetch_melanoma_trials()
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"CT.gov fetch failed: {e}")
            return []

        matches: list[TrialMatch] = []
        seen_ids: set[str] = set()
        for study in studies:
            seen_ids.add(study.nct_id)
            if study.nct_id in REGENERON_TRIALS:
                m = evaluate_regeneron(case, REGENERON_TRIALS[study.nct_id], tcga=tcga_record)
                m.title = study.brief_title or m.title
                m.sponsor = study.sponsor or m.sponsor
                m.phase = study.phase or m.phase
                m.overall_status = study.overall_status
                m.site_contacts = study.site_contacts
                m.url = study.url
            else:
                m = TrialMatch(
                    nct_id=study.nct_id,
                    title=study.brief_title,
                    sponsor=study.sponsor,
                    phase=study.phase,
                    status="unscored",
                    is_regeneron=False,
                    site_contacts=study.site_contacts,
                    overall_status=study.overall_status,
                    url=study.url,
                )
            matches.append(m)

        # If any Regeneron trial is in our registry but CT.gov didn't return it
        # (e.g. status changed to completed/closed), still evaluate so the UI
        # can show the historical match.
        for nct_id, rule in REGENERON_TRIALS.items():
            if nct_id in seen_ids:
                continue
            m = evaluate_regeneron(case, rule, tcga=tcga_record)
            m.overall_status = "NOT_RECRUITING"
            matches.append(m)

        def _rank(t: TrialMatch) -> tuple[int, str]:
            if t.is_regeneron and t.status == "eligible":
                return (0, t.nct_id)
            if t.is_regeneron and t.status == "needs_more_data":
                return (1, t.nct_id)
            if not t.is_regeneron:
                return (2, t.nct_id)
            return (3, t.nct_id)  # regeneron ineligible last

        matches.sort(key=_rank)
        return matches

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


    async def _build_cohort_snapshot(self, case: MelanomaCase) -> CohortSnapshot | None:
        await self.bus.emit(EventKind.TOOL_START, "🧑‍🤝‍🧑 Twin-matching against TCGA-SKCM cohort")
        try:
            cohort = load_cohort()
        except Exception as e:
            await self.bus.emit(EventKind.TOOL_ERROR, f"Cohort load failed: {e}")
            return None
        if not cohort:
            return None

        demo = next((p for p in cohort if p.submitter_id == self.tcga_patient_id), None)
        others = [p for p in cohort if p.submitter_id != self.tcga_patient_id]

        query = QueryPatient(
            braf_v600e=demo.braf_v600e if demo else any(
                m.gene == "BRAF" and m.position == 600 and m.alt_aa == "E" for m in case.mutations
            ),
            nras_q61=demo.nras_q61 if demo else any(
                m.gene == "NRAS" and m.position == 61 for m in case.mutations
            ),
            kit_mutant=demo.kit_mutant if demo else any(m.gene == "KIT" for m in case.mutations),
            nf1_mutant=demo.nf1_mutant if demo else any(m.gene == "NF1" for m in case.mutations),
            stage_bucket=demo.stage_bucket if demo else "Unknown",
            age=demo.age_at_diagnosis if demo else None,
            mutated_genes={m.gene for m in case.mutations},
        )

        twin_matches = find_twins(query, others, top_k=10)
        twins_for_curve = [t.patient for t in twin_matches]
        overall_curve = kaplan_meier(others)
        twin_curve = kaplan_meier(twins_for_curve)

        snapshot = CohortSnapshot(
            cohort_size=len(others),
            twins=[
                TwinMatchRef(
                    submitter_id=t.patient.submitter_id,
                    similarity=t.similarity,
                    matching_features=t.matching_features,
                    stage=t.patient.stage,
                    age_at_diagnosis=t.patient.age_at_diagnosis,
                    vital_status=t.patient.vital_status,
                    survival_days=t.patient.survival_days,
                    mutated_drivers=sorted(
                        g for g in t.patient.mutated_genes
                        if g in {"BRAF", "NRAS", "KIT", "NF1", "TP53", "PTEN", "CDKN2A"}
                    ),
                )
                for t in twin_matches
            ],
            overall_curve=[
                SurvivalPoint(days=p.days, survival=p.survival, at_risk=p.at_risk, events_so_far=p.events_so_far)
                for p in overall_curve
            ],
            twin_curve=[
                SurvivalPoint(days=p.days, survival=p.survival, at_risk=p.at_risk, events_so_far=p.events_so_far)
                for p in twin_curve
            ],
            median_survival_days=_median_survival(overall_curve),
            twin_median_survival_days=_median_survival(twin_curve),
        )

        await self.bus.emit(
            EventKind.COHORT_TWINS_READY,
            f"🧑‍🤝‍🧑 {len(snapshot.twins)} twins matched (median sim {twin_matches[0].similarity if twin_matches else 0:.2f})",
            {"twins": [t.model_dump() for t in snapshot.twins]},
        )
        await self.bus.emit(
            EventKind.SURVIVAL_CURVE_READY,
            f"📈 KM curve ready (cohort n={snapshot.cohort_size}, twin median {snapshot.twin_median_survival_days}d)",
            {
                "overall_curve": [p.model_dump() for p in snapshot.overall_curve],
                "twin_curve": [p.model_dump() for p in snapshot.twin_curve],
                "median_survival_days": snapshot.median_survival_days,
                "twin_median_survival_days": snapshot.twin_median_survival_days,
                "cohort_size": snapshot.cohort_size,
            },
        )
        return snapshot


def _estimate_tmb(mutations: list[Mutation]) -> float:
    """Crude proxy: missense count / 1 Mb. Real TMB needs full-exome context;
    this is enough for the demo to drive 'high TMB' branches when relevant."""
    return float(len(mutations))


def _enrichment_label(enrichment: EnrichedBiomarkers) -> str:
    parts: list[str] = []
    if enrichment.tmb_mut_per_mb is not None:
        parts.append(f"TMB {enrichment.tmb_mut_per_mb:.1f} mut/Mb")
    if enrichment.uv_signature_fraction is not None:
        parts.append(f"UV {enrichment.uv_signature_fraction:.0%}")
    if enrichment.prior_systemic_therapies:
        parts.append(f"{len(enrichment.prior_systemic_therapies)} prior Rx")
    return "🧪 " + " · ".join(parts) if parts else "🧪 Enrichment: no signals"


def _build_biomarker_chips(
    pathology: PathologyFindings,
    enrichment: EnrichedBiomarkers,
    intake: ClinicianIntake | None,
) -> list[BiomarkerChip]:
    """Normalize VLM + TCGA/VCF + intake datapoints into a single chip list.

    The provenance tag lets the UI colour each chip by source so clinicians
    can tell what came from the slide vs. the molecular pipeline vs. their
    own form entry."""
    chips: list[BiomarkerChip] = []

    # VLM-derived (from pathology slide)
    if pathology.pdl1_estimate != "unknown":
        chips.append(BiomarkerChip(
            label="PD-L1",
            value=pathology.pdl1_estimate,
            source="vlm",
            tooltip="Estimated from H&E slide by the VLM",
        ))
    if pathology.tils_present != "unknown":
        chips.append(BiomarkerChip(
            label="TILs",
            value=pathology.tils_present.replace("_", " "),
            source="vlm",
            tooltip="Tumour-infiltrating lymphocytes — slide read",
        ))

    # VCF/computed
    if enrichment.tmb_mut_per_mb is not None:
        chips.append(BiomarkerChip(
            label="TMB",
            value=f"{enrichment.tmb_mut_per_mb:.1f} mut/Mb",
            source="vcf",
            tooltip="Tumour mutational burden — missense count / 30 Mb exome",
        ))
    if enrichment.uv_signature_fraction is not None:
        chips.append(BiomarkerChip(
            label="UV signature",
            value=f"{enrichment.uv_signature_fraction:.0%}",
            source="vcf",
            tooltip=f"Fraction of SNVs matching SBS7 (n={enrichment.total_snvs_scored})",
        ))

    # cBioPortal
    if enrichment.prior_anti_pd1 is not None:
        chips.append(BiomarkerChip(
            label="Prior anti-PD-1",
            value="yes" if enrichment.prior_anti_pd1 else "no",
            source="cbioportal",
            tooltip="Derived from cBioPortal skcm_tcga clinical record",
        ))

    # Clinician intake. Curated demo patients flow through the same block but
    # get a distinct "curated_demo" source so the UI can render a dashed/muted
    # badge and nothing looks like real patient data.
    if intake is not None:
        src = "curated_demo" if demo_intake.is_curated(intake) else "intake"
        src_tip = (
            "Hand-curated demo data — not from a patient record"
            if src == "curated_demo"
            else "Clinician intake (LAG-3 IHC not extractable from H&E)"
        )
        if intake.lag3_ihc_percent is not None:
            chips.append(BiomarkerChip(
                label="LAG-3 IHC",
                value=f"{intake.lag3_ihc_percent:.0f}%",
                source=src,
                tooltip=src_tip,
            ))
        if intake.ecog is not None:
            chips.append(BiomarkerChip(
                label="ECOG",
                value=str(intake.ecog),
                source=src,
                tooltip=src_tip if src == "curated_demo" else None,
            ))

    return chips


def _median_survival(curve) -> int | None:
    """First time the KM step function crosses 0.5."""
    for pt in curve:
        if pt.survival <= 0.5:
            return pt.days
    return None
