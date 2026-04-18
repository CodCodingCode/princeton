"""Right rail — idle empty state / running agent trace / post-run chat surface.

Owns rendering of the post-run chat history that used to live in ``sidebar.py``.
The actual chat input bar (``st.chat_input``) is pinned to the page bottom by
Streamlit; ``app.py`` owns it. This module only paints the rail body.
"""

from __future__ import annotations

import streamlit as st

from . import chat, theme
from .citations import render_citations


_PANEL_NAMES = {
    1: "Pathology + NCCN",
    2: "Molecular",
    3: "Vaccine",
    4: "Cohort",
}


def _short_args(args) -> str:
    if not args:
        return ""
    s = ", ".join(f"{k}={v!r}" for k, v in (args.items() if isinstance(args, dict) else []))
    return s if len(s) < 60 else s[:57] + "…"


def _render_idle() -> None:
    st.markdown(
        f'<div class="nv-rail-header">'
        f'<div class="nv-rail-title">Agent trace</div>'
        f'{theme.pill("idle")}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        theme.empty_state(
            "🩺",
            "Awaiting input",
            "Click <b>Run TCGA demo</b> in the sidebar to start. The agent's reasoning will stream here live.",
        ),
        unsafe_allow_html=True,
    )


def _render_running() -> None:
    step = st.session_state.live_step_label or "Initializing"
    node = st.session_state.live_thinking_node
    node_str = f' · {node}' if node else ''
    st.markdown(
        f'<div class="nv-rail-header">'
        f'<div class="nv-rail-title">Agent trace</div>'
        f'{theme.pill("running")}</div>'
        f'<div class="nv-rail-step">▶ {step}{node_str}</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.live_thinking:
        st.markdown(
            f'<div class="nv-think">{st.session_state.live_thinking}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="nv-think nv-think--idle">Awaiting first reasoning trace…</div>',
            unsafe_allow_html=True,
        )


def _render_focus_banner() -> None:
    panel = st.session_state.focus_panel
    if not panel:
        return
    pname = _PANEL_NAMES.get(panel, f"Panel {panel}")
    target = st.session_state.focus_target
    target_str = f" → {target}" if target else ""
    st.markdown(
        f'<div class="nv-pill nv-pill--accent" style="margin-bottom:10px;">'
        f'<span class="nv-pill-dot"></span>💡 Open the <b>&nbsp;{pname}&nbsp;</b> tab{target_str}</div>',
        unsafe_allow_html=True,
    )


def _render_chat_history() -> None:
    """Inline chat history, styled for the right rail (no sidebar emoji prefixes)."""
    for msg in st.session_state.case_chat_history:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="nv-chat-user"><b>You</b><br>{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            with st.container(border=True):
                if msg.get("thinking"):
                    with st.expander("💭 reasoning", expanded=False):
                        st.markdown(
                            f'<div class="nv-think">{msg["thinking"]}</div>',
                            unsafe_allow_html=True,
                        )
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        st.caption(f"🔧 {tc.get('name')}({_short_args(tc.get('arguments'))})")
                st.markdown(msg["content"])
                render_citations(msg.get("citations") or [], heading="📚 Sources")

    if st.session_state.case_chat_streaming:
        with st.container(border=True):
            if st.session_state.case_chat_buf_thinking:
                st.markdown(
                    f'<div class="nv-think" style="max-height:140px;">'
                    f'💭 {st.session_state.case_chat_buf_thinking}</div>',
                    unsafe_allow_html=True,
                )
            if st.session_state.case_chat_buf_answer:
                st.markdown(st.session_state.case_chat_buf_answer)
            else:
                st.caption("…")


def _render_chat_input_form() -> None:
    """Inline chat input that lives inside the rail (not pinned to page bottom).

    Uses an ``st.form`` so Enter submits and the input clears on send. We can't
    use ``st.chat_input`` here — Streamlit pins it to the page bottom regardless
    of where it's called from.
    """
    disabled = st.session_state.case_chat_streaming
    with st.form("rail_chat_form", clear_on_submit=True, border=False):
        user_msg = st.text_area(
            "Ask the case",
            placeholder=(
                "Streaming response…"
                if disabled else
                "Ask anything about the case…"
            ),
            label_visibility="collapsed",
            height=72,
            disabled=disabled,
            key="rail_chat_input",
        )
        send = st.form_submit_button(
            "Send  ↵",
            type="primary",
            use_container_width=True,
            disabled=disabled,
        )
    if send and user_msg.strip():
        chat.send_case_chat(user_msg.strip())
        st.rerun()


def _render_done() -> None:
    # Chat input first so it's the very top of the rail — no scrolling required.
    _render_chat_input_form()

    st.markdown(
        f'<div class="nv-rail-header" style="margin-top:6px;">'
        f'<div class="nv-rail-title">Ask the case</div>'
        f'{theme.pill("done")}</div>',
        unsafe_allow_html=True,
    )

    _render_focus_banner()

    if not st.session_state.case_chat_history and not st.session_state.case_chat_streaming:
        st.caption(
            "Try “why did you pick that NCCN path?” or "
            "“show me the longest-surviving twin.”"
        )

    _render_chat_history()

    # Collapsed view of the run's reasoning trace, tucked at the bottom.
    if st.session_state.live_thinking:
        with st.expander("View agent trace from this run", expanded=False):
            st.markdown(
                f'<div class="nv-think">{st.session_state.live_thinking}</div>',
                unsafe_allow_html=True,
            )


def render() -> None:
    """Single-call entrypoint. Read run_status, dispatch.

    NOTE: We use ``st.container(border=True)`` instead of an HTML wrapper div.
    A raw ``<div>`` injected via st.markdown() is closed by the browser the
    moment it sees the first Streamlit widget (because Streamlit injects its
    own elements between sibling markdown blocks), which leaves the wrap
    rendering empty above the actual content. ``st.container`` wraps properly.
    """
    status = st.session_state.run_status
    with st.container(border=True):
        if status == "idle":
            _render_idle()
        elif status == "running":
            _render_running()
        else:  # done
            _render_done()
