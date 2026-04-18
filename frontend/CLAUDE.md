# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

Streamlit UI for the melanoma copilot. The entrypoint [app.py](app.py) is now thin (~150 lines) — it loads `.env`, lays out the page, and dispatches to the [ui/](ui/) package. All logic remains in `backend/src/neoantigen/`. This CLAUDE.md is the only source of truth for the frontend (no README.md).

## Running

```bash
# one-time install (from repo root)
pip install -e '../backend[agent]'

# with the GH200 vLLM tunnel up, from this dir:
streamlit run app.py
```

[app.py](app.py) explicitly loads `../backend/.env` via `python-dotenv` BEFORE any `neoantigen` import (several modules cache env at import time). For LLM config (`K2_BASE_URL`, `K2_API_KEY`, `NEOVAX_MODEL`, `KIMI_API_KEY` for the chat agent), see [../backend/CLAUDE.md](../backend/CLAUDE.md).

## Layout (the modern SaaS dashboard rebuild)

```
[top bar: logo + model + animated status pill]
┌─ sidebar ─┬───── tabs (Summary | Path+NCCN | Mol | Vax | Cohort | Trials) ─────┬─ right rail ─┐
│ Run TCGA  │                                                                    │ idle         │
│ ▸ uploads │                              [tab content]                         │  / running   │
│ ▸ dataset │                                                                    │  / done      │
│ Patient   │                                                                    │ + chat input │
│ Intake ★  │                                                                    │ + history    │
└───────────┴────────────────────────────────────────────────────────────────────┴──────────────┘
```

- **Top bar** ([ui/topbar.py](ui/topbar.py)) — brand mark, model badge, status pill (idle / running / done) with a pulsing dot when streaming.
- **Left sidebar** ([ui/sidebar.py](ui/sidebar.py)) — single primary `Run TCGA demo` button, uploads + dataset picker as expanders, optional Regeneron clinician intake form, and a "Patient at a glance" card that appears once mutations or pathology arrive.
- **Main pane** — six tabs via `st.tabs`. Tab labels gain a trailing `✓` once their data lands. Tab order: `Summary` (landing), `Pathology + NCCN` (split column), `Molecular`, `Vaccine`, `Cohort`, `Trials`.
- **Right rail** ([ui/rail.py](ui/rail.py)) — owned by a single `render()` that branches on `run_status`:
  - `idle`: empty state placeholder.
  - `running`: current step indicator + live `<think>` stream in a monospace box.
  - `done`: "Ask the case" header + an inline chat-input form (text_area + Send button — sits in the rail, not pinned to the page bottom) + collapsed agent-trace expander + chat history.

`st.tabs` does NOT support programmatic switching. When the chat `highlight_panel` tool fires, the rail surfaces a `nv-pill--accent` banner pointing at the relevant tab — the user clicks it themselves.

## ui/ package

