# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Princeton Hacks project — **NeoVax**, a melanoma oncologist copilot. The user drops a pathology PDF; the backend extracts oncology fields, walks the NCCN railway (streaming `<think>` tokens from a medical reasoning model), matches Regeneron trials, geocodes trial sites, and produces a downloadable oncologist report. A sidebar Kimi chat drills into the case once the run lands.

Two services:

- [backend/](backend/) — Python 3.11+ package (`neoantigen`). Typer CLI with a single `serve` command that boots a FastAPI + SSE app on :8000. Shipped extras: `agent` (OpenAI + LangGraph), `web` (FastAPI/uvicorn/sse-starlette/reportlab/googlemaps), `pdf-vision` (pdf2image for VLM fallback on scanned PDFs), `rag` (Chroma + sentence-transformers).
- [frontend/](frontend/) — Next.js 15 + Tailwind dashboard. Pages: [/upload](frontend/app/upload) (PDF drop) and [/case/[id]](frontend/app/case) (live dashboard: extracted fields, Mermaid railway, trials list, Google Maps, Kimi chat, SSE event log, downloadable report).

[backend/CLAUDE.md](backend/CLAUDE.md) has a deeper architecture reference but parts of it still describe the older Streamlit + VCF + melanoma_orchestrator design — trust the code over that file when they disagree.

## Running both services

```bash
# Backend (from repo root)
pip install -e './backend[agent,web,pdf-vision,rag]'
neoantigen serve --reload                 # FastAPI on http://localhost:8000

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev                               # Next.js on http://localhost:3000
```

`next.config.mjs` proxies `/api/*` → `NEOVAX_BACKEND_URL` (default `http://localhost:8000`) so CORS never matters in dev. The backend's CORS allowlist can be overridden via `NEOVAX_CORS_ORIGINS` (comma-separated). Health check: `GET /api/health` reports which optional dependencies are wired up.

No test suite exists. `backend/test.py` and `backend/main.py` are empty placeholders.

## Request flow (one case)

```
POST /api/cases (multipart PDF)
  → PatientOrchestrator (backend/src/neoantigen/agent/patient_orchestrator.py)
    1. io/pdf_extract.extract_oncology_fields  → PathologyFindings + intake + mutations
    2. nccn/walker.RailwayWalker.walk          → streams THINKING_DELTA + RAILWAY_STEP
       then nccn/railway.build_map             → Mermaid-ready RailwayMap
    3. external/regeneron_rules.evaluate_all   → ranked TrialMatch list  ┐ parallel
    4. external/trial_sites.fetch_trial_sites  → geocoded TrialSite list ┘
    5. report/pdf_report.build_report_pdf lazily on GET /report.pdf
  → every step publishes on an asyncio EventBus stored in web/storage.CaseRecord
GET  /api/cases/{id}/stream (SSE)             → frontend ChatPanel / RailwayMermaid / EventLog
GET  /api/cases/{id}                          → current PatientCase snapshot
GET  /api/cases/{id}/report.pdf               → reportlab-built PDF
POST /api/cases/{id}/chat                     → LangGraph Kimi agent (chat/agent.py)
```

Case state lives in an in-memory `CaseStore` ([web/storage.py](backend/src/neoantigen/web/storage.py)) — restarting the backend drops all cases. Each case owns one `EventBus`; multiple SSE subscribers are fanned out via per-client queues.

## LLM layer

Two separate model clients:

- **Medical reasoning model** (K2 Think V2 by default; swap to MediX-R1-30B via SSH-tunneled vLLM). OpenAI-compatible. Used by the NCCN walker and the PDF vision fallback. Lives in [backend/src/neoantigen/agent/\_llm.py](backend/src/neoantigen/agent/_llm.py). `stream_with_thinking` surfaces `<think>...</think>` blocks as `THINKING_DELTA` events.
- **Post-run chat model** (Kimi/K2 with tool calling). Used by the LangGraph chat agent in [backend/src/neoantigen/chat/](backend/src/neoantigen/chat/). Emits `CHAT_*` events. Tools never mutate the case — they return UI focus hints and short strings for the model to keep reasoning.

