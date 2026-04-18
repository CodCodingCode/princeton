"""Post-run chat agent helpers + sidebar chat rendering.

All chat events flow through the same queue bridge as the orchestrator — see
``bridge.ingest_event`` for the CHAT_* routing.
"""

from __future__ import annotations

import asyncio
import queue
import threading

import streamlit as st

from neoantigen.agent import EventKind

from .citations import render_citations


def _short_args(args) -> str:
    if not args:
        return ""
    s = ", ".join(f"{k}={v!r}" for k, v in (args.items() if isinstance(args, dict) else []))
    return s if len(s) < 60 else s[:57] + "…"


def send_case_chat(user_msg: str) -> None:
    """Spawn a thread to stream one chat turn through the existing event queue."""
    if st.session_state.case_chat_streaming:
        return
    case_dump = st.session_state.final_case
    if case_dump is None:
        st.warning("Run the agent first.")
        return

    chat = st.session_state.case_chat
    if chat is None:
        try:
            from neoantigen.chat import CaseChatAgent
            from neoantigen.models import MelanomaCase
        except ImportError as e:
            st.error(f"Chat unavailable: {e}")
            return
        try:
            case_obj = MelanomaCase.model_validate(case_dump)
        except Exception as e:
            st.error(f"Failed to load case for chat: {e}")
            return
        chat = CaseChatAgent(case=case_obj)
        if not chat.available:
            st.warning(
                "K2_API_KEY not set in backend/.env — post-run chat disabled."
            )
            return
        st.session_state.case_chat = chat

    st.session_state.case_chat_history.append({"role": "user", "content": user_msg})
    st.session_state.case_chat_buf_thinking = ""
    st.session_state.case_chat_buf_answer = ""
    st.session_state.case_chat_tool_calls = []
    st.session_state.case_chat_streaming = True

    q = st.session_state.event_queue
    if q is None:
        q = queue.Queue()
        st.session_state.event_queue = q

    def _runner():
        from neoantigen.agent.events import EventBus

        async def _bridge():
            chat.bus = EventBus()

            async def _drain():
                async for ev in chat.bus.stream():
                    q.put(ev)

            drain_task = asyncio.create_task(_drain())
            try:
                await chat.send(user_msg)
            finally:
                await chat.bus.close()
                await drain_task

        try:
            asyncio.run(_bridge())
        except Exception as e:
            from neoantigen.agent import AgentEvent
            q.put(AgentEvent(kind=EventKind.TOOL_ERROR, label=f"Chat fatal: {e}"))
            q.put(AgentEvent(kind=EventKind.CHAT_DONE, label="done"))

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    st.session_state.case_chat_thread = t


def render_history() -> None:
    """Render interrupt-mode chat + the post-run case-chat history inline in the sidebar."""
    for msg in st.session_state.chat_messages:
        role_icon = "🧑‍⚕️" if msg["role"] == "user" else "🤖"
        st.markdown(f"{role_icon} {msg['content']}")

    for msg in st.session_state.case_chat_history:
        if msg["role"] == "user":
            st.markdown(f"🧑‍⚕️ {msg['content']}")
        else:
            with st.container(border=True):
                if msg.get("thinking"):
                    with st.expander("💭 reasoning", expanded=False):
                        st.markdown(
                            f"<div style='font-family: ui-monospace,monospace; font-size:0.78em; "
                            f"color:#475569; white-space:pre-wrap;'>{msg['thinking']}</div>",
                            unsafe_allow_html=True,
                        )
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        st.caption(f"🔧 {tc.get('name')}({_short_args(tc.get('arguments'))})")
                st.markdown(f"🤖 {msg['content']}")
                render_citations(msg.get("citations") or [], heading="📚 Sources")

    if st.session_state.case_chat_streaming:
        with st.container(border=True):
            if st.session_state.case_chat_buf_thinking:
                st.markdown(
                    f"<div style='font-family: ui-monospace,monospace; font-size:0.78em; "
                    f"color:#94a3b8; white-space:pre-wrap; max-height:140px; overflow-y:auto;'>"
                    f"💭 {st.session_state.case_chat_buf_thinking}</div>",
                    unsafe_allow_html=True,
                )
            if st.session_state.case_chat_buf_answer:
                st.markdown(f"🤖 {st.session_state.case_chat_buf_answer}")
            else:
                st.caption("…")
