# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Princeton Hacks project — **NeoVax**, a melanoma oncologist copilot. Input: tumour VCF + pathology slide. Output: NCCN-walked treatment plan, molecular landscape (WT/mutant folds + drug co-crystals), ranked neoantigen peptides, mRNA construct, HLA peptide poses, and a TCGA twin-matched survival snapshot.

- [backend/](backend/) — Python package, CLI, pipeline, agent orchestration, sample + TCGA data, RAG store. See [backend/CLAUDE.md](backend/CLAUDE.md) for the authoritative architecture reference.
- [frontend/](frontend/) — Streamlit three-panel live UI in [frontend/app.py](frontend/app.py). Imports the `neoantigen` package installed from `backend/` and reads sample files from `../backend/sample_data/` via `__file__`-anchored paths.
- [plan.md](plan.md) — GH200 + vLLM + MediX-R1-30B integration plan. Still valid; K2 Think V2 remains the default fallback URL.

## Running the Streamlit app

The Streamlit deps ship with the backend's `[agent]` extra. Install once from the repo root, then run from `frontend/`:

```bash
pip install -e './backend[agent]'

cd frontend
streamlit run app.py
```

`app.py` explicitly loads `backend/.env` via `python-dotenv` (see [frontend/app.py:37](frontend/app.py#L37)), so env vars work regardless of CWD.

## LLM layer

The medical reasoning model is a Qwen3-VL-based VLM (MediX-R1-30B on GH200 via vLLM) with an OpenAI-compatible endpoint, accessed through [backend/src/neoantigen/agent/\_llm.py](backend/src/neoantigen/agent/_llm.py). It supports `<think>...</think>` streaming blocks surfaced as `THINKING_DELTA` events in the live UI.

Env vars (all optional — defaults point at the public K2 Think V2 endpoint as a fallback):

- `K2_BASE_URL` — OpenAI-compatible base URL (default `https://api.k2think.ai/v1`). Point at the SSH-tunneled vLLM endpoint, e.g. `http://localhost:8000/v1`.
- `K2_API_KEY` — required by the OpenAI client; vLLM ignores its value but one must be set.
- `NEOVAX_MODEL` — served model name, e.g. `medix-r1-30b`. Default `MBZUAI-IFM/K2-Think-v2`.
- `NEOVAX_LOG_PATH` — every model call is logged here (default `backend/out/k2.log`). **Check this first when agent output looks wrong.**

Call surfaces in `_llm.py`: `call_for_json`, `call_with_vision` (image input), `stream_with_thinking` (async iterator of `("thinking", chunk)` / `("answer", chunk)` tuples).

## Working in this repo

- Two entry points share the pipeline: the pure-pipeline CLI (`neoantigen run` / `neoantigen demo`) and the full agent flow (`neoantigen melanoma-demo` + [frontend/app.py](frontend/app.py)). Changes to pipeline behaviour should be considered against both.
- No test suite exists — [backend/test.py](backend/test.py) and [backend/main.py](backend/main.py) are empty placeholders.
- Generated artefacts (case JSON, logs, cached downloads) live in `backend/out/`.
