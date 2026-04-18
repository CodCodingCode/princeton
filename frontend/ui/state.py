"""Streamlit session-state defaults. No neoantigen imports."""

from __future__ import annotations

import streamlit as st

DEFAULTS: dict = {
    "events": [],
    "event_queue": None,
    "agent_thread": None,
    "running": False,
    "done": False,
    "run_status": "idle",  # idle | running | done — drives the right-rail switch
    "started_at": None,
    "live_thinking": "",
    "live_thinking_node": None,
    "live_step_label": "",  # short human label of the current agent stage
    "active_bus": None,
    "focus_panel": None,    # 1-4, set by chat highlight_panel tool
    "focus_target": None,   # optional sub-element key
    "chat_messages": [],
    "nccn_steps": [],
    "molecules": [],
    "poses": [],
    "pipeline": None,
    "pathology": None,
    "pathology_slide_path": None,
    "pathology_thinking": "",
    "pathology_raw": "",
    "mutations": [],
    "selected_node": None,
    "citations_by_node": {},
    "cohort": None,
    "trials": [],
    "case_chat": None,
    "case_chat_history": [],
    "case_chat_queue": None,
    "case_chat_thread": None,
    "case_chat_streaming": False,
    "case_chat_buf_thinking": "",
    "case_chat_buf_answer": "",
    "case_chat_tool_calls": [],
    "final_case": None,
    # Regeneron-track additions
    "enrichment": None,                # EnrichedBiomarkers dict
    "biomarker_chips": [],             # list of BiomarkerChip dicts
    "intake": None,                    # ClinicianIntake dict — built from sidebar form
    "intake_form_ecog": None,
    "intake_form_lag3": None,
    "intake_form_recist": None,
    "intake_form_life_exp": None,
    "intake_form_prior_sys": None,
    "intake_form_prior_pd1": None,
}


def init() -> None:
    for key, default in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
