"""Melanoma Oncologist Copilot — Streamlit entrypoint.

Layout:
    [top bar: logo + model + status pill]
    ┌─ sidebar ─┬───── tabs (Summary | Path+NCCN | Mol | Vax | Cohort | Trials) ─────┬─ right rail ─┐
    │ inputs    │                                                                       │ idle/running │
    │ patient   │                              [tab content]                            │ /done states │
    └───────────┴───────────────────────────────────────────────────────────────────────┴──────────────┘

The thick stuff lives in ``ui/`` — this file is just load-order + layout glue.

Run from /frontend with the GH200 vLLM tunnel up:
    streamlit run app.py
"""

from __future__ import annotations

import time

# CRITICAL: load .env BEFORE importing from `neoantigen` (several modules,
# notably agent/_llm.py, cache env vars at module-import time). Also eagerly
# import pandas before any worker thread can race plotly's isinstance checks.
from dotenv import load_dotenv

from ui.paths import BACKEND_DIR

load_dotenv(dotenv_path=BACKEND_DIR / ".env")

import pandas as _pd  # noqa: F401, E402 — eager import before thread spawn

import streamlit as st  # noqa: E402

from ui import (  # noqa: E402
    bridge,
    cohort,
    funnel,
    molecular,
    nccn,
    pathology,
    rail,
    sidebar,
    state,
    summary,
    theme,
    topbar,
    trials,
    vaccine,
)

st.set_page_config(
    page_title="NeoVax · Melanoma Copilot",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

state.init()
theme.inject_css()
topbar.render()
sidebar.render()

# Drain queue (writes into session_state via bridge.ingest_event)
if bridge.drain_queue():
    st.session_state.running = False
    st.session_state.done = True
    st.session_state.run_status = "done"


def _tab_label(name: str, populated: bool) -> str:
    return f"{name}  ✓" if populated else name


def _render_tabs() -> None:
    from ui.paths import BACKEND_DIR as _BD
    nccn_done = bool(st.session_state.nccn_steps) or bool(st.session_state.pathology)
    funnel_ready = (_BD / "out" / "cases" / "funnel_summary.json").exists()
    tab_labels = [
        "Summary",
        _tab_label("Pathology + NCCN", nccn_done),
        _tab_label("Molecular", bool(st.session_state.molecules)),
        _tab_label("Vaccine", bool(st.session_state.pipeline)),
        _tab_label("Cohort", bool(st.session_state.cohort)),
        _tab_label("Trials", bool(st.session_state.trials)),
        _tab_label("Portfolio funnel", funnel_ready),
    ]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        summary.render()

    with tabs[1]:
        c_left, c_right = st.columns([1, 1.5], gap="medium")
        with c_left:
            pathology.render_panel()
        with c_right:
            if st.session_state.run_status == "idle" and not st.session_state.nccn_steps:
                st.markdown(
                    theme.empty_state(
                        "🌳",
                        "NCCN walker idle",
                        "The melanoma decision tree will light up as the agent walks it.",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                nccn.render_flowchart()
        if st.session_state.selected_node:
            nccn.render_node_detail(st.session_state.selected_node)
        elif st.session_state.nccn_steps:
            nccn.render_node_detail(st.session_state.nccn_steps[-1]["node_id"])

    with tabs[2]:
        molecular.render_biomarker_chips(st.session_state.biomarker_chips or [])
        if not st.session_state.molecules:
            st.markdown(
                theme.empty_state(
                    "🧬",
                    "Folding driver proteins…",
                    "WT and mutant ESMFold structures plus drug co-crystals will appear here.",
                ),
                unsafe_allow_html=True,
            )
        else:
            for mol in st.session_state.molecules:
                molecular.render_molecule(mol)

    with tabs[3]:
        vaccine.render_panel()

    with tabs[4]:
        cohort.render_panel()

    with tabs[5]:
        trials.render_panel()

    with tabs[6]:
        funnel.render()


# ── Two-column split: main pane + right rail ─────────────────
main_col, rail_col = st.columns([3.4, 1], gap="medium")

with main_col:
    _render_tabs()

with rail_col:
    rail.render()

# ── Live update loop — drives the right-rail streaming ──
# (post-run chat input lives inside rail.render() so it sits in the rail,
#  not pinned to the page bottom.)
if st.session_state.running or st.session_state.case_chat_streaming:
    time.sleep(0.4)
    st.rerun()
