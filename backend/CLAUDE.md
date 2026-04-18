# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

NeoVax — a personalized cancer vaccine pipeline that turns tumor mutations (VCF/TSV) into ranked neoantigen candidates and mRNA vaccine constructs. Hackathon project (Princeton Hacks).

## Commands

```bash
# Install (editable)
pip install -e .

# Install with ML scoring (MHCflurry)
pip install -e '.[ml]'
mhcflurry-downloads fetch   # one-time model download

# Run CLI
neoantigen demo                           # bundled BRAF sample
neoantigen run sample_data/braf_v600e.tsv # custom input
neoantigen run input.vcf --mhcflurry --with-apis --top 20 --max-nm 500

# Run web dashboard
streamlit run app.py
```

No test suite exists yet (test.py is empty).

## Architecture

**Dual interface** over a shared pipeline: CLI (`src/neoantigen/cli.py` via Typer/Rich) and web dashboard (`app.py` via Streamlit).

**Pipeline flow** (each step is a separate module in `src/neoantigen/pipeline/`):

```
parser.py   → Parse mutations from VCF (SnpEff ANN) or TSV
protein.py  → Fetch wild-type sequence from UniProt, apply mutation
peptides.py → Sliding-window peptide generation (8–11 aa)
scoring.py  → MHC binding prediction (HeuristicScorer or MHCflurryScorer via Protocol)
filters.py  → Filter by mutation presence, self-reactivity, affinity threshold
construct.py→ Assemble mRNA: Kozak + ATG + epitopes + linkers + stop codon
codon.py    → Codon-optimized reverse translation
runner.py   → Orchestrator (RunConfig dataclass, async execution)
```

**External APIs** (`src/neoantigen/external/`): DGIdb GraphQL for drug-gene interactions, ClinicalTrials.gov REST v2 for relevant trials. Both use `httpx.AsyncClient` with `asyncio.gather()`.

**Data layer**: All data flows through Pydantic models defined in `models.py` (Mutation, Peptide, Candidate, VaccineConstruct, PipelineResult, etc.).

**Caching**: Protein sequences cached at `~/.cache/neoantigen/proteins/`, AlphaFold structures at `~/.cache/neoantigen/structures/`. Streamlit uses `@st.cache_data`.

**Gene map** (`genes.py`): Hardcoded dict mapping ~20 common cancer driver genes to UniProt accessions. Unknown genes raise `KeyError` — add new mappings here.

## Key Design Decisions

- Scorer uses a Python Protocol (duck typing) so HeuristicScorer, DLAHeuristicScorer, and MHCflurryScorer are interchangeable without inheritance.
- MHCflurry is an optional dependency (`[ml]` extra) — the heuristic scorer works without it.
- The pipeline is sync at the module level but runner.py uses async for concurrent external API calls.
- `genes.lookup()` takes a `species` parameter; canine entries fall back to human orthologs since canine UniProt coverage is fragmented. Pipeline uses DLA heuristic scorer for canine alleles regardless of which reference protein is actually fetched.

## Agent layer (`src/neoantigen/agent/`)

Wraps the pipeline + external discovery as Claude Agent SDK tools. One entry point (`CaseOrchestrator`) drives the whole flow from `(pathology_pdf, tumor_vcf)` to a complete `CaseFile`.

**Architecture**:

```
app_agent.py / CLI (agent-demo)
    │
    ▼
CaseOrchestrator ── claude_agent_sdk.query() with an in-process MCP server
    │                                            │
    │                                            ▼
    │                           ALL_TOOLS from agent/tools.py
    │                           (read_pathology, run_neoantigen_pipeline,
    │                            find_sequencing_labs, find_vet_oncologists,
    │                            find_synthesis_vendors, validate_structure_3d,
    │                            find_drug_interactions, find_clinical_trials,
    │                            draft_email, generate_timeline,
    │                            explain_case_to_owner)
    │
    └─► EventBus (asyncio.Queue) ──► UI consumer
         tools emit progress events     (Streamlit live feed or CLI printer)
```

**Event flow**: Each tool emits `TOOL_START` + `TOOL_RESULT` (+ occasionally `CASE_UPDATE` payloads with structured data). `build_case_file(events)` reconstructs the final `CaseFile` by replaying CASE_UPDATE payloads. The Streamlit UI consumes events live via a thread + `queue.Queue` bridge (`app_agent.py:run_agent_in_background`).

**Model selection**: `NEOVAX_MODEL` env var overrides the default (`claude-sonnet-4-5`). Set to `claude-opus-4-6` for highest-quality orchestration at higher cost.

**Credentials**: `.env` is loaded by `app_agent.py` via `python-dotenv`. Keys:

- `ANTHROPIC_API_KEY` — for direct LLM calls in `pathology.py`, `emails.py`, `explain.py` (fall back to heuristics if missing). The agent SDK itself uses the `claude` CLI subprocess transport by default, which can reuse Claude Code's auth.
- `GOOGLE_PLACES_API_KEY` — for real lab/vet geo lookups (`labs.py` merges real + curated static results).
- `GOOGLE_CREDENTIALS_PATH` + `GMAIL_SENDER_EMAIL` — for actual email sending (`emails.send_via_gmail`). Drafts still generate without these.

## Run commands

```bash
# CLI headless
.venv/bin/neoantigen agent-demo --pdf sample_data/luna_pathology.pdf --vcf sample_data/luna_tumor.vcf

# Streamlit live UI
streamlit run app_agent.py

# Regenerate bundled demo pathology PDF after editing scripts/generate_luna_pdf.py
.venv/bin/python scripts/generate_luna_pdf.py
```
