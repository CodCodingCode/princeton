# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python 3.11+ package `neoantigen`. Ships one Typer command - `neoantigen serve` - which boots a FastAPI + SSE app on :8000. The app accepts a pathology PDF, runs an async orchestrator that extracts oncology fields → walks the NCCN railway → matches Regeneron trials → geocodes trial sites → lazily builds a ReportLab PDF, and streams every step live as Server-Sent Events for the Next.js frontend in [../frontend/](../frontend/).

## Commands

```bash
pip install -e '.[agent,web,pdf-vision,rag]'
neoantigen serve --reload                           # FastAPI on :8000
python scripts/build_pubmed_rag.py                  # one-shot, ~100–150 MB, 15–30 min
```

No test suite. [test_fixtures/](test_fixtures/) holds a full case's worth of pathology/imaging/chemo PDFs plus `GROUND_TRUTH.json` - use as fodder for the PDF extractor, not as pytest fixtures.

## Architecture

### The request flow ([agent/patient_orchestrator.py](src/neoantigen/agent/patient_orchestrator.py))

`PatientOrchestrator.run()` is a deterministic Python coroutine - **not** an LLM-driven tool loop - and emits on an `EventBus` at every step:

```
1. io/pdf_extract.extract_oncology_fields  → PathologyFindings + ClinicianIntake + Mutation[]
                                             (pypdf first; pdf2image + VLM fallback on scans)
2. nccn/walker.RailwayWalker.walk          → streams THINKING_DELTA, emits RAILWAY_STEP per node
   nccn/railway.build_map                  → RailwayMap for Mermaid
3. Parallel via asyncio.gather:
   ├─ external/regeneron_rules.evaluate_all → ranked TrialMatch list
   └─ external/trial_sites.fetch_trial_sites → geocoded TrialSite list (Google Maps)
4. DONE; the PDF report is built lazily on GET /report.pdf
```

Rationale for scripting the flow in Python: the medical model (K2 Think V2 / MediX-R1-30B) is tuned for reasoning, not multi-turn tool calling - we only invoke it where reasoning matters (NCCN decisions and the VLM fallback on scanned PDFs). The streaming `<think>` UX the frontend depends on is easier to preserve this way than through a tool-calling agent.

### Event bus ([agent/events.py](src/neoantigen/agent/events.py) + [web/storage.py](src/neoantigen/web/storage.py))

`EventBus` wraps an `asyncio.Queue`. `CaseRecord` owns one bus per case and runs a fanout pump that appends to a `replay` list and forwards to every subscriber queue. New SSE subscribers get the replay first, then live events - so reconnecting a tab mid-run catches up without re-running the orchestrator.

`EventKind` (17 values) is the source of truth for cross-cutting work - the frontend's SSE handler switches on these string values. Adding or renaming one touches both sides. Notable kinds: `PDF_EXTRACTED`, `RAILWAY_STEP`, `RAILWAY_READY`, `TRIAL_MATCHES_READY`, `TRIAL_SITES_READY`, `CASE_UPDATE`, and the `CHAT_*` family.

Case state lives only in memory ([web/storage.py `CaseStore`](src/neoantigen/web/storage.py)). Restarting the backend drops all cases.

### Treatment-railway walker ([nccn/](src/neoantigen/nccn/))

- [dynamic_walker.py](src/neoantigen/nccn/dynamic_walker.py) - the live path. Cancer-agnostic: for each of four fixed phases (staging → primary → systemic → followup) it builds a RAG query from the detected `primary_cancer_type` + driver mutations, retrieves top-K phase-2+ citations filtered by cancer type, and asks the medical model to emit 2-4 decisions per phase grounded in those citations. Emits `RAILWAY_STEP` per decision. Degrades to a "needs more data" placeholder per phase when the model or RAG is unavailable.
- [walker.py](src/neoantigen/nccn/walker.py) + [melanoma_v2024.py](src/neoantigen/nccn/melanoma_v2024.py) - **legacy.** Static melanoma decision graph driven node-by-node. Kept for reference but no longer wired into the orchestrator.
- [railway.py](src/neoantigen/nccn/railway.py) - converts walked `RailwayStep[]` into a `RailwayMap` the frontend renders (now via the custom `RailwayChart` component, not Mermaid).

### Post-run chat agent ([chat/](src/neoantigen/chat/))

