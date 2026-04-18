"""Streamlit session-state defaults. No neoantigen imports."""

from __future__ import annotations

import streamlit as st

DEFAULTS: dict = {
    "events": [],
    "event_queue": None,
    "agent_thread": None,
    "running": False,
    "done": False,
    "started_at": None,
    "live_thinking": "",
    "live_thinking_node": None,
    "active_bus": None,
    "chat_messages": [],
    "nccn_steps": [],
    "molecules": [],
    "poses": [],
    "pipeline": None,
    "pathology": None,
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
}


def init() -> None:
    for key, default in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
