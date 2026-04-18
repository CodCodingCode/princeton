# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**NeoVax** — a melanoma oncologist copilot. Input: tumour VCF (or a TCGA-SKCM submitter id) + pathology slide. Output: NCCN treatment plan, molecular landscape, ranked neoantigen peptides + mRNA construct, HLA peptide poses, TCGA twin-matched survival snapshot.

The Streamlit UI (`app.py`) lives in [../frontend/](../frontend/). This directory contains the Python package, CLI, sample data, TCGA cohort + RAG build scripts.

## Commands

```bash
# Install (editable)
pip install -e .

# Install with ML scoring (MHCflurry)
pip install -e '.[ml]'
mhcflurry-downloads fetch   # one-time model download

# Pure-pipeline CLI (no LLM, no UI)
neoantigen demo                           # bundled BRAF V600E sample
neoantigen run sample_data/braf_v600e.tsv
neoantigen run input.vcf --mhcflurry --top 20 --max-nm 500

# Full melanoma agent (VLM pathology → NCCN walk → molecular → vaccine → twins)
neoantigen melanoma-demo                                   # auto-picks TCGA demo patient if cohort built, else sample VCF + slide
neoantigen melanoma-demo --tcga-patient TCGA-XX-XXXX
neoantigen melanoma-demo --slide path/slide.jpg --vcf path/tumor.vcf

# One-off data builds (slow — run once)
python scripts/fetch_tcga_skcm.py   # populates data/tcga_skcm/
python scripts/build_pubmed_rag.py  # populates data/rag/ (ChromaDB)
```

For the Streamlit UI, see [../frontend/](../frontend/).

No test suite exists (`test.py` and `main.py` are empty).

## Architecture

**Dual interface** over a shared peptide pipeline:

- Pure CLI (`src/neoantigen/cli.py` via Typer/Rich) — `run`, `demo`, `fetch-gene` for the scoring pipeline alone; `melanoma-demo` for the full agent.
- Three-panel Streamlit live UI (`../frontend/app.py`) — drives `MelanomaOrchestrator` in a background thread and consumes its `EventBus` via a `queue.Queue` bridge.

### Peptide pipeline (`src/neoantigen/pipeline/`)

Each step is a separate module:

```
parser.py    → Parse mutations from VCF (SnpEff ANN) or TSV
protein.py   → Fetch wild-type sequence from UniProt, apply mutation
peptides.py  → Sliding-window peptide generation (8–11 aa)
scoring.py   → MHC binding prediction (HeuristicScorer or MHCflurryScorer via Protocol)
filters.py   → Filter by mutation presence, self-reactivity, affinity threshold
construct.py → Assemble mRNA: Kozak + ATG + epitopes + linkers + stop codon
codon.py     → Codon-optimized reverse translation
runner.py    → Orchestrator (RunConfig dataclass, sync run; async wrapper in the orchestrator)
```

All data flows through Pydantic models in `models.py` (Mutation, Peptide, Candidate, VaccineConstruct, PipelineResult, PathologyFindings, NCCNStep, MelanomaCase, CohortSnapshot, …).

### Melanoma agent orchestrator (`src/neoantigen/agent/melanoma_orchestrator.py`)

`MelanomaOrchestrator.run()` drives a deterministic Python workflow and emits progress on an `EventBus` (asyncio.Queue):

```
1. VLM pathology     → vlm_pathology.analyze_slide() → PathologyFindings
2. Mutations         → TCGA cohort lookup or pipeline.parser.parse()
3. NCCN walk         → nccn.walker.NCCNWalker streams THINKING_DELTA while walking
                       melanoma_v2024.GRAPH; emits NCCN_NODE_VISITED per node
4. Parallel:
   ├─ Molecular landscape → agent.molecular.build_landscape() — WT/mutant folds +
   │                        drug co-crystals for top drivers
   └─ Vaccine pipeline    → pipeline.runner.run() (only if NCCN path reaches the
                            vaccine branch), then agent.structure.dock_peptide()
                            for the top 3 candidates into HLA-A*02:01
5. Cohort snapshot   → cohort.find_twins() + kaplan_meier() (only when running
                       on a TCGA patient and the cohort is built)
```