| Module                             | Public surface                                                                                                      | Notes                                                                                                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ui/theme.py](ui/theme.py)         | `COLORS`, `CSS`, `inject_css()`, `plotly_theme()`, `pill()`, `chip()`, `metric()`, `metric_grid()`, `empty_state()` | Single source of truth for every colour, spacing, and HTML helper. Never hardcode hex elsewhere.                                                                                      |
| [ui/state.py](ui/state.py)         | `DEFAULTS`, `init()`                                                                                                | Session-state schema. New keys: `run_status`, `live_step_label`, `focus_panel`, `focus_target`, `enrichment`, `biomarker_chips`, `intake`, `intake_form_*`.                           |
| [ui/bridge.py](ui/bridge.py)       | `run_agent_in_background()`, `drain_queue()`, `ingest_event()`, `_STEP_LABELS`                                      | Queue bridge unchanged in shape; routes one extra event (`ENRICHMENT_READY`) and writes `live_step_label` from the static `_STEP_LABELS` map for the rail's "current step" indicator. |
| [ui/topbar.py](ui/topbar.py)       | `render()`                                                                                                          | Brand + status pill.                                                                                                                                                                  |
| [ui/sidebar.py](ui/sidebar.py)     | `render()`, `start_run()`                                                                                           | Inputs + intake form + patient card. `start_run()` sets `run_status="running"` and passes the `ClinicianIntake` to the orchestrator.                                                  |
| [ui/summary.py](ui/summary.py)     | `render()`                                                                                                          | Hero card + 5-metric grid + final-recommendation callout + activity timeline derived from session_state.                                                                              |
| [ui/pathology.py](ui/pathology.py) | `render_panel()`                                                                                                    | Slide thumbnail + clinical summary card with chip row + AJCC T-stage fallback when the VLM doesn't supply one.                                                                        |
| [ui/nccn.py](ui/nccn.py)           | `render_flowchart()`, `render_node_detail()`, `_graph_layout()` (cached)                                            | Flowchart uses `theme.COLORS` + `theme.plotly_theme()`. Node-detail card uses `nv-card--accent` with chip evidence row.                                                               |
| [ui/molecular.py](ui/molecular.py) | `render_molecule()`, `render_biomarker_chips()`                                                                     | Each molecule wrapped in `nv-card`. Biomarker strip merges VLM + VCF + cBioPortal + clinician sources, colour-coded by provenance.                                                    |
| [ui/vaccine.py](ui/vaccine.py)     | `render_panel()`, `_render_construct_bar()`, `BNT111_ANTIGENS`                                                      | Top-3 hero peptide cards above the ranked table; mRNA construct uses `theme.plotly_theme()`.                                                                                          |
| [ui/cohort.py](ui/cohort.py)       | `render_panel()`                                                                                                    | HTML metric grid with delta sub on the twins card.                                                                                                                                    |
| [ui/trials.py](ui/trials.py)       | `render_panel()`, `_render_trial_card()`                                                                            | Cards use `theme.pill()` + chip-row criteria (ok / warn / bad) instead of emoji bullets.                                                                                              |
| [ui/chat.py](ui/chat.py)           | `send_case_chat()`                                                                                                  | Spawns the chat worker thread. History rendering moved out — see `ui/rail.py`.                                                                                                        |
| [ui/citations.py](ui/citations.py) | `render_citations()`                                                                                                | Shared PubMed list — used by NCCN node detail and chat assistant bubbles.                                                                                                             |
| [ui/paths.py](ui/paths.py)         | `BACKEND_DIR`, `SAMPLE_DIR`, `OUT_DIR`, `DEMO_VCF`, `DEMO_SLIDE`, `CASES_ROOT`                                      | All `__file__`-anchored.                                                                                                                                                              |

## Background thread + queue bridge

Streamlit is single-threaded and doesn't play well with asyncio, so the orchestrator runs in a worker thread:

```
[main]  sidebar.start_run ──► spawn thread ──► bridge.run_agent_in_background
                                                   │
                                                   ├─ asyncio.run(_bridge())
                                                   │       ├─ EventBus.stream() ──► queue.Queue
                                                   │       └─ MelanomaOrchestrator.run(intake=…)
                                                   │
[main rerun loop] bridge.drain_queue ◄── queue.Queue
                  bridge.ingest_event routes each event → session_state
                  st.rerun() every 0.4s while running
```

The chat agent ([ui/chat.py](ui/chat.py) `send_case_chat`) reuses the same queue-bridge pattern on its own dedicated thread. The `bus_holder` dict is shared so any sidebar widget could call `bus.push_interrupt(msg)` on the live `EventBus` from the main thread.

## Event → session_state routing ([ui/bridge.py](ui/bridge.py), `ingest_event`)

Every panel renders from `st.session_state`, never from events directly.

**Orchestrator events**

| EventKind                 | Session state key                                               |
| ------------------------- | --------------------------------------------------------------- |
| `THINKING_DELTA`          | `live_thinking` (+ `live_thinking_node`) — reset on node change |
| `NCCN_NODE_VISITED`       | `nccn_steps[]`                                                  |
| `NCCN_PATH_COMPLETE`      | sets `live_step_label` (rail step indicator)                    |
| `VLM_FINDING`             | `pathology`, `pathology_slide_path`, `pathology_thinking`       |
| `MOLECULE_READY`          | `molecules[]`                                                   |
| `DRUG_COMPLEX_READY`      | sets `live_step_label` (drug-co-crystal step in the rail)       |
| `PIPELINE_RESULT`         | `pipeline`                                                      |
| `STRUCTURE_READY`         | `poses[]`                                                       |
| `CASE_UPDATE` (mutations) | `mutations`                                                     |
| `RAG_CITATIONS`           | `citations_by_node[node_id]`                                    |
| `COHORT_TWINS_READY`      | `cohort["twins"]`                                               |
| `SURVIVAL_CURVE_READY`    | `cohort["overall_curve"/"twin_curve"/...]`                      |
| `TRIAL_MATCHES_READY`     | `trials[]`                                                      |
| `ENRICHMENT_READY`        | `enrichment`, `biomarker_chips[]`                               |
| `DONE`                    | `final_case` + `app.py` flips `run_status="done"`               |