Env vars (put them in `backend/.env`; the CLI loads it via `python-dotenv`):

| Var                               | Purpose                                                                              | Default                            |
| --------------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------- |
| `K2_BASE_URL`                     | OpenAI-compatible base URL for the medical model                                     | `https://api.k2think.ai/v1`        |
| `K2_API_KEY`                      | Required by the OpenAI client (vLLM ignores the value but one must be set)           | —                                  |
| `NEOVAX_MODEL`                    | Served model name (`medix-r1-30b` on vLLM)                                           | `MBZUAI-IFM/K2-Think-v2`           |
| `KIMI_API_KEY`                    | Sidebar chat; chat is cleanly disabled when unset                                    | —                                  |
| `NEOVAX_LOG_PATH`                 | Every model call is logged here — **check this first when agent output looks wrong** | `backend/out/k2.log`               |
| `GOOGLE_MAPS_API_KEY`             | Geocodes trial sites server-side; falls back to no coords                            | —                                  |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Renders the map in the browser; `TrialMap` degrades to a text list without it        | —                                  |
| `NEOVAX_BACKEND_URL`              | Frontend proxy target                                                                | `http://localhost:8000`            |
| `NEOVAX_CORS_ORIGINS`             | Comma-separated backend allowlist                                                    | `localhost:3000`, `localhost:5173` |

For the GH200 vLLM path, the user has a saved SSH tunnel — see memory `ssh_tunnel_medix.md`.

## Silent fallbacks (read first when output looks wrong)

The orchestrator never hard-fails on missing deps — it degrades to `needs_more_data` and logs a line. Symptom → cause map:

| Symptom                                                                        | Missing                                                                                             | Check                                                                                                            |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| NCCN railway renders every node as "standard of care" with no `<think>` stream | `K2_API_KEY` unset                                                                                  | [\_llm.py `has_api_key()`](backend/src/neoantigen/agent/_llm.py) false → walker falls back to safest option      |
| NCCN steps have no PubMed citations                                            | `scripts/build_pubmed_rag.py` never run                                                             | [rag/store.py `has_store()`](backend/src/neoantigen/rag/store.py) false → walker omits citation block            |
| Sidebar chat never appears / `/api/health` shows `kimi_api_key: false`         | `KIMI_API_KEY` unset                                                                                | [chat/k2_client.py `has_kimi_key()`](backend/src/neoantigen/chat/k2_client.py) false → chat endpoint returns 503 |
| Trial sites list present but map is blank                                      | `GOOGLE_MAPS_API_KEY` unset server-side, **or** `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` unset client-side | `/api/health` reports server-side; client-side is compile-time                                                   |
| PDF upload succeeds but `pathology` is mostly empty                            | Scanned PDF + `pdf-vision` extra not installed                                                      | [io/pdf_extract.py](backend/src/neoantigen/io/pdf_extract.py) falls back to text-only extraction                 |

## Working in this repo

- The Typer CLI is intentionally tiny — `neoantigen serve` is the only command. Don't bring back the old `run`/`demo`/`melanoma-demo`/`melanoma-batch` surface unless the user asks; those were removed with the pathology-PDF pivot.
- Shared Pydantic models live in [backend/src/neoantigen/models.py](backend/src/neoantigen/models.py). The frontend's `lib/types.ts` mirrors them by hand — when you change a model field, update both sides.
- Event kinds live in [backend/src/neoantigen/agent/events.py](backend/src/neoantigen/agent/events.py). The frontend's SSE handler switches on these string values, so adding or renaming one is a cross-cutting change.
- Generated artefacts (K2 logs, cached downloads, per-case JSON) live in [backend/out/](backend/out/).
- Regeneron track: the 4-trial registry (`REGENERON_TRIALS`) + structured eligibility predicates live in [backend/src/neoantigen/external/regeneron_rules.py](backend/src/neoantigen/external/regeneron_rules.py). Most `never_in_intake_gates` stay `needs_more_data` until the intake path captures ECOG / prior therapy / RECIST — start there to raise trial-match precision.
