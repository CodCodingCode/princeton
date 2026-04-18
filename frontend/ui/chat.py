"""Post-run chat agent dispatch.

The chat history rendering moved to ``ui/rail.py`` (the right-rail surface).
This module only owns the worker-thread spawn that streams a chat turn through
the existing event queue. ``bridge.ingest_event`` handles routing the resulting
``CHAT_*`` events into session_state.
"""

from __future__ import annotations

import asyncio
import queue
import threading

import streamlit as st

from neoantigen.agent import EventKind


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
                "KIMI_API_KEY not set in backend/.env — post-run chat disabled."
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
            import sys
            import traceback
            # Print the full traceback to the Streamlit log so we can debug
            # silent chat failures (the UI only surfaces the str(e)).
            print(f"[chat worker] {type(e).__name__}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            from neoantigen.agent import AgentEvent
            q.put(AgentEvent(kind=EventKind.TOOL_ERROR, label=f"Chat fatal: {type(e).__name__}: {e}"))
            q.put(AgentEvent(kind=EventKind.CHAT_DONE, label="done"))

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    st.session_state.case_chat_thread = t
