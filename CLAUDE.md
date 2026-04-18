# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Princeton Hacks project — **NeoVax**, a personalized cancer vaccine pipeline.

- [backend/](backend/) — Python package, CLI, pipeline, Claude Agent SDK orchestration, sample data. See [backend/CLAUDE.md](backend/CLAUDE.md) for full architecture and design decisions — it is the authoritative reference for anything under `backend/`.
- [frontend/](frontend/) — Streamlit dashboards ([frontend/app.py](frontend/app.py) and [frontend/app_agent.py](frontend/app_agent.py)). They import the `neoantigen` package installed from `backend/` and read sample files from `../backend/sample_data/` via `__file__`-anchored paths.

## Running the Streamlit apps

The Streamlit deps ship with the backend's `[agent]` extra, so install once from `backend/` and then run from `frontend/`:

```bash
# one-time install (from repo root)
pip install -e './backend[agent]'

# dashboards
cd frontend
streamlit run app.py         # plain pipeline dashboard
streamlit run app_agent.py   # agent-driven live dashboard (reads backend/.env)
```

`app_agent.py` loads `.env` via `python-dotenv` from the current working directory, so run it from `frontend/` (or copy/symlink the backend's `.env`) if you need `ANTHROPIC_API_KEY` and friends.

## Working in this repo

- Two entry points share the pipeline: the plain CLI/dashboard ([frontend/app.py](frontend/app.py), `neoantigen` CLI) and the agent-driven flow ([frontend/app_agent.py](frontend/app_agent.py), `neoantigen agent-demo`). When changing pipeline behavior, consider both.
- No test suite exists — `backend/test.py` and `backend/main.py` are empty placeholders.
- Uploads from `app_agent.py` are written to `backend/out/uploads/`, alongside the rest of the generated artifacts.
