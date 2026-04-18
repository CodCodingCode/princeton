# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

Streamlit UI for the melanoma copilot. A single app ([app.py](app.py)) — a thin layer over the `neoantigen` package installed from [../backend/](../backend/). No logic lives here; all pipeline/orchestrator code is under `backend/src/neoantigen/`.

The sibling [README.md](README.md) is stale (references a removed `app_agent.py` and the old canine pipeline). Treat this CLAUDE.md as authoritative.

## Running

```bash
# one-time install (from repo root)
pip install -e '../backend[agent]'

# with the GH200 vLLM tunnel up, from this dir:
streamlit run app.py
```

[app.py](app.py) explicitly loads `../backend/.env` via `python-dotenv` (see [app.py:37](app.py#L37)), so env vars resolve regardless of CWD. For LLM config (`K2_BASE_URL`, `K2_API_KEY`, `NEOVAX_MODEL`), see [../backend/CLAUDE.md](../backend/CLAUDE.md).

## Architecture

**Four live panels** over one `MelanomaOrchestrator` run:

1. **NCCN guideline walker** — [melanoma_v2024.GRAPH](../backend/src/neoantigen/nccn/melanoma_v2024.py) rendered as a Plotly flowchart; nodes light up as the agent visits them, chosen edges highlighted. Click a node → `_node_detail` shows decision, evidence, reasoning, PubMed citations.
2. **Molecular landscape** — WT/mutant ESMFold PDBs + drug co-crystals per driver mutation, rendered with `py3Dmol`.
3. **Vaccine designer** — ranked peptide table, top peptide–HLA docked poses, mRNA construct bar chart (`_render_construct_bar`).
4. **Twin cohort + Kaplan-Meier** — TCGA-SKCM twin matches + KM survival curves (only populated when running on a TCGA patient with cohort built).

### Background thread + queue bridge

Streamlit is single-threaded and doesn't play well with asyncio, so the orchestrator runs in a worker thread:

```
[main]  _start_run ──► spawn thread ──► run_agent_in_background
                                            │
                                            ├─ asyncio.run(_bridge())
                                            │       ├─ EventBus.stream() ──► queue.Queue
                                            │       └─ MelanomaOrchestrator.run()
                                            │
[main rerun loop] _drain_queue ◄── queue.Queue
                  _ingest_event routes each event → session_state
                  st.rerun() every 0.4s while running
```

The `bus_holder` dict is shared between threads so the sidebar chat input can call `bus.push_interrupt(user_msg)` on the live `EventBus` from the main thread.

### Event → session_state routing ([app.py:132](app.py#L132), `_ingest_event`)

Every panel renders from `st.session_state`, never from events directly. Which key each event kind lands in:

| EventKind                 | Session state key                                               |
| ------------------------- | --------------------------------------------------------------- |
| `THINKING_DELTA`          | `live_thinking` (+ `live_thinking_node`) — reset on node change |
| `NCCN_NODE_VISITED`       | `nccn_steps[]`                                                  |
| `VLM_FINDING`             | `pathology`                                                     |
| `MOLECULE_READY`          | `molecules[]`                                                   |
| `PIPELINE_RESULT`         | `pipeline`                                                      |
| `STRUCTURE_READY`         | `poses[]`                                                       |
| `CASE_UPDATE` (mutations) | `mutations`                                                     |
| `RAG_CITATIONS`           | `citations_by_node[node_id]`                                    |
| `COHORT_TWINS_READY`      | `cohort["twins"]`                                               |
| `SURVIVAL_CURVE_READY`    | `cohort["overall_curve"/"twin_curve"/...]`                      |

When adding a new event kind: emit it from the orchestrator, then add a branch to `_ingest_event` and a reader in the relevant `_render_*` function.

### Paths

All paths are `__file__`-anchored so the app runs from anywhere:

```python
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
SAMPLE_DIR  = BACKEND_DIR / "sample_data"     # tcga_skcm_demo.vcf, tcga_skcm_demo_slide.jpg
OUT_DIR     = BACKEND_DIR / "out"             # uploads/ and case artefacts land here
```

Uploaded files (`slide_up`, `vcf_up`) are written to `OUT_DIR / "uploads"` before being passed to the orchestrator — the orchestrator needs real paths, not file-like objects.

### Two run modes

- **Run uploads** — user-provided slide + VCF via file uploaders.
- **Run TCGA demo** — auto-detects whether `scripts/fetch_tcga_skcm.py` has been executed (`cohort.has_cohort()`); if yes, passes a `tcga_patient_id` so the orchestrator swaps in the cohort Maf-derived mutations and enables Panel 4; otherwise falls back to `sample_data/tcga_skcm_demo.vcf` with no twins.

## Gotchas

- The `@st.cache_data` on `_graph_layout` caches the NCCN node positions. If you edit the graph structure, restart Streamlit (not just rerun).
- `st.plotly_chart(... on_select="rerun")` is how clicking an NCCN node updates `selected_node`. Requires Streamlit ≥ 1.31.
- `time.sleep(0.4) + st.rerun()` at the bottom drives the live update loop while `running`. Removing it freezes the UI until the next user interaction.
- `py3Dmol` HTML is injected via `st.components.v1.html` — tall viewers can clip; set `height=` on both the view and the component.
