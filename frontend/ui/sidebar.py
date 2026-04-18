"""Sidebar layout: input uploads, live-thinking feed, and the chat entrypoint."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import streamlit as st

from . import bridge, chat
from .paths import BACKEND_DIR, CASES_ROOT, DEMO_SLIDE, DEMO_VCF, OUT_DIR
from .state import DEFAULTS


def start_run(slide_path: Path, vcf_path: Path, tcga_patient_id: str | None = None) -> None:
    event_q: queue.Queue = queue.Queue()
    bus_holder: dict = {"bus": None}
    st.session_state.event_queue = event_q
    st.session_state.events = []
    st.session_state.live_thinking = ""
    st.session_state.live_thinking_node = None
    st.session_state.nccn_steps = []
    st.session_state.molecules = []
    st.session_state.poses = []
    st.session_state.pipeline = None
    st.session_state.pathology = None
    st.session_state.mutations = []
    st.session_state.chat_messages = []
    st.session_state.citations_by_node = {}
    st.session_state.cohort = None
    st.session_state.running = True
    st.session_state.done = False
    st.session_state.started_at = time.time()
    thread = threading.Thread(
        target=bridge.run_agent_in_background,
        args=(slide_path, vcf_path, event_q, bus_holder, tcga_patient_id),
        daemon=True,
    )
    thread.start()
    st.session_state.agent_thread = thread
    st.session_state.active_bus = bus_holder
    st.rerun()


def _render_inputs() -> None:
    st.markdown("## 🩺 Patient inputs")
    slide_up = st.file_uploader("Pathology slide (image)", type=["jpg", "jpeg", "png", "tif", "tiff"])
    vcf_up = st.file_uploader("Tumour VCF / TSV", type=["vcf", "tsv"])

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "Run uploads",
            disabled=(slide_up is None or vcf_up is None or st.session_state.running),
            use_container_width=True,
        ):
            upload_dir = OUT_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            slide_path = upload_dir / slide_up.name
            vcf_path = upload_dir / vcf_up.name
            slide_path.write_bytes(slide_up.read())
            vcf_path.write_bytes(vcf_up.read())
            start_run(slide_path, vcf_path)
    with col_b:
        if st.button("Run TCGA demo", type="primary", disabled=st.session_state.running, use_container_width=True):
            tcga_id: str | None = None
            slide_for_demo = DEMO_SLIDE
            try:
                from neoantigen.cohort import demo_patient_id, has_cohort
                if has_cohort():
                    tcga_id = demo_patient_id()
                    tcga_slide = BACKEND_DIR / "data" / "tcga_skcm" / "demo_slide.jpg"
                    if tcga_slide.exists():
                        slide_for_demo = tcga_slide
            except Exception:
                pass
            start_run(slide_for_demo, DEMO_VCF, tcga_patient_id=tcga_id)

    # Dataset case picker — requires `python backend/scripts/build_tcga_skcm_cases.py`.
    # Each case dir holds slide.jpg + tumor.vcf; the dir name is the TCGA submitter_id,
    # so passing it as tcga_patient_id unlocks the cohort/twin-matching panel.
    if CASES_ROOT.exists():
        dataset_cases = sorted(
            p.name for p in CASES_ROOT.iterdir()
            if p.is_dir() and (p / "slide.jpg").exists() and (p / "tumor.vcf").exists()
        )
        if dataset_cases:
            st.markdown("##### 📚 Or pick from dataset")
            selected_sid = st.selectbox(
                f"{len(dataset_cases)} TCGA-SKCM cases",
                dataset_cases,
                index=0,
                disabled=st.session_state.running,
                label_visibility="collapsed",
            )
            if st.button(
                f"Run {selected_sid}",
                disabled=st.session_state.running,
                use_container_width=True,
            ):
                case_dir = CASES_ROOT / selected_sid
                start_run(
                    case_dir / "slide.jpg",
                    case_dir / "tumor.vcf",
                    tcga_patient_id=selected_sid,
                )

    if st.session_state.done and st.button("↻ New case", use_container_width=True):
        for k in list(DEFAULTS.keys()):
            st.session_state[k] = DEFAULTS[k]
        st.rerun()


def _render_live_thinking() -> None:
    st.markdown("### 💭 Live thinking")
    if st.session_state.live_thinking:
        st.caption(f"Node: {st.session_state.live_thinking_node or '—'}")
        st.markdown(
            "<div style='font-family: ui-monospace, SFMono-Regular, monospace; font-size:0.78em; "
            "color:#475569; max-height:280px; overflow-y:auto; background:#f1f5f9; padding:8px; "
            f"border-radius:6px; white-space:pre-wrap;'>{st.session_state.live_thinking}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Reasoning will stream here while the agent walks the guideline.")


def _render_chat_input() -> None:
    if st.session_state.running:
        st.markdown("### 💬 Interrupt the walker")
        st.caption("Type a message to inject context into the next NCCN decision.")
    elif st.session_state.done:
        st.markdown("### 💬 Ask the case (Kimi K2)")
        st.caption("The agent has the full case. Ask follow-ups, request panels, pull papers.")
    else:
        st.markdown("### 💬 Chat")

    chat.render_history()

    chat_disabled = not (st.session_state.running or st.session_state.done) or st.session_state.case_chat_streaming
    placeholder = (
        "Interject…"
        if st.session_state.running
        else "Ask anything about the case…" if st.session_state.done
        else "Run the agent first"
    )
    user_msg = st.chat_input(placeholder, disabled=chat_disabled)
    if not user_msg:
        return
    if st.session_state.running:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        bus_holder = st.session_state.get("active_bus") or {}
        bus = bus_holder.get("bus")
        if bus is not None:
            bus.push_interrupt(user_msg)
            st.session_state.chat_messages.append(
                {"role": "agent", "content": "Acknowledged — will reconsider at the next NCCN node."}
            )
    elif st.session_state.done:
        chat.send_case_chat(user_msg)
        st.rerun()


def render() -> None:
    with st.sidebar:
        _render_inputs()
        st.divider()
        _render_live_thinking()
        st.divider()
        _render_chat_input()
