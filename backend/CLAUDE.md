# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

NeoVax — a personalized cancer vaccine pipeline that turns tumor mutations (VCF/TSV) into ranked neoantigen candidates and mRNA vaccine constructs. Hackathon project (Princeton Hacks).

The Streamlit UIs (`app.py`, `app_agent.py`) live in [../frontend/](../frontend/). This directory contains only the Python package, CLI, sample data, and scripts.

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
```

For the Streamlit dashboards, see [../frontend/](../frontend/).

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

## Gmail sign-in (for email sending)

Actual email sending (`emails.send_via_gmail`) goes through an OAuth installed-app flow handled by `agent/gmail_auth.py`. No env vars for creds or sender — the user clicks "Sign in with Google" in the Streamlit UI, a browser consent opens, and a token is cached on disk. The sender email is auto-discovered via `gmail.users.getProfile`. Drafts still generate without sign-in.

Requirements:

- A Desktop-app OAuth client in GCP Console. Download the client secrets JSON to `~/.config/neovax/client_secret.json` (override with `NEOVAX_GOOGLE_CLIENT_SECRET`).
- Add intended demo recipients as test users on the OAuth consent screen while the app is unverified.
- Scopes requested: `gmail.send`, `userinfo.email`.

Token cache location: `$NEOANTIGEN_CACHE/gmail_token.json` (override with `NEOVAX_GMAIL_TOKEN`). Sign out deletes the token + sender sidecar.

Headless machines: `run_local_server` needs a browser. Sign in once on a workstation, then copy the token file to the server if needed.

## Run commands

```bash
# CLI headless
.venv/bin/neoantigen agent-demo --pdf sample_data/luna_pathology.pdf --vcf sample_data/luna_tumor.vcf

# Streamlit live UI — see ../frontend/

# Regenerate bundled demo pathology PDF after editing scripts/generate_luna_pdf.py
.venv/bin/python scripts/generate_luna_pdf.py
```
