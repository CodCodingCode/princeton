"""Queue-based bridge between the main Streamlit thread and the async orchestrator.

The orchestrator emits events on an asyncio ``EventBus``; a worker thread
drains those into a ``queue.Queue`` that the main Streamlit rerun loop reads
synchronously. See ../CLAUDE.md § "Background thread + queue bridge".
"""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path

import streamlit as st

from neoantigen.agent import AgentEvent, EventBus, EventKind
from neoantigen.agent.melanoma_orchestrator import MelanomaOrchestrator


def run_agent_in_background(
    slide_path: Path,
    vcf_path: Path,
    event_q: queue.Queue,
    bus_holder: dict,
    tcga_patient_id: str | None = None,
) -> None:
    async def _bridge():
        bus = EventBus()
        bus_holder["bus"] = bus
        orch = MelanomaOrchestrator(
            slide_path=slide_path,
            vcf_path=vcf_path,
            bus=bus,
            tcga_patient_id=tcga_patient_id,
        )

        async def _drain():
            async for ev in bus.stream():
                event_q.put(ev)
            event_q.put(None)

        drain_task = asyncio.create_task(_drain())
        try:
            await orch.run()
        finally:
            await drain_task

    try:
        asyncio.run(_bridge())
    except Exception as e:
        event_q.put(AgentEvent(kind=EventKind.TOOL_ERROR, label=f"Fatal: {e}", payload={"error": str(e)}))
        event_q.put(None)


def drain_queue() -> bool:
    q = st.session_state.event_queue
    if q is None:
        return False
    done = False
    while True:
        try:
            ev = q.get_nowait()
        except queue.Empty:
            break
        if ev is None:
            done = True
            break
        ingest_event(ev)
        st.session_state.events.append(ev)
        if ev.kind == EventKind.DONE:
            done = True
    return done


def ingest_event(ev: AgentEvent) -> None:
    """Route event into the right pieces of session state for live rendering."""
    p = ev.payload
    if ev.kind == EventKind.THINKING_DELTA:
        node = p.get("node_id")
        if node != st.session_state.live_thinking_node:
            st.session_state.live_thinking = ""
            st.session_state.live_thinking_node = node
        st.session_state.live_thinking += p.get("delta", "")
    elif ev.kind == EventKind.NCCN_NODE_VISITED:
        st.session_state.nccn_steps.append(p.get("step", {}))
        st.session_state.live_thinking = ""
        st.session_state.live_thinking_node = None
    elif ev.kind == EventKind.VLM_FINDING:
        st.session_state.pathology = p.get("findings")
    elif ev.kind == EventKind.MOLECULE_READY:
        st.session_state.molecules.append(p.get("view"))
    elif ev.kind == EventKind.PIPELINE_RESULT:
        st.session_state.pipeline = p.get("pipeline")
    elif ev.kind == EventKind.STRUCTURE_READY:
        st.session_state.poses.append(p.get("pose"))
    elif ev.kind == EventKind.CASE_UPDATE and "mutations" in p:
        st.session_state.mutations = p.get("mutations", [])
    elif ev.kind == EventKind.RAG_CITATIONS:
        nid = p.get("node_id")
        if nid:
            st.session_state.citations_by_node[nid] = p.get("citations", [])
    elif ev.kind == EventKind.COHORT_TWINS_READY:
        cohort = dict(st.session_state.cohort or {})
        cohort["twins"] = p.get("twins", [])
        st.session_state.cohort = cohort
    elif ev.kind == EventKind.SURVIVAL_CURVE_READY:
        cohort = dict(st.session_state.cohort or {})
        cohort["overall_curve"] = p.get("overall_curve", [])
        cohort["twin_curve"] = p.get("twin_curve", [])
        cohort["median_survival_days"] = p.get("median_survival_days")
        cohort["twin_median_survival_days"] = p.get("twin_median_survival_days")
        cohort["cohort_size"] = p.get("cohort_size", 0)
        st.session_state.cohort = cohort
    elif ev.kind == EventKind.TRIAL_MATCHES_READY:
        st.session_state.trials = p.get("trials", [])
    elif ev.kind == EventKind.DONE:
        if "case" in p:
            st.session_state.final_case = p["case"]
    elif ev.kind == EventKind.CHAT_THINKING_DELTA:
        st.session_state.case_chat_buf_thinking += p.get("delta", "")
    elif ev.kind == EventKind.CHAT_ANSWER_DELTA:
        st.session_state.case_chat_buf_answer += p.get("delta", "")
    elif ev.kind == EventKind.CHAT_TOOL_CALL:
        st.session_state.case_chat_tool_calls.append({
            "name": p.get("name"),
            "arguments": p.get("arguments"),
        })
    elif ev.kind == EventKind.CHAT_UI_FOCUS:
        focus = p.get("focus") or ""
        panel = p.get("panel")
        if panel == 1 and focus:
            st.session_state.selected_node = focus
    elif ev.kind == EventKind.CHAT_DONE:
        st.session_state.case_chat_history.append({
            "role": "assistant",
            "content": st.session_state.case_chat_buf_answer.strip(),
            "thinking": st.session_state.case_chat_buf_thinking.strip(),
            "tool_calls": list(st.session_state.case_chat_tool_calls),
            "citations": p.get("citations", []),
        })
        st.session_state.case_chat_buf_thinking = ""
        st.session_state.case_chat_buf_answer = ""
        st.session_state.case_chat_tool_calls = []
        st.session_state.case_chat_streaming = False
