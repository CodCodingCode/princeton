# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**NeoVax** — a melanoma oncologist copilot. Input: tumour VCF (or a TCGA-SKCM submitter id) + pathology slide. Output: NCCN treatment plan, molecular landscape, ranked neoantigen peptides + mRNA construct, HLA peptide poses, TCGA twin-matched survival snapshot, matched clinical trials, and a post-run chat agent for tumour-board drill-down.

The Streamlit UI (`app.py`) lives in [../frontend/](../frontend/). This directory contains the Python package, CLI, sample data, TCGA cohort + RAG build scripts.

## Commands

```bash
# Install (editable). MHCflurry ships as a base dep; fetch its models once.
pip install -e .
mhcflurry-downloads fetch

# Pure-pipeline CLI (no LLM, no UI)
neoantigen demo                           # bundled BRAF V600E sample
neoantigen run sample_data/braf_v600e.tsv
neoantigen run input.vcf --top 20 --max-nm 500
neoantigen run input.vcf --scorer heuristic   # test fixture only; prints ⚠ banner

# Full melanoma agent (VLM pathology → NCCN walk → molecular → vaccine → twins → trials)
neoantigen melanoma-demo                                   # auto-picks TCGA demo patient if cohort built, else sample VCF + slide
neoantigen melanoma-demo --tcga-patient TCGA-XX-XXXX
neoantigen melanoma-demo --slide path/slide.jpg --vcf path/tumor.vcf

# Batch runner over every <submitter_id>/ under --dataset (expects slide.jpg + tumor.vcf per case)
neoantigen melanoma-batch --dataset data/tcga_skcm/cases --output-dir out/cases --limit 20

# One-off data builds (slow — run once)
python scripts/fetch_tcga_skcm.py          # populates data/tcga_skcm/
python scripts/build_tcga_skcm_cases.py    # fans cohort out to data/tcga_skcm/cases/<submitter_id>/{slide.jpg,tumor.vcf,metadata.json}
python scripts/build_pubmed_rag.py         # populates data/rag/ (ChromaDB)
```

For the Streamlit UI, see [../frontend/](../frontend/).

No test suite exists (`test.py` and `main.py` are empty).

## Architecture

**Dual interface** over a shared peptide pipeline:

- Pure CLI ([src/neoantigen/cli.py](src/neoantigen/cli.py) via Typer/Rich) — `run`, `demo`, `fetch-gene` for the scoring pipeline alone; `melanoma-demo` and `melanoma-batch` for the full agent.
- Five-panel Streamlit live UI ([../frontend/app.py](../frontend/app.py)) — drives `MelanomaOrchestrator` in a background thread and consumes its `EventBus` via a `queue.Queue` bridge.

### Peptide pipeline ([src/neoantigen/pipeline/](src/neoantigen/pipeline/))

Each step is a separate module:

```
parser.py    → Parse mutations from VCF (SnpEff ANN) or TSV
protein.py   → Fetch wild-type sequence from UniProt, apply mutation
peptides.py  → Sliding-window peptide generation (8–11 aa)
scoring.py   → MHC binding prediction (MHCflurryScorer default; HeuristicScorer is a ⚠ test fixture)
filters.py   → Filter by mutation presence, self-reactivity, affinity threshold
construct.py → Assemble mRNA: Kozak + ATG + epitopes + linkers + stop codon
codon.py     → Codon-optimized reverse translation
runner.py    → Orchestrator (RunConfig dataclass, sync run; async wrapper in the orchestrator)
```

All data flows through Pydantic models in [models.py](src/neoantigen/models.py): `Mutation`, `Peptide`, `Candidate`, `VaccineConstruct`, `PipelineResult`, `PathologyFindings`, `CitationRef`, `NCCNStep`, `TwinMatchRef`, `SurvivalPoint`, `CohortSnapshot`, `MoleculeView`, `StructurePose`, `TrialMatch`, `MelanomaCase`.

### Melanoma agent orchestrator ([src/neoantigen/agent/melanoma_orchestrator.py](src/neoantigen/agent/melanoma_orchestrator.py))

`MelanomaOrchestrator.run()` drives a deterministic Python workflow and emits progress on an `EventBus` (asyncio.Queue):

```
1. VLM pathology     → vlm_pathology.analyze_slide() → PathologyFindings
2. Mutations         → TCGA cohort lookup or pipeline.parser.parse()
3. NCCN walk         → nccn.walker.NCCNWalker streams THINKING_DELTA while walking
                       melanoma_v2024.GRAPH; emits NCCN_NODE_VISITED per node,
                       NCCN_PATH_COMPLETE when done
4. Parallel:
   ├─ Molecular landscape → agent.molecular.build_landscape() — WT/mutant folds +
   │                        drug co-crystals (DRUG_COMPLEX_READY) for top drivers
   └─ Vaccine pipeline    → pipeline.runner.run() (only if NCCN path reaches the
   │                        vaccine branch), then agent.structure.dock_peptide()
   │                        for the top 3 candidates into HLA-A*02:01
   └─ Clinical trials     → external.trials (ClinicalTrials.gov v2) + external.regeneron_rules
                            (hardcoded Regeneron trial predicates); TRIAL_MATCHES_READY
5. Cohort snapshot   → cohort.find_twins() + kaplan_meier() (only when running
                       on a TCGA patient and the cohort is built)
6. DONE              → final MelanomaCase bundled and emitted
```