LangGraph state machine: `rag_retrieve` → `k2_respond` → optional `tool_dispatch` loop (max 3 rounds). [agent.py:57 `_slim_case`](src/neoantigen/chat/agent.py#L57) renders the case as a ~2K-token string that ships with every Kimi call - so the agent remembers pathology, intake, railway, and mutations across turns without blowing context. Tools ([chat/tools.py](src/neoantigen/chat/tools.py)) never mutate the case; they return a short string and emit `CHAT_UI_FOCUS` events for the frontend to react to. Chat is disabled cleanly when `KIMI_API_KEY` is unset - [k2_client.py `has_kimi_key()`](src/neoantigen/chat/k2_client.py) gates `CaseChatAgent.available`.

### External APIs ([external/](src/neoantigen/external/))

- [trials.py](src/neoantigen/external/trials.py) - ClinicalTrials.gov REST v2 client (disk-cached).
- [regeneron_rules.py](src/neoantigen/external/regeneron_rules.py) - hardcoded predicate gates for four specific Regeneron-sponsored trials (currently all melanoma — fianlimab/cemiplimab + the BNT111 partnership). The registry is illustrative for the demo; the broader pipeline is cancer-agnostic, this matcher is the one component still narrowed to a sponsor's catalog. Most `never_in_intake_gates` (ECOG, prior therapy, RECIST) stay `needs_more_data` until the intake path captures them.
- [trial_sites.py](src/neoantigen/external/trial_sites.py) - geocodes NCT site addresses via Google Maps when `GOOGLE_MAPS_API_KEY` is set.

All use `httpx.AsyncClient` with `asyncio.gather()` where applicable.

### RAG ([rag/store.py](src/neoantigen/rag/store.py))

Chroma collection built by [scripts/build_pubmed_rag.py](scripts/build_pubmed_rag.py). Topic seeds drive NCBI E-utilities searches and each abstract is tagged with a `cancer_type` metadata field; query-time the walker filters retrieval to the case's cancer type so a lung case doesn't get melanoma trials back. `all-MiniLM-L6-v2` embeds the query and returns top-K `Citation` objects. `has_store()` gates both the walker (adds a "Recent literature" block to each decision prompt) and the chat agent's `pubmed_search` tool. Silent no-op when the store isn't built. The corpus seed list still leans melanoma-heavy (BRAF V600E, NRAS Q61, KIT, NF1, anti-PD-1, TMB, AJCC staging, brain mets…) - extend `scripts/build_pubmed_rag.py` to broaden coverage.

### Shared types ([models.py](src/neoantigen/models.py))

One Pydantic module defines every type that crosses a module boundary: `PathologyFindings`, `ClinicianIntake`, `Mutation`, `NCCNStep`, `RailwayStep`, `RailwayAlternative`, `RailwayMap`, `CitationRef`, `TrialMatch`, `TrialSite`, `PatientCase`. The frontend's [lib/types.ts](../frontend/lib/types.ts) mirrors these by hand - changing a field on either side needs both files updated.

## LLM layer ([agent/\_llm.py](src/neoantigen/agent/_llm.py))

Shared OpenAI-compatible client for the medical model. Backend selection is env-driven - swap K2 ↔ MediX without touching code.

- `K2_BASE_URL` (default `https://api.k2think.ai/v1`) - point at the SSH-tunneled vLLM endpoint, e.g. `http://localhost:8000/v1`.
- `K2_API_KEY` - required by the OpenAI client; vLLM ignores its value but one must be set.
- `NEOVAX_MODEL` - served model name (default `MBZUAI-IFM/K2-Think-v2`; use `medix-r1-30b` when hitting vLLM).
- `NEOVAX_LOG_PATH` - every request + response is logged here (default `out/k2.log`). **Check this first when agent output looks wrong.**

Call surfaces: `call_for_json(schema, system, user)`, `call_with_vision(images, system, user, schema)`, `stream_with_thinking(system, user)`. `has_api_key()` lets callers degrade gracefully.

Separately, the chat agent uses `KIMI_API_KEY` through [chat/k2_client.py](src/neoantigen/chat/k2_client.py) - two independent model clients.

## Key design decisions

- **Orchestrator is deterministic Python, not LLM tool-calling.** The medical model is only called for per-node NCCN decisions and the VLM PDF-extraction fallback. Keeps the flow reliable while preserving streaming `<think>`.
- **Chat flips that tradeoff.** Once the case is built, open-ended questions need a LangGraph tool-calling agent on a separate model (Kimi). The two agents never share a conversation - chat just gets a slimmed case summary.
- **Degrade, don't fail.** Missing `K2_API_KEY`, missing RAG store, missing Google Maps key, scanned PDF without `pdf-vision` - every path falls back silently and logs. `/api/health` surfaces which ones are wired up.
- **Event-bus fanout with replay.** Reconnecting SSE clients (or opening a second tab) replays everything the orchestrator emitted so far, then gets live events. Case state is otherwise in-memory and ephemeral.