Default HLA allele is hard-coded: `DEFAULT_HLA = "HLA-A*02:01"` at [melanoma_orchestrator.py:51](src/neoantigen/agent/melanoma_orchestrator.py#L51).

Event consumers:

- CLI `melanoma-demo` — renders events as Rich-styled lines (skips `THINKING_DELTA` / `ANSWER_DELTA`).
- Streamlit — streams thinking live into the sidebar; reconstructs panel state from `CASE_UPDATE` payloads.

### NCCN walker (`src/neoantigen/nccn/`)

- [melanoma_v2024.py](src/neoantigen/nccn/melanoma_v2024.py) — static decision graph (`GRAPH`, `ROOT`). Nodes declare `evidence_required` (which `PatientState` fields to show the model) and option labels.
- [walker.py](src/neoantigen/nccn/walker.py) — at each node, builds a prompt with the question, option labels, sliced patient evidence, and optionally RAG citations from `rag.query_papers()`. Streams the model's `<think>` block as `THINKING_DELTA`, parses post-think JSON (`_DecisionResponse`), emits `NCCN_NODE_VISITED`, advances. Falls back to safest standard-of-care when evidence is missing.

### Cohort (`src/neoantigen/cohort/`)

TCGA-SKCM survival analysis, produced by `scripts/fetch_tcga_skcm.py`:

- [tcga.py](src/neoantigen/cohort/tcga.py) — `load_cohort()`, `has_cohort()`, `demo_patient_id()`, `mutations_for_patient()`. Returns empty cohort if data folder is missing; orchestrator falls back to "no twins available".
- [twins.py](src/neoantigen/cohort/twins.py) — `find_twins(query, others, top_k)` scored on BRAF V600E / NRAS Q61 / KIT / NF1 / stage / age / shared driver genes.
- [survival.py](src/neoantigen/cohort/survival.py) — `kaplan_meier()` returning `KMPoint` series.

### RAG (`src/neoantigen/rag/`)

ChromaDB-backed PubMed retrieval built by `scripts/build_pubmed_rag.py`. `has_store()` gates whether the NCCN walker adds citations to each decision prompt. Returns `Citation` objects (PMID, title, snippet) via `query_papers()`.

### External APIs (`src/neoantigen/external/`)

DGIdb GraphQL (drug-gene interactions) and ClinicalTrials.gov REST v2 — both via `httpx.AsyncClient` with `asyncio.gather()`.

### Caching

- Protein sequences → `~/.cache/neoantigen/proteins/`
- AlphaFold structures → `~/.cache/neoantigen/structures/`
- Streamlit → `@st.cache_data`

### Gene map (`genes.py`)

Hardcoded dict mapping ~20 common cancer driver genes to UniProt accessions. Unknown genes raise `KeyError` — add new mappings here.

## Key design decisions

- Scorer uses a Python `Protocol` (duck typing) so `HeuristicScorer`, `DLAHeuristicScorer`, `MHCflurryScorer` are interchangeable without inheritance.
- MHCflurry is an optional `[ml]` extra — the heuristic scorer works without it.
- The pipeline is sync at the module level but the orchestrator uses `asyncio.gather` for concurrent molecular + pipeline steps and `asyncio.to_thread` to offload the sync pipeline runner.
- The orchestrator is **deterministic Python**, not LLM-driven tool calling. The medical model is only invoked for per-node NCCN decisions (via `stream_with_thinking`) and for vision-based pathology extraction. Rationale: MediX-R1-30B is tuned for medical reasoning, not multi-turn tool-use loops — scripting the flow in Python keeps it reliable while preserving the streaming `<think>` UX the UI depends on.

## LLM layer (`src/neoantigen/agent/_llm.py`)

Shared OpenAI-compatible client for the medical reasoning model. Backend selection is env-driven — swap K2 ↔ MediX without touching code.

- `K2_BASE_URL` (default `https://api.k2think.ai/v1`) — point at the SSH-tunneled vLLM endpoint, e.g. `http://localhost:8000/v1`.
- `K2_API_KEY` — required by the OpenAI client; vLLM ignores its value.
- `NEOVAX_MODEL` — served model name (default `MBZUAI-IFM/K2-Think-v2`; use `medix-r1-30b` when hitting vLLM).
- `NEOVAX_LOG_PATH` — every request is logged here (default `out/k2.log`). Check this first when agent output looks wrong.

Call surfaces: `call_for_json(schema, system, user)`, `call_with_vision(images, system, user, schema)`, `stream_with_thinking(system, user)`. `has_api_key()` / heuristic fallbacks exist so modules can degrade gracefully when no key is set.

See [../plan.md](../plan.md) for the GH200 + vLLM + MediX-R1-30B deployment plan.

## Run commands

```bash
# Headless end-to-end
.venv/bin/neoantigen melanoma-demo \
  --slide sample_data/tcga_skcm_demo_slide.jpg \
  --vcf   sample_data/tcga_skcm_demo.vcf

# On a TCGA cohort patient (requires scripts/fetch_tcga_skcm.py first)
.venv/bin/neoantigen melanoma-demo --tcga-patient TCGA-XX-XXXX

# Streamlit live UI — see ../frontend/
```