Default HLA allele: `DEFAULT_HLA = "HLA-A*02:01"` at [melanoma_orchestrator.py:54](src/neoantigen/agent/melanoma_orchestrator.py#L54).

Event consumers:

- CLI `melanoma-demo` — renders events as Rich-styled lines (skips `THINKING_DELTA` / `ANSWER_DELTA`).
- CLI `melanoma-batch` — drains events silently; writes per-case JSON and a summary table.
- Streamlit — streams thinking live into the sidebar; reconstructs panel state from `CASE_UPDATE` / `DONE` payloads.

Full `EventKind` enum in [src/neoantigen/agent/events.py](src/neoantigen/agent/events.py): `TOOL_START`, `TOOL_RESULT`, `TOOL_ERROR`, `LOG`, `DONE`, `THINKING_DELTA`, `ANSWER_DELTA`, `VLM_FINDING`, `NCCN_NODE_VISITED`, `NCCN_PATH_COMPLETE`, `MOLECULE_READY`, `DRUG_COMPLEX_READY`, `PIPELINE_RESULT`, `STRUCTURE_READY`, `CASE_UPDATE`, `RAG_CITATIONS`, `COHORT_TWINS_READY`, `SURVIVAL_CURVE_READY`, `TRIAL_MATCHES_READY`, and the chat-agent set `CHAT_THINKING_DELTA`, `CHAT_ANSWER_DELTA`, `CHAT_TOOL_CALL`, `CHAT_TOOL_RESULT`, `CHAT_UI_FOCUS`, `CHAT_RERANK`, `CHAT_DONE`.

### NCCN walker ([src/neoantigen/nccn/](src/neoantigen/nccn/))

- [melanoma_v2024.py](src/neoantigen/nccn/melanoma_v2024.py) — static decision graph (`GRAPH`, `ROOT`). Nodes declare `evidence_required` (which `PatientState` fields to show the model) and option labels.
- [walker.py](src/neoantigen/nccn/walker.py) — at each node, builds a prompt with the question, option labels, sliced patient evidence, and optionally RAG citations from `rag.query_papers()`. Streams the model's `<think>` block as `THINKING_DELTA`, parses post-think JSON (`_DecisionResponse`), emits `NCCN_NODE_VISITED`, advances. Falls back to safest standard-of-care when evidence is missing.

### Cohort ([src/neoantigen/cohort/](src/neoantigen/cohort/))

TCGA-SKCM survival analysis, produced by `scripts/fetch_tcga_skcm.py`:

- [tcga.py](src/neoantigen/cohort/tcga.py) — `load_cohort()`, `has_cohort()`, `demo_patient_id()`, `mutations_for_patient()`. Returns empty cohort if data folder is missing; orchestrator falls back to "no twins available".
- [twins.py](src/neoantigen/cohort/twins.py) — `find_twins(query, others, top_k)` scored on BRAF V600E / NRAS Q61 / KIT / NF1 / stage / age / shared driver genes.
- [survival.py](src/neoantigen/cohort/survival.py) — `kaplan_meier()` returning `KMPoint` series.

### RAG ([src/neoantigen/rag/](src/neoantigen/rag/))

ChromaDB-backed PubMed retrieval built by `scripts/build_pubmed_rag.py`. `has_store()` gates whether the NCCN walker adds citations to each decision prompt, and is re-used by the chat agent's `pubmed_search` tool. Returns `Citation` objects (PMID, title, snippet) via `query_papers()`.

### External APIs ([src/neoantigen/external/](src/neoantigen/external/))

- [trials.py](src/neoantigen/external/trials.py) — ClinicalTrials.gov REST v2 client (disk-cached) returning raw `CTGovStudy` records.
- [regeneron_rules.py](src/neoantigen/external/regeneron_rules.py) — hardcoded predicate gates for four Regeneron-sponsored melanoma trials (age, AJCC stage, T-stage, driver mutations, etc.), used to produce ranked `TrialMatch` entries for the case.

Both use `httpx.AsyncClient` with `asyncio.gather()` where applicable.

### Post-run chat agent ([src/neoantigen/chat/](src/neoantigen/chat/))

LangGraph state machine that takes a completed `MelanomaCase` and lets the doctor drill in from the Streamlit sidebar. One user turn = one full graph traversal (`rag_retrieve` → `k2_respond` → optional `tool_dispatch` loop, max 3 rounds).

- [agent.py](src/neoantigen/chat/agent.py) — `CaseChatAgent` + graph builder. `_slim_case()` renders the case as a ~2–3K-token summary that ships with every K2 call, so the agent remembers pathology, NCCN path, top peptides, and cohort across turns. Streams `<think>` + answer chunks + tool calls out-of-band as `CHAT_*` events.
- [k2_client.py](src/neoantigen/chat/k2_client.py) — separate Kimi/K2 client using `KIMI_API_KEY`. `has_kimi_key()` gates `CaseChatAgent.available`; chat is cleanly disabled when unset.
- [tools.py](src/neoantigen/chat/tools.py) — five tools registered as OpenAI-format schemas in `TOOL_SCHEMAS`:
  - `highlight_panel(panel: 1–5, focus?)` — scroll the UI to a panel (1=NCCN, 2=molecular, 3=vaccine, 4=cohort) and optionally focus a sub-element.
  - `pubmed_search(query, top_k?)` — fresh PubMed RAG search.
  - `show_twin(submitter_id)` — open a twin in the cohort panel.
  - `rerank_peptides(by: binding|length|gene|rank)` — re-sort the vaccine table.
  - `explain_node(node_id)` — return recorded reasoning + citations for a walked NCCN node.
- [state.py](src/neoantigen/chat/state.py) — `ChatMessage`, `ChatState`, `ToolCall` typed dicts/dataclasses.

Tools never mutate the underlying case — they emit `CHAT_UI_FOCUS` / `CHAT_RERANK` / `CHAT_TOOL_RESULT` for the UI to react to, and return a short string so K2 can keep reasoning.

### Caching

- Protein sequences → `~/.cache/neoantigen/proteins/`
- AlphaFold structures → `~/.cache/neoantigen/structures/`
- ClinicalTrials.gov → on-disk cache in `trials.py`
- Streamlit → `@st.cache_data`

### Gene map ([genes.py](src/neoantigen/genes.py))

Hardcoded dict mapping ~20 common cancer driver genes to UniProt accessions. Unknown genes raise `KeyError` — add new mappings here.

## Key design decisions

- Scorer uses a Python `Protocol` (duck typing). `MHCflurryScorer` is the production default; `HeuristicScorer` is a test fixture (made-up anchor-residue math) that emits a `RuntimeWarning` and surfaces a ⚠ banner in CLI + Streamlit whenever it runs — including the orchestrator's fallback path if MHCflurry isn't installed.
- The pipeline is sync at the module level but the orchestrator uses `asyncio.gather` for concurrent molecular + pipeline + trials steps and `asyncio.to_thread` to offload the sync pipeline runner.
- The orchestrator is **deterministic Python**, not LLM-driven tool calling. The medical model is only invoked for per-node NCCN decisions (via `stream_with_thinking`) and for vision-based pathology extraction. Rationale: MediX-R1-30B is tuned for medical reasoning, not multi-turn tool-use loops — scripting the flow in Python keeps it reliable while preserving the streaming `<think>` UX the UI depends on.
- The **post-run chat** flips that tradeoff: once the case is built, the user asks open-ended questions, so `chat/` uses a LangGraph-driven tool-calling agent with a separate model (K2/Kimi). The two agents never share a conversation — chat just gets a slimmed case summary as context.

## LLM layer ([src/neoantigen/agent/\_llm.py](src/neoantigen/agent/_llm.py))

Shared OpenAI-compatible client for the medical reasoning model. Backend selection is env-driven — swap K2 ↔ MediX without touching code.

- `K2_BASE_URL` (default `https://api.k2think.ai/v1`) — point at the SSH-tunneled vLLM endpoint, e.g. `http://localhost:8000/v1`.
- `K2_API_KEY` — required by the OpenAI client; vLLM ignores its value.
- `NEOVAX_MODEL` — served model name (default `MBZUAI-IFM/K2-Think-v2`; use `medix-r1-30b` when hitting vLLM).
- `NEOVAX_LOG_PATH` — every request is logged here (default `out/k2.log`). Check this first when agent output looks wrong.

Separate from this, the chat agent uses `KIMI_API_KEY` through [chat/k2_client.py](src/neoantigen/chat/k2_client.py).

Call surfaces: `call_for_json(schema, system, user)`, `call_with_vision(images, system, user, schema)`, `stream_with_thinking(system, user)`. `has_api_key()` / heuristic fallbacks exist so modules can degrade gracefully when no key is set.

## Run commands

```bash
# Headless end-to-end
.venv/bin/neoantigen melanoma-demo \
  --slide sample_data/tcga_skcm_demo_slide.jpg \
  --vcf   sample_data/tcga_skcm_demo.vcf

# On a TCGA cohort patient (requires scripts/fetch_tcga_skcm.py first)
.venv/bin/neoantigen melanoma-demo --tcga-patient TCGA-XX-XXXX

# Batch over the full per-case dataset
.venv/bin/neoantigen melanoma-batch --dataset data/tcga_skcm/cases --limit 20

# Streamlit live UI — see ../frontend/
```
