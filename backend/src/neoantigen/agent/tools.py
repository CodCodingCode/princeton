"""Claude Agent SDK tool wrappers.

Each tool is a thin adapter around existing pipeline functions (runner.run,
dgidb.search_drugs, etc.) or a new discovery/comms capability. Every tool emits
`tool_start` + `tool_result` events so the Streamlit UI can render a live feed.

Tools return dicts matching the SDK convention: {"content": [{"type": "text", "text": ...}]}.
Structured payloads are JSON-dumped so the agent can parse them on subsequent turns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from ..external.clinicaltrials import search_trials
from ..external.dgidb import search_drugs
from ..models import CaseFile, EmailDraft, LabMatch, PathologyReport, StructurePose, TimelineEvent
from ..pipeline.parser import parse as parse_mutations
from ..pipeline.runner import RunConfig, run as run_pipeline_sync
from ..pipeline.scoring import build_scorer
from .events import EventKind, emit


def _text(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        return {"content": [{"type": "text", "text": payload}]}
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str, indent=2)}]}


# ─────────────────────────────────────────────────────────────
# Pipeline tools
# ─────────────────────────────────────────────────────────────


@tool(
    "run_neoantigen_pipeline",
    "Run the end-to-end neoantigen vaccine pipeline on a VCF or TSV mutation file. "
    "Returns ranked peptide candidates + mRNA construct. "
    "Use after extracting pathology so you can pick the right species + DLA allele.",
    {
        "vcf_path": str,
        "species": str,
        "allele": str,
        "top_n": int,
        "max_nm": float,
    },
)
async def run_neoantigen_pipeline(args: dict[str, Any]) -> dict[str, Any]:
    vcf_path = Path(args["vcf_path"])
    species = args.get("species", "canine")
    allele = args.get("allele", "DLA-88*50101")
    top_n = int(args.get("top_n", 15))
    max_nm = float(args.get("max_nm", 500.0))

    await emit(EventKind.TOOL_START, "🧬 Analyzing tumor genome", {"vcf": str(vcf_path), "species": species, "allele": allele})

    try:
        mutations = parse_mutations(vcf_path)
        if not mutations:
            await emit(EventKind.TOOL_ERROR, "No mutations parsed from VCF")
            return _text({"error": "no mutations in VCF"})

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
        return _text({"error": str(e)})

    summary = {
        "mutations_found": len(result.mutations),
        "candidates": len(result.candidates),
        "top_candidate": {
            "sequence": result.candidates[0].peptide.sequence,
            "mutation": result.candidates[0].peptide.mutation.full_label,
            "score_nm": result.candidates[0].peptide.score_nm,
        }
        if result.candidates
        else None,
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
    return _text(summary)


@tool(
    "find_drug_interactions",
    "Query DGIdb for existing FDA-approved drugs targeting the mutated genes. "
    "Use after pipeline has identified mutations.",
    {"genes": list},
)
async def find_drug_interactions(args: dict[str, Any]) -> dict[str, Any]:
    import httpx

    genes = [g.upper() for g in args.get("genes", [])]
    await emit(EventKind.TOOL_START, f"🔎 Searching DGIdb for drugs targeting {', '.join(genes)}")

    async with httpx.AsyncClient() as client:
        drugs_lists = []
        for g in genes:
            try:
                drugs_lists.append(await search_drugs(client, g))
            except Exception as e:
                await emit(EventKind.LOG, f"DGIdb error for {g}: {e}")

    drugs = [d for sub in drugs_lists for d in sub]
    unique_drugs = list({(d.gene, d.drug_name): d for d in drugs}.values())

    await emit(
        EventKind.TOOL_RESULT,
        f"💊 Found {len(unique_drugs)} drug interactions",
        {"drugs": [d.model_dump() for d in unique_drugs[:20]]},
    )
    return _text(
        {
            "count": len(unique_drugs),
            "drugs": [
                {"gene": d.gene, "drug": d.drug_name, "interaction": d.interaction_types}
                for d in unique_drugs[:20]
            ],
        }
    )


@tool(
    "find_clinical_trials",
    "Search ClinicalTrials.gov for open trials relevant to the mutated genes. "
    "Filter by cancer type when possible.",
    {"genes": list, "cancer_type": str},
)
async def find_clinical_trials(args: dict[str, Any]) -> dict[str, Any]:
    import httpx

    genes = [g.upper() for g in args.get("genes", [])]
    cancer_type = args.get("cancer_type", "")
    await emit(EventKind.TOOL_START, f"🧪 Searching ClinicalTrials.gov for {cancer_type or 'relevant'} trials")

    async with httpx.AsyncClient() as client:
        trial_lists = []
        for g in genes:
            try:
                trial_lists.append(await search_trials(client, g))
            except Exception as e:
                await emit(EventKind.LOG, f"ClinicalTrials error for {g}: {e}")

    trials = [t for sub in trial_lists for t in sub]
    unique = list({t.nct_id: t for t in trials}.values())

    await emit(
        EventKind.TOOL_RESULT,
        f"🧪 Found {len(unique)} clinical trials",
        {"trials": [t.model_dump() for t in unique[:15]]},
    )
    return _text(
        {
            "count": len(unique),
            "trials": [
                {"nct_id": t.nct_id, "phase": t.phase, "status": t.status, "title": t.title, "url": t.url}
                for t in unique[:10]
            ],
        }
    )


# ─────────────────────────────────────────────────────────────
# Discovery tools (pathology, labs, structure)
# ─────────────────────────────────────────────────────────────


@tool(
    "read_pathology",
    "Extract structured fields from a pathology PDF (cancer type, grade, breed, age, location, prior treatments). "
    "Use this FIRST, before running the pipeline.",
    {"pdf_path": str},
)
async def read_pathology(args: dict[str, Any]) -> dict[str, Any]:
    from .pathology import extract_pathology

    pdf_path = Path(args["pdf_path"])
    await emit(EventKind.TOOL_START, f"🔬 Reading pathology report from {pdf_path.name}")

    try:
        report = await extract_pathology(pdf_path)
    except Exception as e:
        await emit(EventKind.TOOL_ERROR, f"Pathology extraction failed: {e}")
        return _text({"error": str(e)})

    await emit(
        EventKind.TOOL_RESULT,
        f"📋 {report.patient_name} — {report.cancer_type}"
        + (f" grade {report.grade}" if report.grade else "")
        + (f" at {report.location}" if report.location else ""),
        {"pathology": report.model_dump()},
    )
    await emit(EventKind.CASE_UPDATE, "pathology", {"pathology": report.model_dump()})
    return _text(report.model_dump())


@tool(
    "find_sequencing_labs",
    "Find tumor sequencing / genomics labs near the owner's location using Google Places API.",
    {"location": str, "radius_km": int},
)
async def find_sequencing_labs(args: dict[str, Any]) -> dict[str, Any]:
    from .labs import find_sequencing_labs as _find

    location = args["location"]
    radius_km = int(args.get("radius_km", 50))

    await emit(EventKind.TOOL_START, f"🏥 Finding sequencing labs near {location}")
    labs = await _find(location, radius_km=radius_km)
    await emit(
        EventKind.TOOL_RESULT,
        f"🏥 Found {len(labs)} sequencing labs",
        {"labs": [l.model_dump() for l in labs]},
    )
    await emit(EventKind.CASE_UPDATE, "sequencing_labs", {"labs": [l.model_dump() for l in labs]})
    return _text([l.model_dump() for l in labs])


@tool(
    "find_vet_oncologists",
    "Find board-certified veterinary oncologists near the owner's location.",
    {"location": str, "radius_km": int},
)
async def find_vet_oncologists(args: dict[str, Any]) -> dict[str, Any]:
    from .labs import find_vet_oncologists as _find

    location = args["location"]
    radius_km = int(args.get("radius_km", 50))

    await emit(EventKind.TOOL_START, f"👨‍⚕️ Finding vet oncologists near {location}")
    vets = await _find(location, radius_km=radius_km)
    await emit(
        EventKind.TOOL_RESULT,
        f"👨‍⚕️ Found {len(vets)} vet oncologists",
        {"vets": [v.model_dump() for v in vets]},
    )
    await emit(EventKind.CASE_UPDATE, "vet_oncologists", {"vets": [v.model_dump() for v in vets]})
    return _text([v.model_dump() for v in vets])


@tool(
    "find_synthesis_vendors",
    "Return curated list of mRNA synthesis + LNP vendors with pricing and lead times.",
    {"mrna_length_bp": int},
)
async def find_synthesis_vendors(args: dict[str, Any]) -> dict[str, Any]:
    from .labs import find_synthesis_vendors as _find

    length_bp = int(args.get("mrna_length_bp", 600))
    await emit(EventKind.TOOL_START, "💉 Finding mRNA synthesis + LNP vendors")

    vendors = _find(length_bp)
    await emit(
        EventKind.TOOL_RESULT,
        f"💉 {len(vendors)} vendors matched",
        {"vendors": [v.model_dump() for v in vendors]},
    )
    await emit(EventKind.CASE_UPDATE, "synthesis_vendors", {"vendors": [v.model_dump() for v in vendors]})
    return _text([v.model_dump() for v in vendors])


@tool(
    "validate_structure_3d",
    "Predict the 3D pose of a peptide docked into a DLA/MHC groove using PANDORA "
    "(falls back to ESMFold if PANDORA unavailable). Returns PDB text for rendering.",
    {"peptide": str, "dla_allele": str, "mutation_label": str},
)
async def validate_structure_3d(args: dict[str, Any]) -> dict[str, Any]:
    from .structure import dock_peptide

    peptide = args["peptide"]
    allele = args.get("dla_allele", "DLA-88*50101")
    mutation_label = args.get("mutation_label", "")

    await emit(EventKind.TOOL_START, f"🔭 Docking {peptide} into {allele}")

    try:
        pose = await dock_peptide(peptide=peptide, allele=allele, mutation_label=mutation_label)
    except Exception as e:
        await emit(EventKind.TOOL_ERROR, f"Structure prediction failed: {e}")
        return _text({"error": str(e)})

    await emit(
        EventKind.STRUCTURE_READY,
        f"🔭 {peptide} docked into {allele} (method: {pose.method})",
        {"pose": pose.model_dump()},
    )
    await emit(EventKind.CASE_UPDATE, "structure", {"pose": pose.model_dump()})
    return _text(
        {
            "peptide": pose.peptide_sequence,
            "allele": pose.dla_allele,
            "method": pose.method,
            "binding_energy_kcal_mol": pose.binding_energy_kcal_mol,
            "pdb_available": bool(pose.pdb_text),
        }
    )


# ─────────────────────────────────────────────────────────────
# Communications tools
# ─────────────────────────────────────────────────────────────


@tool(
    "draft_email",
    "Draft a professional email for a specific recipient type "
    "(sequencing_lab, synthesis_vendor, vet_oncologist, ethics_board, owner). "
    "Uses the accumulated case context to personalize the message.",
    {"recipient_type": str, "recipient_name": str, "recipient_email": str, "context": str},
)
async def draft_email(args: dict[str, Any]) -> dict[str, Any]:
    from .emails import draft_email as _draft

    recipient_type = args["recipient_type"]
    recipient_name = args["recipient_name"]
    recipient_email = args.get("recipient_email", "")
    context = args.get("context", "")

    await emit(EventKind.TOOL_START, f"📧 Drafting email to {recipient_name}")
    draft = await _draft(
        recipient_type=recipient_type,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        context=context,
    )
    await emit(
        EventKind.EMAIL_DRAFTED,
        f"📧 Email ready: '{draft.subject}' → {recipient_name}",
        {"email": draft.model_dump()},
    )
    await emit(EventKind.CASE_UPDATE, "email", {"email": draft.model_dump()})
    return _text({"subject": draft.subject, "recipient": draft.recipient_name, "body_preview": draft.body[:300]})


@tool(
    "generate_timeline",
    "Generate a week-by-week treatment timeline for the patient.",
    {"start_week": int, "species": str},
)
async def generate_timeline(args: dict[str, Any]) -> dict[str, Any]:
    from .timeline import generate_timeline as _gen

    start_week = int(args.get("start_week", 1))
    species = args.get("species", "canine")

    await emit(EventKind.TOOL_START, "📅 Generating treatment timeline")
    events = _gen(start_week=start_week, species=species)
    await emit(
        EventKind.TOOL_RESULT,
        f"📅 {len(events)}-week treatment plan",
        {"timeline": [e.model_dump() for e in events]},
    )
    await emit(EventKind.CASE_UPDATE, "timeline", {"timeline": [e.model_dump() for e in events]})
    return _text([e.model_dump() for e in events])


@tool(
    "explain_case_to_owner",
    "Generate a plain-English explanation of the case + vaccine rationale for the pet owner. "
    "Use at the end, after all other tools have populated the case.",
    {"patient_name": str, "cancer_type": str, "candidate_count": int, "top_mutation": str},
)
async def explain_case_to_owner(args: dict[str, Any]) -> dict[str, Any]:
    from .explain import explain_case

    await emit(EventKind.TOOL_START, "📝 Writing plain-English explanation")
    text = await explain_case(**args)
    await emit(
        EventKind.TOOL_RESULT,
        "📝 Explanation ready",
        {"explanation": text},
    )
    await emit(EventKind.CASE_UPDATE, "plain_english", {"plain_english": text})
    return _text({"explanation_preview": text[:400]})


# Export the list of tools for the MCP server
ALL_TOOLS = [
    read_pathology,
    run_neoantigen_pipeline,
    find_drug_interactions,
    find_clinical_trials,
    find_sequencing_labs,
    find_vet_oncologists,
    find_synthesis_vendors,
    validate_structure_3d,
    draft_email,
    generate_timeline,
    explain_case_to_owner,
]