**Chat events** (from `CaseChatAgent`, fires per user turn)

| EventKind             | Session state key                                                                 |
| --------------------- | --------------------------------------------------------------------------------- |
| `CHAT_THINKING_DELTA` | `case_chat_buf_thinking` (streamed)                                               |
| `CHAT_ANSWER_DELTA`   | `case_chat_buf_answer` (streamed)                                                 |
| `CHAT_TOOL_CALL`      | `case_chat_tool_calls[]`                                                          |
| `CHAT_TOOL_RESULT`    | handled inline in the assistant bubble (e.g. PubMed snippets)                     |
| `CHAT_UI_FOCUS`       | sets `focus_panel` + `focus_target` → rail surfaces "Open the {panel} tab" banner |
| `CHAT_RERANK`         | reorders the vaccine table                                                        |
| `CHAT_DONE`           | flushes buffers into `case_chat_history[]`, clears `case_chat_streaming`          |

When adding a new event kind: emit it from the orchestrator (or `chat/`), then add a branch to `bridge.ingest_event` and a reader in the relevant `ui/*.render*` function.

## Two run modes

- **Run uploads** — user-provided slide + VCF via the sidebar's "Or upload your own" expander. Files written to `OUT_DIR / "uploads"` before being passed to the orchestrator (it needs real paths, not file-like objects).
- **Run TCGA demo** — auto-detects whether `scripts/fetch_tcga_skcm.py` has been executed (`cohort.has_cohort()`); if yes, passes a `tcga_patient_id` so the orchestrator swaps in the cohort MAF-derived mutations and enables the Cohort panel; otherwise falls back to `sample_data/tcga_skcm_demo.vcf` with no twins. There's also a "Pick from dataset" expander that appears when `backend/data/tcga_skcm/cases/` is populated by `build_tcga_skcm_cases.py`.

## Gotchas

- `@st.cache_data` on `_graph_layout` caches the NCCN node positions. If you edit the graph structure, restart Streamlit (not just rerun).
- `st.plotly_chart(... on_select="rerun")` is how clicking an NCCN node updates `selected_node`. Requires Streamlit ≥ 1.31.
- `st.tabs` re-renders all tab bodies on every script run — heavy py3Dmol embeds may flicker during the 0.4s rerun loop. If it becomes a problem, wrap viewer HTML in `@st.cache_data` keyed on a content hash.
- `st.tabs` does NOT support programmatic tab switching, so the chat `highlight_panel` tool surfaces a hint banner in the rail rather than auto-switching.
- `st.chat_input` pins to the page bottom regardless of where it's called. The rail uses `st.form` + `st.text_area` + `st.form_submit_button` (with `clear_on_submit=True`) for an inline chat input that lives in the rail.
- `time.sleep(0.4) + st.rerun()` at the bottom of `app.py` drives the live update loop while `running` or `case_chat_streaming`. Removing it freezes the UI until the next user interaction.
- `py3Dmol` HTML is injected via `st.components.v1.html` — tall viewers can clip; set `height=` on both the view and the component.
- The chat agent's `KIMI_API_KEY` is separate from the orchestrator's `K2_API_KEY`. If chat silently refuses to respond, check `CaseChatAgent.available` / the `KIMI_API_KEY` env var — the orchestrator doesn't need it, so the run will still succeed without chat.
- All hex colours should come from `theme.COLORS` and all Plotly layouts from `theme.plotly_theme()`. Hardcoded hexes will drift from the rest of the UI when the palette changes.
