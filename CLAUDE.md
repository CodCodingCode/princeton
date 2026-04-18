# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Princeton Hacks project — **NeoVax**, a melanoma oncologist copilot. Input: tumour VCF (or TCGA-SKCM submitter id) + pathology slide. Output: NCCN-walked treatment plan, molecular landscape (WT/mutant folds + drug co-crystals), ranked neoantigen peptides, mRNA construct, HLA peptide poses, TCGA twin-matched survival snapshot, and matched clinical trials. After the run finishes, a sidebar chat agent (LangGraph + tool calls) drills into the case for tumour-board prep.

- [backend/](backend/) — Python package, CLI, pipeline, agent orchestration, post-run chat agent, sample + TCGA data, RAG store. See [backend/CLAUDE.md](backend/CLAUDE.md) for the authoritative architecture reference.
- [frontend/](frontend/) — Streamlit five-panel live UI in [frontend/app.py](frontend/app.py). Imports the `neoantigen` package installed from `backend/` and reads sample files from `../backend/sample_data/` via `__file__`-anchored paths.

## Running the Streamlit app

The Streamlit deps ship with the backend's `[agent]` extra. Install once from the repo root, then run from `frontend/`:

```bash
pip install -e './backend[agent]'

cd frontend
streamlit run app.py
```

[frontend/app.py](frontend/app.py) explicitly loads `backend/.env` via `python-dotenv` at [frontend/app.py:37](frontend/app.py#L37), so env vars work regardless of CWD.

## LLM layer

Two separate model clients:

- **Medical reasoning model** (Qwen3-VL-based VLM, MediX-R1-30B on GH200 via vLLM, OpenAI-compatible) — used by the orchestrator for VLM pathology, NCCN decisions, and molecular reasoning. Accessed via [backend/src/neoantigen/agent/\_llm.py](backend/src/neoantigen/agent/_llm.py). Supports `<think>...</think>` streaming blocks surfaced as `THINKING_DELTA` events.
- **Post-run chat model** (K2/Kimi with tool calling) — used by the LangGraph chat agent in [backend/src/neoantigen/chat/](backend/src/neoantigen/chat/). Accessed via [backend/src/neoantigen/chat/k2_client.py](backend/src/neoantigen/chat/k2_client.py). Emits `CHAT_*` events.

Env vars (all optional — orchestrator defaults point at the public K2 Think V2 endpoint):

- `K2_BASE_URL` — OpenAI-compatible base URL for the medical model (default `https://api.k2think.ai/v1`). Point at the SSH-tunneled vLLM endpoint, e.g. `http://localhost:8000/v1`.
- `K2_API_KEY` — required by the OpenAI client; vLLM ignores its value but one must be set.
- `NEOVAX_MODEL` — served model name, e.g. `medix-r1-30b`. Default `MBZUAI-IFM/K2-Think-v2`.
- `KIMI_API_KEY` — separate key for the sidebar chat agent; chat is disabled when unset.
- `NEOVAX_LOG_PATH` — every model call is logged here (default `backend/out/k2.log`). **Check this first when agent output looks wrong.**

Call surfaces in [\_llm.py](backend/src/neoantigen/agent/_llm.py): `call_for_json`, `call_with_vision` (image input), `stream_with_thinking` (async iterator of `("thinking", chunk)` / `("answer", chunk)` tuples).

## Working in this repo

- Three entry points share the pipeline: the pure-pipeline CLI (`neoantigen run` / `neoantigen demo`), the full agent flow (`neoantigen melanoma-demo` + [frontend/app.py](frontend/app.py)), and the batch runner (`neoantigen melanoma-batch` over per-case dirs built by `scripts/build_tcga_skcm_cases.py`). Changes to pipeline behaviour should be considered against all three.
- No test suite exists — [backend/test.py](backend/test.py) and [backend/main.py](backend/main.py) are empty placeholders.
- Generated artefacts (case JSON, logs, cached downloads) live in [backend/out/](backend/out/); per-case TCGA-SKCM builds live in [backend/data/tcga_skcm/](backend/data/tcga_skcm/).
