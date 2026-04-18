"""Step-level helpers called by the deterministic orchestrator.

Each function is a thin adapter around an existing pipeline / discovery /
communications capability. Every function emits `TOOL_START` + `TOOL_RESULT`
(or a semantic variant) events so the Streamlit UI can render a live feed,
plus a `CASE_UPDATE` event carrying the structured payload that
`build_case_file()` will later replay into a CaseFile.

Functions return the raw payload dict/list so the orchestrator can branch
on it for the next step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..external.clinicaltrials import search_trials
from ..external.dgidb import search_drugs
from ..pipeline.parser import parse as parse_mutations
from ..pipeline.runner import RunConfig, run as run_pipeline_sync
from ..pipeline.scoring import build_scorer
from .events import EventKind, emit


# ─────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────


async def run_neoantigen_pipeline(
    vcf_path: Path,
    species: str = "canine",
    allele: str = "DLA-88*50101",
    top_n: int = 15,
    max_nm: float = 500.0,
) -> dict[str, Any]:
    await emit(
        EventKind.TOOL_START,
        "🧬 Analyzing tumor genome",
        {"vcf": str(vcf_path), "species": species, "allele": allele},
    )

    try:
        mutations = parse_mutations(vcf_path)
        if not mutations:
            await emit(EventKind.TOOL_ERROR, "No mutations parsed from VCF")
            return {"error": "no mutations in VCF"}

        scorer_name = "dla-heuristic" if allele.startswith("DLA") else "heuristic"
        config = RunConfig(
            scorer=build_scorer(scorer_name, allele),
            top_n=top_n,
            max_nm=max_nm,
            with_apis=False,
            species=species,
        )
        result = run_pipeline_sync(mutations, config)
    except Exception as e:
        await emit(EventKind.TOOL_ERROR, f"Pipeline failed: {e}")
        return {"error": str(e)}

    genes = sorted({m.gene for m in result.mutations if getattr(m, "gene", None)})
    top = result.candidates[0] if result.candidates else None

    summary: dict[str, Any] = {
        "mutations_found": len(result.mutations),
        "candidates": len(result.candidates),
        "genes": genes,
        "top_candidate": (
            {
                "sequence": top.peptide.sequence,
                "mutation": top.peptide.mutation.full_label,
                "score_nm": top.peptide.score_nm,
            }
            if top
            else None
        ),
        "construct_length_bp": result.vaccine.length_bp if result.vaccine else 0,
        "estimated_cost_usd": result.vaccine.estimated_cost_usd if result.vaccine else 0,
    }

    await emit(
        EventKind.TOOL_RESULT,
        f"💊 Scored {len(result.mutations)} mutations → {len(result.candidates)} candidates",
        {"summary": summary, "result_json": result.model_dump()},
    )
    await emit(
        EventKind.CASE_UPDATE,
        "pipeline",
        {"pipeline_result": result.model_dump()},
    )
    return summary


async def find_drug_interactions(genes: list[str]) -> list[dict[str, Any]]:
    import httpx

    genes_upper = [g.upper() for g in genes]
    await emit(
        EventKind.TOOL_START,
        f"🔎 Searching DGIdb for drugs targeting {', '.join(genes_upper) or 'N/A'}",
    )

    async with httpx.AsyncClient() as client:
        drugs_lists = []
        for g in genes_upper:
            try:
                drugs_lists.append(await search_drugs(client, g))
            except Exception as e:
                await emit(EventKind.LOG, f"DGIdb error for {g}: {e}")

    drugs = [d for sub in drugs_lists for d in sub]
    unique_drugs = list({(d.gene, d.drug_name): d for d in drugs}.values())
    payload = [d.model_dump() for d in unique_drugs[:20]]

    await emit(
        EventKind.TOOL_RESULT,
        f"💊 Found {len(unique_drugs)} drug interactions",
        {"drugs": payload},
    )
    return payload


async def find_clinical_trials(genes: list[str], cancer_type: str = "") -> list[dict[str, Any]]:
    import httpx

    genes_upper = [g.upper() for g in genes]
    await emit(
        EventKind.TOOL_START,
        f"🧪 Searching ClinicalTrials.gov for {cancer_type or 'relevant'} trials",
    )

    async with httpx.AsyncClient() as client:
        trial_lists = []
        for g in genes_upper:
            try:
                trial_lists.append(await search_trials(client, g))
            except Exception as e:
                await emit(EventKind.LOG, f"ClinicalTrials error for {g}: {e}")

    trials = [t for sub in trial_lists for t in sub]
    unique = list({t.nct_id: t for t in trials}.values())
    payload = [t.model_dump() for t in unique[:15]]

    await emit(
        EventKind.TOOL_RESULT,
        f"🧪 Found {len(unique)} clinical trials",
        {"trials": payload},
    )
    return payload


# ─────────────────────────────────────────────────────────────
# Discovery (pathology, labs, structure)
# ─────────────────────────────────────────────────────────────


async def read_pathology(pdf_path: Path) -> dict[str, Any]:
    from .pathology import extract_pathology

    await emit(EventKind.TOOL_START, f"🔬 Reading pathology report from {pdf_path.name}")

    try:
        report = await extract_pathology(pdf_path)
    except Exception as e:
        await emit(EventKind.TOOL_ERROR, f"Pathology extraction failed: {e}")
        return {"error": str(e)}

    payload = report.model_dump()
    await emit(
        EventKind.TOOL_RESULT,
        f"📋 {report.patient_name} — {report.cancer_type}"
        + (f" grade {report.grade}" if report.grade else "")
        + (f" at {report.location}" if report.location else ""),
        {"pathology": payload},
    )
    await emit(EventKind.CASE_UPDATE, "pathology", {"pathology": payload})
    return payload


async def find_sequencing_labs(location: str, radius_km: int = 50) -> list[dict[str, Any]]:
    from .labs import find_sequencing_labs as _find

    await emit(EventKind.TOOL_START, f"🏥 Finding sequencing labs near {location}")
    labs = await _find(location, radius_km=radius_km)
    payload = [l.model_dump() for l in labs]
    await emit(
        EventKind.TOOL_RESULT,
        f"🏥 Found {len(labs)} sequencing labs",
        {"labs": payload},
    )
    await emit(EventKind.CASE_UPDATE, "sequencing_labs", {"labs": payload})
    return payload


async def find_vet_oncologists(location: str, radius_km: int = 50) -> list[dict[str, Any]]:
    from .labs import find_vet_oncologists as _find

    await emit(EventKind.TOOL_START, f"👨‍⚕️ Finding vet oncologists near {location}")
    vets = await _find(location, radius_km=radius_km)
    payload = [v.model_dump() for v in vets]
    await emit(
        EventKind.TOOL_RESULT,
        f"👨‍⚕️ Found {len(vets)} vet oncologists",
        {"vets": payload},
    )
    await emit(EventKind.CASE_UPDATE, "vet_oncologists", {"vets": payload})
    return payload


async def find_synthesis_vendors(mrna_length_bp: int = 600) -> list[dict[str, Any]]:
    from .labs import find_synthesis_vendors as _find

    await emit(EventKind.TOOL_START, "💉 Finding mRNA synthesis + LNP vendors")
    vendors = _find(mrna_length_bp)
    payload = [v.model_dump() for v in vendors]
    await emit(
        EventKind.TOOL_RESULT,
        f"💉 {len(vendors)} vendors matched",
        {"vendors": payload},
    )
    await emit(EventKind.CASE_UPDATE, "synthesis_vendors", {"vendors": payload})
    return payload


async def validate_structure_3d(
    peptide: str,
    dla_allele: str = "DLA-88*50101",
    mutation_label: str = "",
) -> dict[str, Any]:
    from .structure import dock_peptide

    await emit(EventKind.TOOL_START, f"🔭 Docking {peptide} into {dla_allele}")

    try:
        pose = await dock_peptide(peptide=peptide, allele=dla_allele, mutation_label=mutation_label)
    except Exception as e:
        await emit(EventKind.TOOL_ERROR, f"Structure prediction failed: {e}")
        return {"error": str(e)}

    payload = pose.model_dump()
    await emit(
        EventKind.STRUCTURE_READY,
        f"🔭 {peptide} docked into {dla_allele} (method: {pose.method})",
        {"pose": payload},
    )
    await emit(EventKind.CASE_UPDATE, "structure", {"pose": payload})
    return payload


# ─────────────────────────────────────────────────────────────
# Communications
# ─────────────────────────────────────────────────────────────


async def draft_email(
    recipient_type: str,
    recipient_name: str,
    recipient_email: str = "",
    context: str = "",
) -> dict[str, Any]:
    from .emails import draft_email as _draft

    await emit(EventKind.TOOL_START, f"📧 Drafting email to {recipient_name}")
    draft = await _draft(
        recipient_type=recipient_type,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        context=context,
    )
    payload = draft.model_dump()
    await emit(
        EventKind.EMAIL_DRAFTED,
        f"📧 Email ready: '{draft.subject}' → {recipient_name}",
        {"email": payload},
    )
    await emit(EventKind.CASE_UPDATE, "email", {"email": payload})
    return payload


async def generate_timeline(start_week: int = 1, species: str = "canine") -> list[dict[str, Any]]:
    from .timeline import generate_timeline as _gen

    await emit(EventKind.TOOL_START, "📅 Generating treatment timeline")
    events = _gen(start_week=start_week, species=species)
    payload = [e.model_dump() for e in events]
    await emit(
        EventKind.TOOL_RESULT,
        f"📅 {len(events)}-week treatment plan",
        {"timeline": payload},
    )
    await emit(EventKind.CASE_UPDATE, "timeline", {"timeline": payload})
    return payload


async def explain_case_to_owner(
    patient_name: str,
    cancer_type: str,
    candidate_count: int,
    top_mutation: str,
) -> str:
    from .explain import explain_case

    await emit(EventKind.TOOL_START, "📝 Writing plain-English explanation")
    text = await explain_case(
        patient_name=patient_name,
        cancer_type=cancer_type,
        candidate_count=candidate_count,
        top_mutation=top_mutation,
    )
    await emit(
        EventKind.TOOL_RESULT,
        "📝 Explanation ready",
        {"explanation": text},
    )
    await emit(EventKind.CASE_UPDATE, "plain_english", {"plain_english": text})
    return text
